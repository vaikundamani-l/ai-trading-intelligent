import math
import time
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from app.config import settings

def funding_in_window(entry_unix_s: int, holding_bars: int = 5, buffer_sec: int = 120) -> bool:
    """Conservatively check if a funding snapshot lies in entry..holding window."""
    funding_sec = settings.FUNDING_INTERVAL_SEC
    bars_sec = 300  # 5 minutes
    left = entry_unix_s - buffer_sec
    right = entry_unix_s + holding_bars * bars_sec + buffer_sec
    next_snapshot = ((left - 1) // funding_sec + 1) * funding_sec
    return next_snapshot <= right

class Alpha5SBR5:
    """Primary deterministic strategy: SBR-5 Sweep and Reclaim.
    Ported directly from research reference btc_sbr5_backtest.py.
    """
    def __init__(self):
        self.name = "ALPHA-5: SBR-5 SWEEP & RECLAIM"
        self.lookback = settings.SBR5_LOOKBACK
        self.vol_lookback = settings.SBR5_VOL_LOOKBACK
        self.atr_lookback = settings.SBR5_ATR_LOOKBACK
        self.vol_multiplier = settings.SBR5_VOLUME_MULTIPLIER
        self.sweep_atr = settings.SBR5_SWEEP_ATR
        self.reclaim_atr = settings.SBR5_RECLAIM_ATR
        self.max_reclaim_atr = settings.SBR5_MAX_RECLAIM_ATR
        self.stop_buffer_atr = settings.SBR5_STOP_BUFFER_ATR
        self.target_r = settings.SBR5_TARGET_R
        self.max_hold_bars = settings.SBR5_MAX_HOLD_BARS
        self.min_stop_frac = settings.SBR5_MIN_STOP_FRACTION
        self.max_stop_frac = settings.SBR5_MAX_STOP_FRACTION
        self.tick_size = settings.TICK_SIZE

    def evaluate(self, df: pd.DataFrame, current_market: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates completed 5m bars. Never uses unfinalized candle data."""
        min_bars = max(self.lookback, self.vol_lookback, self.atr_lookback) + 2
        if df is None or len(df) < min_bars:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Insufficient completed 5m candles: have {len(df) if df is not None else 0}, need >= {min_bars}"],
                "invalidation_risks": ["Historical context building"],
                "is_setup": False
            }

        d = df[df["time"] + 300 <= time.time()].copy()
        if len(d) < min_bars:
            return {"is_setup": False, "reasons": ["Awaiting completed candles"]}
        prev_close = d['close'].shift(1)
        true_range = pd.concat([
            d['high'] - d['low'],
            (d['high'] - prev_close).abs(),
            (d['low'] - prev_close).abs()
        ], axis=1).max(axis=1)

        # All normalizers are calculated on bars strictly BEFORE the signal bar
        d['atr_prior'] = true_range.rolling(self.atr_lookback, min_periods=self.atr_lookback).mean().shift(1)
        d['prev_low'] = d['low'].rolling(self.lookback, min_periods=self.lookback).min().shift(1)
        d['prev_high'] = d['high'].rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        d['vol_prior'] = d['volume'].rolling(self.vol_lookback, min_periods=self.vol_lookback).mean().shift(1)

        # Last completed bar is at index -1 (or -2 if current bar is live in-progress)
        sig = d.iloc[-1]
        t = int(sig['time'])
        atr = float(sig['atr_prior'])
        prev_low = float(sig['prev_low'])
        prev_high = float(sig['prev_high'])
        vol_prior = float(sig['vol_prior'])
        
        c_open = float(sig['open'])
        c_high = float(sig['high'])
        c_low = float(sig['low'])
        c_close = float(sig['close'])
        c_vol = float(sig['volume'])

        if math.isnan(atr) or atr <= 0:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": ["ATR calculation not ready"],
                "invalidation_risks": [],
                "is_setup": False
            }

        # Volume condition
        vol_ok = c_vol >= self.vol_multiplier * vol_prior
        sweep_thresh = max(self.tick_size, self.sweep_atr * atr)

        # 1. Bullish SBR-5 condition
        # low swept previous low by >= sweep_thresh
        # close reclaimed inside [prev_low + 0.10*atr, prev_low + 1.20*atr]
        # close > open (bullish candle)
        # volume >= 1.25x prior 24 bars
        long_cond = (
            vol_ok and
            (c_low < prev_low - sweep_thresh) and
            (c_close > prev_low + self.reclaim_atr * atr) and
            (c_close < prev_low + self.max_reclaim_atr * atr) and
            (c_close > c_open)
        )

        # 2. Bearish SBR-5 condition (symmetric)
        short_cond = (
            vol_ok and
            (c_high > prev_high + sweep_thresh) and
            (c_close < prev_high - self.reclaim_atr * atr) and
            (c_close > prev_high - self.max_reclaim_atr * atr) and
            (c_close < c_open)
        )

        direction = 1 if long_cond else (-1 if short_cond else 0)
        
        if direction == 0:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "candle_time": t,
                "reasons": [
                    f"No liquidity sweep on completed candle (Low: ${c_low:.1f}, PrevLow24: ${prev_low:.1f})",
                    f"Volume: {c_vol:.1f} vs required {self.vol_multiplier * vol_prior:.1f} (Ratio: {c_vol/vol_prior if vol_prior > 0 else 0:.2f}x)",
                    f"Current ATR14: ${atr:.1f}"
                ],
                "invalidation_risks": ["Market in normal range oscillation"],
                "is_setup": False
            }

        # We have a candidate setup! Now calculate executable price, stop, target, and risk gates.
        best_bid = current_market.get("best_bid", c_close)
        best_ask = current_market.get("best_ask", c_close)
        slip = settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0

        # Modeled entry is next available executable ask for long, bid for short
        entry = (best_ask if direction == 1 else best_bid) * (1 + direction * slip)
        
        # Funding safety gate: check next bar entry timestamp against funding snapshots
        entry_ts = int(current_market.get("entry_time", t + 300))
        if funding_in_window(entry_ts, self.max_hold_bars, settings.FUNDING_BUFFER_SEC):
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": ["Funding snapshot within the 25-minute holding window. Trade gated per research safety rules."],
                "invalidation_risks": ["Adverse funding rate debit during snapshot"],
                "is_setup": False
            }

        # Stop loss calculation
        if direction == 1:
            raw_stop = c_low - self.stop_buffer_atr * atr
            stop = min(raw_stop, entry * (1 - self.min_stop_frac))
            stop = math.floor(stop / self.tick_size) * self.tick_size
        else:
            raw_stop = c_high + self.stop_buffer_atr * atr
            stop = max(raw_stop, entry * (1 + self.min_stop_frac))
            stop = math.ceil(stop / self.tick_size) * self.tick_size

        risk_move = direction * (entry - stop)
        if risk_move <= 0:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": ["Calculated stop is invalid or on wrong side of entry"],
                "invalidation_risks": ["Invalid stop distance"],
                "is_setup": False
            }

        stop_dist_frac = risk_move / entry
        if stop_dist_frac > self.max_stop_frac:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Stop distance {stop_dist_frac*100:.2f}% exceeds maximum allowed limit {self.max_stop_frac*100:.2f}%"],
                "invalidation_risks": ["Excessive volatility risk"],
                "is_setup": False
            }

        # Target calculation (1.8R)
        target = entry + direction * self.target_r * risk_move
        target = (math.ceil(target / self.tick_size) * self.tick_size if direction == 1
                  else math.floor(target / self.tick_size) * self.tick_size)

        # Fees & Slippage calculation (Taker + GST + Slippage)
        # Entry taker fee + Exit taker fee = 2 legs
        fee_fraction = 2 * (settings.FEE_TAKER_BPS / 10000.0) * settings.GST_MULTIPLIER
        slip_fraction = 2 * slip
        total_costs_bps = (fee_fraction + slip_fraction) * 10000.0
        gross_reward_bps = (abs(target - entry) / entry) * 10000.0
        net_reward_bps = gross_reward_bps - total_costs_bps
        risk_bps = (risk_move / entry) * 10000.0
        net_rr = net_reward_bps / (risk_bps + total_costs_bps) if (risk_bps + total_costs_bps) > 0 else 0.0

        if net_reward_bps <= total_costs_bps:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Expected gross reward ({gross_reward_bps:.1f} bps) cannot cover round-trip execution costs ({total_costs_bps:.1f} bps)"],
                "invalidation_risks": ["Fee/slippage drag dominates setup"],
                "is_setup": False
            }

        action = "BUY" if direction == 1 else "SELL"
        reasons = [
            f"Previous 24-bar {'low swept' if direction == 1 else 'high swept'} by {abs(c_low - prev_low if direction == 1 else c_high - prev_high):.1f} USD (> {sweep_thresh:.1f} USD)",
            f"Completed candle closed back inside range ({'reclaimed above L24' if direction == 1 else 'reclaimed below H24'})",
            f"Volume impulse confirmed: {c_vol:.1f} ({c_vol/vol_prior:.2f}x prior 24-bar mean)",
            f"Stop distance {stop_dist_frac*100:.2f}% is within acceptable 0.15% - 0.80% bounds",
            f"Net reward ({net_reward_bps:.1f} bps) clears conservative 2-leg taker fee & slippage ({total_costs_bps:.1f} bps)"
        ]

        risks = [
            "Signal expires if executable price deviates > 0.10% from modeled entry",
            "Maximum position holding period is strictly 25 minutes (5 candles)",
            "Stop loss gap risk exists during extreme market jumps",
            "Historical bar-level backtest does not guarantee live execution fills"
        ]

        return {
            "action": action,
            "direction": direction,
            "strategy": self.name,
            "entry_price": round(entry, 1),
            "stop_loss": round(stop, 1),
            "take_profit": round(target, 1),
            "risk_reward": round(net_rr, 2),
            "gross_reward_bps": round(gross_reward_bps, 1),
            "estimated_fees_bps": round(fee_fraction * 10000.0, 1),
            "estimated_slippage_bps": round(slip_fraction * 10000.0, 1),
            "net_reward_bps": round(net_reward_bps, 1),
            "candle_timestamp": t,
            "valid_until_ts": t + 300 + 120,  # Valid for 2 minutes into next bar
            "reasons": reasons,
            "invalidation_risks": risks,
            "is_setup": True
        }

sbr5_strategy = Alpha5SBR5()
