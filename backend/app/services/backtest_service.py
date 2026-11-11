import math
import time
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, replace
import pandas as pd
import numpy as np

from app.config import settings
from app.services.delta_market_data import market_data_service

@dataclass(frozen=True)
class BacktestConfig:
    lookback: int = 24
    vol_lookback: int = 24
    atr_lookback: int = 14
    volume_multiplier: float = 1.25
    sweep_atr: float = 0.12
    reclaim_atr: float = 0.10
    max_reclaim_atr: float = 1.20
    stop_buffer_atr: float = 0.10
    target_r: float = 1.80
    max_hold_bars: int = 5
    minimum_stop_fraction: float = 0.0015
    maximum_stop_fraction: float = 0.0080
    max_risk_fraction: float = 0.0025
    max_notional_equity_multiple: float = 2.0
    daily_loss_limit_fraction: float = 0.01
    peak_drawdown_kill_fraction: float = 0.05
    max_consecutive_losses: int = 4
    cooldown_bars: int = 12
    fee_taker_fraction: float = 0.0005
    gst_multiplier: float = 1.18
    slip_per_leg_bps: float = 1.0
    tick_size: float = 0.5
    funding_buffer_seconds: int = 120

def funding_in_window(entry_unix_s: int, holding_bars: int, buffer_sec: int) -> bool:
    funding_sec = 8 * 3600
    left = entry_unix_s - buffer_sec
    right = entry_unix_s + holding_bars * 300 + buffer_sec
    next_snapshot = ((left - 1) // funding_sec + 1) * funding_sec
    return next_snapshot <= right

def compute_sbr5_signals(df: pd.DataFrame, c: BacktestConfig) -> pd.DataFrame:
    d = df.copy()
    prev_close = d['close'].shift(1)
    true_range = pd.concat([
        d['high'] - d['low'],
        (d['high'] - prev_close).abs(),
        (d['low'] - prev_close).abs()
    ], axis=1).max(axis=1)

    d['atr_prior'] = true_range.rolling(c.atr_lookback, min_periods=c.atr_lookback).mean().shift(1)
    d['prev_low'] = d['low'].rolling(c.lookback, min_periods=c.lookback).min().shift(1)
    d['prev_high'] = d['high'].rolling(c.lookback, min_periods=c.lookback).max().shift(1)
    d['vol_prior'] = d['volume'].rolling(c.vol_lookback, min_periods=c.vol_lookback).mean().shift(1)
    atr = d['atr_prior']

    active = (d['volume'] >= c.volume_multiplier * d['vol_prior']) & (atr > 0)
    d['long_signal'] = (
        active &
        (d['low'] < d['prev_low'] - np.maximum(c.tick_size, c.sweep_atr * atr)) &
        (d['close'] > d['prev_low'] + c.reclaim_atr * atr) &
        (d['close'] < d['prev_low'] + c.max_reclaim_atr * atr) &
        (d['close'] > d['open'])
    ).fillna(False)

    d['short_signal'] = (
        active &
        (d['high'] > d['prev_high'] + np.maximum(c.tick_size, c.sweep_atr * atr)) &
        (d['close'] < d['prev_high'] - c.reclaim_atr * atr) &
        (d['close'] > d['prev_high'] - c.max_reclaim_atr * atr) &
        (d['close'] < d['open'])
    ).fillna(False)

    return d

def simulate_trade(d: pd.DataFrame, signal_idx: int, direction: int, c: BacktestConfig, equity: float) -> dict | None:
    i = signal_idx + 1
    if i >= len(d):
        return None
    sig = d.iloc[signal_idx]
    entry_bar = d.iloc[i]
    entry_t = int(entry_bar['dt'].timestamp())
    
    if funding_in_window(entry_t, c.max_hold_bars, c.funding_buffer_seconds):
        return None

    slip = c.slip_per_leg_bps / 10000.0
    entry = float(entry_bar['open']) * (1.0 + direction * slip)

    if direction == 1:
        raw_stop = float(sig['low']) - c.stop_buffer_atr * float(sig['atr_prior'])
        stop = min(raw_stop, entry * (1.0 - c.minimum_stop_fraction))
        stop = math.floor(stop / c.tick_size) * c.tick_size
    else:
        raw_stop = float(sig['high']) + c.stop_buffer_atr * float(sig['atr_prior'])
        stop = max(raw_stop, entry * (1.0 + c.minimum_stop_fraction))
        stop = math.ceil(stop / c.tick_size) * c.tick_size

    risk_move = direction * (entry - stop)
    if risk_move <= 0 or (risk_move / entry) > c.maximum_stop_fraction:
        return None

    target = entry + direction * c.target_r * risk_move
    target = (math.ceil(target / c.tick_size) * c.tick_size if direction == 1
              else math.floor(target / c.tick_size) * c.tick_size)

    risk_per_notional = (risk_move / entry) + (2 * c.fee_taker_fraction * c.gst_multiplier) + (2 * slip)
    notional = min(equity * c.max_risk_fraction / risk_per_notional, equity * c.max_notional_equity_multiple)
    lot_notional = entry * 0.001
    notional = math.floor((notional + 1e-12) / lot_notional) * lot_notional
    
    if notional <= 0:
        return None

    exit_px = float('nan')
    exit_reason = ''
    exit_i = i

    for j in range(i, min(i + c.max_hold_bars, len(d))):
        bar = d.iloc[j]
        opened_past_stop = (direction == 1 and bar['open'] <= stop) or (direction == -1 and bar['open'] >= stop)
        stop_hit = (direction == 1 and bar['low'] <= stop) or (direction == -1 and bar['high'] >= stop)
        target_hit = (direction == 1 and bar['high'] >= target) or (direction == -1 and bar['low'] <= target)

        if opened_past_stop or stop_hit:
            base = min(stop, float(bar['open'])) if direction == 1 else max(stop, float(bar['open']))
            exit_px = base * (1.0 - direction * slip)
            exit_reason = 'stop_or_ambiguous_both_hit'
        elif target_hit:
            exit_px = float(target) * (1.0 - direction * slip)
            exit_reason = 'target'
        elif j == min(i + c.max_hold_bars, len(d)) - 1:
            exit_px = float(bar['close']) * (1.0 - direction * slip)
            exit_reason = 'time_limit_25m'
        else:
            continue
        exit_i = j
        break

    if not math.isfinite(exit_px):
        return None

    gross_fraction = direction * (exit_px - entry) / entry
    fees_fraction = c.fee_taker_fraction * c.gst_multiplier * (1.0 + exit_px / entry)
    net_fraction = gross_fraction - fees_fraction
    pnl = notional * net_fraction

    return {
        'signal_utc': sig['dt'].isoformat(),
        'entry_utc': entry_bar['dt'].isoformat(),
        'exit_utc': d.iloc[exit_i]['dt'].isoformat(),
        'direction': direction,
        'entry': round(entry, 1),
        'stop': round(stop, 1),
        'target': round(target, 1),
        'exit': round(exit_px, 1),
        'reason': exit_reason,
        'holding_bars': exit_i - i + 1,
        'notional_usd': round(notional, 2),
        'gross_bps': round(gross_fraction * 10000.0, 1),
        'fees_bps': round(fees_fraction * 10000.0, 1),
        'net_bps': round(net_fraction * 10000.0, 1),
        'pnl_usd': round(pnl, 2),
        'exit_idx': exit_i,
        'hour_of_day': entry_bar['dt'].hour
    }

def run_sbr5_backtest(df: pd.DataFrame, c: BacktestConfig = BacktestConfig(), initial_equity: float = 10000.0) -> Dict[str, Any]:
    if df is None or len(df) < 50:
        return {"error": "Insufficient historical candles for backtest"}

    d = compute_sbr5_signals(df, c)
    equity = initial_equity
    peak = initial_equity
    records = []
    equity_curve = [{"time": d.iloc[0]['dt'].isoformat(), "equity": initial_equity}]
    
    start_idx = max(c.lookback, c.vol_lookback, c.atr_lookback) + 1
    i = start_idx
    losing_streak = 0
    cooldown_end = -1
    daily_start_equity = initial_equity
    day = None

    while i < len(d) - 1:
        current_day = d.iloc[i]['dt'].date()
        if current_day != day:
            day = current_day
            daily_start_equity = equity

        # Check daily loss limit and cooldown
        if i < cooldown_end or equity <= daily_start_equity * (1.0 - c.daily_loss_limit_fraction):
            i += 1
            continue

        # Hard peak drawdown kill-switch
        if equity <= peak * (1.0 - c.peak_drawdown_kill_fraction):
            break

        direction = 1 if d.iloc[i]['long_signal'] else (-1 if d.iloc[i]['short_signal'] else 0)
        if direction == 0:
            i += 1
            continue

        trade = simulate_trade(d, i, direction, c, equity)
        if trade is None:
            i += 1
            continue

        equity += trade['pnl_usd']
        peak = max(peak, equity)
        trade['equity_after'] = round(equity, 2)
        records.append(trade)
        equity_curve.append({"time": trade['exit_utc'], "equity": round(equity, 2)})

        losing_streak = losing_streak + 1 if trade['pnl_usd'] <= 0 else 0
        i = trade['exit_idx'] + 1
        if losing_streak >= c.max_consecutive_losses:
            cooldown_end = i + c.cooldown_bars
            losing_streak = 0

    # Buy & Hold Return
    bh_start = d.iloc[start_idx]['close']
    bh_end = d.iloc[-1]['close']
    buy_hold_ret_pct = ((bh_end / bh_start) - 1.0) * 100.0 if bh_start > 0 else 0.0

    if not records:
        return {
            "trades_count": 0,
            "start_equity": initial_equity,
            "end_equity": round(equity, 2),
            "total_return_pct": 0.0,
            "buy_and_hold_return_pct": round(buy_hold_ret_pct, 2),
            "win_rate_pct": 0.0,
            "profit_factor": None,
            "max_drawdown_pct": 0.0,
            "avg_net_bps": 0.0,
            "trades": [],
            "equity_curve": equity_curve,
            "status": "NO TRADES IN SELECTED WINDOW"
        }

    wins = [t['pnl_usd'] for t in records if t['pnl_usd'] > 0]
    losses = [t['pnl_usd'] for t in records if t['pnl_usd'] < 0]
    win_rate = (len(wins) / len(records)) * 100.0
    tot_win = sum(wins)
    tot_loss = abs(sum(losses))
    profit_factor = (tot_win / tot_loss) if tot_loss > 0 else (999.0 if tot_win > 0 else None)

    # Calculate Max Drawdown
    eq_series = pd.Series([initial_equity] + [t['equity_after'] for t in records])
    cummax = eq_series.cummax()
    drawdowns = (eq_series - cummax) / cummax
    max_dd_pct = float(drawdowns.min() * 100.0)

    # Cost Sensitivity Analysis (Stress test: 0 bp, 1 bp, 2 bp, 3 bp, 5 bp)
    sensitivity = []
    for slip_bps in [0.0, 1.0, 2.0, 3.0, 5.0]:
        c_slip = replace(c, slip_per_leg_bps=slip_bps)
        # Fast approximation of net effect across trades
        add_slip_frac = 2 * (slip_bps - c.slip_per_leg_bps) / 10000.0
        adj_pnl = sum(t['pnl_usd'] - (t['notional_usd'] * add_slip_frac) for t in records)
        adj_ret = (adj_pnl / initial_equity) * 100.0
        sensitivity.append({
            "slippage_bps": slip_bps,
            "net_return_pct": round(adj_ret, 2),
            "total_pnl_usd": round(adj_pnl, 2)
        })

    # Hourly Distribution
    hourly = {}
    for t in records:
        h = t['hour_of_day']
        if h not in hourly:
            hourly[h] = {"trades": 0, "wins": 0, "pnl": 0.0}
        hourly[h]["trades"] += 1
        if t["pnl_usd"] > 0:
            hourly[h]["wins"] += 1
        hourly[h]["pnl"] = round(hourly[h]["pnl"] + t["pnl_usd"], 2)

    return {
        "trades_count": len(records),
        "start_equity": initial_equity,
        "end_equity": round(equity, 2),
        "total_return_pct": round(((equity / initial_equity) - 1.0) * 100.0, 2),
        "buy_and_hold_return_pct": round(buy_hold_ret_pct, 2),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "max_drawdown_pct": round(abs(max_dd_pct), 2),
        "avg_net_bps": round(float(np.mean([t['net_bps'] for t in records])), 1),
        "trades": records,
        "equity_curve": equity_curve,
        "cost_sensitivity": sensitivity,
        "hourly_performance": hourly,
        "status": "RESEARCH COMPLETE (Not forward-tested profitability proof)"
    }
