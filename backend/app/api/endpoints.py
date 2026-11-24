import time
import math
from app.database import update_risk_state
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Literal
import pandas as pd

from app.config import settings
from app.timeframes import TIMEFRAME_SECONDS, timeframe_seconds
from app.strategies.engine_safety import resolve_bar_exit
from app.services.delta_market_data import market_data_service
from app.decision_engine import decision_engine, SignalDecisionEngine
from app.ml.prediction_engine import prediction_engine
from app.services.paper_trading import paper_trading_service
from app.services.backtest_service import run_sbr5_backtest, BacktestConfig, compute_sbr5_signals
from app.database import get_recent_signals, get_recent_alerts, get_risk_state, insert_alert
from app.strategies.alpha1_orderflow import alpha1_strategy
from app.strategies.alpha2_volatility import alpha2_strategy
from app.strategies.alpha3_basis import alpha3_strategy
from app.strategies.alpha4_dislocation import alpha4_dislocation
from app.strategies.alpha5_sbr5 import sbr5_strategy

router = APIRouter(prefix="/api")
# Selected-timeframe signals are observational and do not write into the legacy
# 5m signal ledger or drive the background paper-execution loop.
timeframe_engines = {resolution: SignalDecisionEngine(resolution, persist=False)
                     for resolution in TIMEFRAME_SECONDS if resolution != "5m"}

@router.get('/strategies/bollinger8h')
@router.get('/strategies/bollinger')
def bollinger8h_report(minutes: int = 480):
    if minutes < 5 or minutes > 1440 or minutes % 5:
        raise HTTPException(422, 'Choose a multiple of 5 minutes, from 5 to 1440.')
    from app.strategies.bollinger8h import analyze, replay
    base = 3600 if minutes % 60 == 0 else 900 if minutes % 15 == 0 else 300
    # Never select a source interval larger than the requested timeframe.
    base = min(base, minutes*60)
    resolution = {3600:'1h',900:'15m',300:'5m'}[base]
    duration = minutes * 60
    hourly = market_data_service.fetch_candles_rest(resolution, count=1000)
    state = market_data_service.get_market_state()
    signal = analyze(hourly, state, duration=duration, base=base)
    risk = get_risk_state() or {}
    safe = bool(state.get('is_data_safe')) and state.get('exchange_status') == 'operational'
    spread = float(state.get('spread_bps') or 0)
    bid, ask = float(state.get('best_bid') or 0), float(state.get('best_ask') or 0)
    quote = math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask
    safety = {'safe_feed': safe, 'safe_quote': quote, 'spread_within_limit': math.isfinite(spread) and 0 <= spread <= 2, 'risk_governor_clear': not risk.get('is_halted') and time.time() >= (risk.get('cooldown_until_ts') or 0)}
    signal.setdefault('checks', {}).update(safety)
    if not all(safety.values()):
        signal['action'] = 'WAIT'
        for key in ('entry_price', 'stop_loss', 'take_profit'):
            signal.pop(key, None)
    signal['next_close_ts'] = (int(time.time()) // duration + 1) * duration
    simulation = replay(hourly, duration=duration, base=base)
    stress = []
    for deviation, cost in ((1.7,13.8),(1.9,13.8),(1.8,27.6)):
        result = replay(hourly, cost_bps=cost, deviation=deviation, duration=duration, base=base)
        stress.append({'deviation': deviation, 'cost_bps': cost, 'trades': result['total_trades'], 'net_bps_sum': result['net_bps_sum']})
    return {'signal': signal, 'simulation': simulation, 'stress_tests': stress, 'generated_at': int(time.time()), 'validation': 'Exploratory sensitivity only; no out-of-sample edge established. Funding excluded.'}

# Models for request validation
class BacktestRequest(BaseModel):
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
    slip_per_leg_bps: float = 1.0
    initial_equity: float = 10000.0

class PaperTradeRequest(BaseModel):
    direction: Literal[1, -1]
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    stop_loss: float = Field(gt=0, allow_inf_nan=False)
    take_profit: float = Field(gt=0, allow_inf_nan=False)
    contracts: Optional[int] = None

class RiskCalculatorRequest(BaseModel):
    equity: float = Field(default=10000.0, gt=0, allow_inf_nan=False)
    risk_pct: float = Field(default=0.25, gt=0, le=0.25, allow_inf_nan=False)
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    stop_loss: float = Field(gt=0, allow_inf_nan=False)
    leverage: float = Field(default=2.0, gt=0, le=2, allow_inf_nan=False)

# 1. Market Data Endpoints
@router.get("/market/ticker")
def get_ticker():
    return market_data_service.get_market_state()

@router.get("/market/candles")
def get_candles(resolution: str = Query("5m", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d)$"), limit: int = 250):
    """Historical candles and modeled signals on the requested timeframe."""
    bar_seconds = timeframe_seconds(resolution)
    df = market_data_service.fetch_candles_rest(resolution=resolution, count=limit)
    if df.empty:
        df = market_data_service.candles_cache.get(resolution, pd.DataFrame())

    if df.empty:
        return {
            "resolution": resolution,
            "candles": [],
            "trend": {
                "timeframe": resolution,
                "direction": "RANGING",
                "strength": "NEUTRAL",
                "summary": "Awaiting candle data from exchange"
            }
        }

    # Calculate indicators
    d = df.sort_values('time').drop_duplicates('time').reset_index(drop=True).copy()
    close = d['close']
    d['ema_9'] = close.ewm(span=9, adjust=False).mean()
    d['ema_21'] = close.ewm(span=21, adjust=False).mean()
    d['ema_50'] = close.ewm(span=50, adjust=False).mean()
    d['ema_200'] = close.ewm(span=200, adjust=False).mean()
    
    # VWAP
    cum_vol = d['volume'].cumsum()
    cum_vol_price = (d['volume'] * (d['high'] + d['low'] + d['close']) / 3.0).cumsum()
    d['vwap'] = cum_vol_price / (cum_vol + 1e-12)

    # Bollinger Bands (20, 2)
    sma_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    d['bb_upper'] = sma_20 + (2.0 * std_20)
    d['bb_lower'] = sma_20 - (2.0 * std_20)
    d['bb_mid'] = sma_20

    # ATR 14
    prev_close = close.shift(1)
    tr = pd.concat([
        d['high'] - d['low'],
        (d['high'] - prev_close).abs(),
        (d['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    d['atr_14'] = tr.rolling(14).mean()

    # RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-12)
    d['rsi_14'] = 100 - (100 / (1 + rs))

    # Swing Highs/Lows (24 bars lookback for SBR-5 liquidity levels)
    d['prev_high_24'] = d['high'].rolling(24).max().shift(1)
    d['prev_low_24'] = d['low'].rolling(24).min().shift(1)

    # Trend calculation for this timeframe
    last_row = d.iloc[-1]
    prev_row = d.iloc[-2] if len(d) >= 2 else last_row
    
    ema9_val = float(last_row['ema_9']) if pd.notnull(last_row['ema_9']) else float(last_row['close'])
    ema21_val = float(last_row['ema_21']) if pd.notnull(last_row['ema_21']) else float(last_row['close'])
    ema50_val = float(last_row['ema_50']) if pd.notnull(last_row['ema_50']) else float(last_row['close'])
    rsi_val = float(last_row['rsi_14']) if pd.notnull(last_row['rsi_14']) else 50.0
    cur_px = float(last_row['close'])
    prev_px = float(prev_row['close'])
    mom_pct = ((cur_px / prev_px) - 1.0) * 100.0 if prev_px > 0 else 0.0

    if ema9_val > ema21_val and cur_px > ema50_val:
        trend_direction = "BULLISH"
        trend_strength = "STRONG" if rsi_val > 55 else "MODERATE"
        trend_summary = f"Bullish: Price (${cur_px:,.1f}) > EMA9 (${ema9_val:,.1f}) > EMA21 (${ema21_val:,.1f})"
    elif ema9_val < ema21_val and cur_px < ema50_val:
        trend_direction = "BEARISH"
        trend_strength = "STRONG" if rsi_val < 45 else "MODERATE"
        trend_summary = f"Bearish: Price (${cur_px:,.1f}) < EMA9 (${ema9_val:,.1f}) < EMA21 (${ema21_val:,.1f})"
    else:
        trend_direction = "RANGING"
        trend_strength = "NEUTRAL"
        trend_summary = f"Consolidating: Price oscillating between EMA9 (${ema9_val:,.1f}) and EMA21 (${ema21_val:,.1f})"

    trend_info = {
        "timeframe": resolution,
        "direction": trend_direction,
        "strength": trend_strength,
        "ema9": round(ema9_val, 1),
        "ema21": round(ema21_val, 1),
        "ema50": round(ema50_val, 1),
        "rsi": round(rsi_val, 1),
        "momentum_pct": round(mom_pct, 3),
        "summary": trend_summary
    }

    # Calculate strategy signals across historical candles (SBR-5 Sweep & Reclaim)
    try:
        cfg = BacktestConfig(
            lookback=settings.SBR5_LOOKBACK,
            vol_lookback=settings.SBR5_VOL_LOOKBACK,
            atr_lookback=settings.SBR5_ATR_LOOKBACK,
            volume_multiplier=settings.SBR5_VOLUME_MULTIPLIER,
            sweep_atr=settings.SBR5_SWEEP_ATR,
            reclaim_atr=settings.SBR5_RECLAIM_ATR,
            max_reclaim_atr=settings.SBR5_MAX_RECLAIM_ATR,
            stop_buffer_atr=settings.SBR5_STOP_BUFFER_ATR,
            target_r=settings.SBR5_TARGET_R,
            max_hold_bars=settings.SBR5_MAX_HOLD_BARS,
            tick_size=settings.TICK_SIZE,
            trend_filter=settings.SBR5_TREND_FILTER,
            momentum_enabled=settings.SCALP5_MOMENTUM_ENABLED,
            big_move_only=settings.SCALP5_BIG_MOVE_ONLY,
            resolution=resolution, context_profile=settings.SCALP5_CONTEXT_PROFILE,
        )
        sig_df = compute_sbr5_signals(d, cfg)
    except Exception:
        sig_df = d.copy()
        sig_df['long_signal'] = False
        sig_df['short_signal'] = False

    from app.strategies.alpha2_volatility import compute_alpha2_signals, alpha2_strategy
    try:
        a2_df = compute_alpha2_signals(d)
    except Exception:
        a2_df = d.copy()
        a2_df['alpha2_long'] = False
        a2_df['alpha2_short'] = False

    # Check for recorded signals from database
    db_signal_map = {}
    try:
        db_signals = get_recent_signals(limit=100)
        for s in db_signals:
            act = s.get("action")
            if act in ("BUY", "SELL"):
                c_ts = s.get("candle_timestamp") or s.get("timestamp")
                if c_ts:
                    db_signal_map[int(c_ts)] = s
    except Exception:
        pass

    candles_list = []
    passed_signals = []
    diagnostics = {"candidate_count": 0, "qualified_count": 0, "filtered_count": 0,
                   "filtered_reasons": {}}
    for idx, row in d.iterrows():
        t_val = int(row['time'])
        is_long = bool(sig_df.at[idx, 'long_signal']) if 'long_signal' in sig_df.columns and idx in sig_df.index else False
        is_short = bool(sig_df.at[idx, 'short_signal']) if 'short_signal' in sig_df.columns and idx in sig_df.index else False
        research_alpha_enabled = settings.ENABLE_RESEARCH_ALPHA2_SIGNALS and not settings.SCALP5_BIG_MOVE_ONLY
        is_a2_l = research_alpha_enabled and bool(a2_df.at[idx, 'alpha2_long']) if 'alpha2_long' in a2_df.columns and idx in a2_df.index else False
        is_a2_s = research_alpha_enabled and bool(a2_df.at[idx, 'alpha2_short']) if 'alpha2_short' in a2_df.columns and idx in a2_df.index else False

        sig_action = None
        sig_strategy = None
        sig_price = None
        sig_stop = None
        sig_target = None

        # Replayed completed-candle setups must pass
        # the same funding, trend, stop-distance and cost gates as live ones.
        # Volatility breakout takes top priority for catching explosive expansions;
        # otherwise SBR-5 / Momentum setups.
        if t_val + bar_seconds <= time.time() and (is_a2_l or is_a2_s or is_long or is_short):
            diagnostics["candidate_count"] += 1
            next_open = float(d.iloc[idx + 1]['open']) if idx + 1 < len(d) else float(row['close'])
            setup = None
            if is_long or is_short:
                setup = sbr5_strategy.evaluate(
                    d.iloc[:idx + 1],
                    {"best_bid": next_open, "best_ask": next_open, "entry_time": t_val + bar_seconds},
                    as_of=t_val + bar_seconds, resolution=resolution,
                )
            if not setup or not setup.get("is_setup"):
                if is_a2_l or is_a2_s:
                    setup = alpha2_strategy.evaluate(
                        d.iloc[:idx + 1],
                        {"best_bid": next_open, "best_ask": next_open, "entry_time": t_val + bar_seconds},
                        resolution=resolution, as_of=t_val + bar_seconds
                    )

            if setup and setup.get("is_setup"):
                diagnostics["qualified_count"] += 1
                sig_action = setup["action"]
                sig_strategy = setup["strategy"] + " (MODELED)"
                sig_price = setup["entry_price"]
                sig_stop = setup["stop_loss"]
                sig_target = setup["take_profit"]
                # Recorded setup levels take precedence for an eligible setup.
                saved = db_signal_map.get(t_val, {}) if resolution == "5m" else {}
                levels = [saved.get(k) for k in ("entry_price", "stop_loss", "take_profit")]
                if saved.get("action") == sig_action and all(
                    isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in levels
                ):
                    e, st, tp = levels
                    valid = st < e < tp if sig_action == "BUY" else tp < e < st
                    if valid:
                        sig_strategy = saved.get("strategy") or setup["strategy"]
                        sig_price, sig_stop, sig_target = levels

            else:
                diagnostics["filtered_count"] += 1
                reason = (setup or {}).get("reasons", [""])[0] if setup else "Condition not met"
                category = ("Stop distance too wide" if "Stop distance" in reason else
                            "Funding window" if "Funding snapshot" in reason else
                            "Target too small after costs" if "target ignored" in reason or "gross reward" in reason else
                            "Candle history incomplete" if "spacing" in reason or "Insufficient" in reason or "Candle history" in reason else
                            "Entry moved too far" if "Entry drift" in reason else
                            "Unsafe execution quote" if "bid/ask" in reason else
                            "Other setup checks")
                reasons = diagnostics["filtered_reasons"]
                reasons[category] = reasons.get(category, 0) + 1

        candle_item = {
            "time": t_val,
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "volume": float(row['volume']),
            "ema9": round(float(row['ema_9']), 1) if pd.notnull(row['ema_9']) else None,
            "ema21": round(float(row['ema_21']), 1) if pd.notnull(row['ema_21']) else None,
            "ema50": round(float(row['ema_50']), 1) if pd.notnull(row['ema_50']) else None,
            "ema200": round(float(row['ema_200']), 1) if pd.notnull(row['ema_200']) else None,
            "vwap": round(float(row['vwap']), 1) if pd.notnull(row['vwap']) else None,
            "bb_upper": round(float(row['bb_upper']), 1) if pd.notnull(row['bb_upper']) else None,
            "bb_lower": round(float(row['bb_lower']), 1) if pd.notnull(row['bb_lower']) else None,
            "atr": round(float(row['atr_14']), 1) if pd.notnull(row['atr_14']) else None,
            "rsi": round(float(row['rsi_14']), 1) if pd.notnull(row['rsi_14']) else None,
            "sbr_prev_high": round(float(row['prev_high_24']), 1) if pd.notnull(row['prev_high_24']) else None,
            "sbr_prev_low": round(float(row['prev_low_24']), 1) if pd.notnull(row['prev_low_24']) else None,
            "signal": sig_action,
            "signal_action": sig_action,
            "signal_strategy": sig_strategy,
            "signal_price": sig_price,
            "signal_stop": sig_stop,
            "signal_target": sig_target,
            "signal_outcome": None,
            "signal_pnl_r": None,
            "signal_exit_price": None,
            "signal_exit_bars": None,
        }
        candles_list.append(candle_item)

    # Model forward outcomes; candle OHLC cannot prove actual fills.
    for i, c_item in enumerate(candles_list):
        if not c_item.get("signal"):
            continue
        sig_act = c_item["signal"]
        direction = 1 if sig_act == "BUY" else -1
        entry_px = c_item["signal_price"] or c_item["close"]
        stop_px = c_item["signal_stop"]
        target_px = c_item["signal_target"]

        outcome = "ACTIVE"
        exit_px = None
        exit_bars = None

        max_hold = settings.SBR5_MAX_HOLD_BARS
        lookahead = candles_list[i + 1 : i + 1 + max_hold]
        cur_stop = stop_px
        risk_dist = abs(entry_px - stop_px) if stop_px else 1.0

        for step, nxt in enumerate(lookahead):
            if nxt['time'] != c_item['time'] + (step + 1) * bar_seconds:
                # Do not invent a trade outcome across unavailable bars.
                break

            # Dynamic Breakeven Ratchet (+1.0R in favorable direction -> lock entry + fee buffer)
            if direction == 1 and nxt["high"] >= entry_px + 1.0 * risk_dist:
                cur_stop = max(cur_stop, entry_px + entry_px * 0.0014)
            elif direction == -1 and nxt["low"] <= entry_px - 1.0 * risk_dist:
                cur_stop = min(cur_stop, entry_px - entry_px * 0.0014)

            # Dynamic Trailing Stop (+1.5R in favorable direction -> lock +0.75R profit)
            if direction == 1 and nxt["high"] >= entry_px + 1.5 * risk_dist:
                cur_stop = max(cur_stop, entry_px + 0.75 * risk_dist)
            elif direction == -1 and nxt["low"] <= entry_px - 1.5 * risk_dist:
                cur_stop = min(cur_stop, entry_px - 0.75 * risk_dist)

            result = resolve_bar_exit(nxt, direction, cur_stop, target_px,
                                      timeout=(step == max_hold - 1 and nxt['time'] + bar_seconds <= time.time()))
            if result is not None:
                exit_px, outcome_raw = result
                outcome = "BREAKEVEN_WIN" if outcome_raw == "STOP_HIT" and (direction * (exit_px - entry_px) > 0) else outcome_raw
                exit_bars = step + 1
                break

        pnl_r = None
        if exit_px is not None and stop_px:
            # Entry includes modeled entry slippage. Apply exit slippage and
            # both taker fees; R is net P&L divided by initial price risk.
            filled_exit = exit_px * (1 - direction * settings.DEFAULT_SLIP_PER_LEG_BPS / 10000)
            fees = (entry_px + filled_exit) * settings.FEE_TAKER_BPS / 10000 * settings.GST_MULTIPLIER
            risk_dist = abs(entry_px - stop_px)
            pnl_r = round((direction * (filled_exit - entry_px) - fees) / risk_dist, 2) if risk_dist else None
            exit_px = round(filled_exit, 1)

        c_item["signal_outcome"] = outcome
        c_item["signal_pnl_r"] = pnl_r
        c_item["signal_exit_price"] = exit_px
        c_item["signal_exit_bars"] = exit_bars

        passed_signals.append({
            "time": c_item["time"],
            "action": c_item["signal_action"],
            "strategy": c_item["signal_strategy"],
            "price": c_item["signal_price"],
            "stop_loss": c_item["signal_stop"],
            "take_profit": c_item["signal_target"],
            "outcome": outcome,
            "pnl_r": pnl_r,
            "exit_price": exit_px,
            "exit_bars": exit_bars,
        })

    return {
        "resolution": resolution,
        "count": len(candles_list),
        "candles": candles_list,
        "trend": trend_info,
        "passed_signals": passed_signals,
        "signal_diagnostics": diagnostics,
    }

@router.get("/market/trends")
def get_multi_timeframe_trends():
    """Computes instant trend direction across all 8 standard timeframes."""
    resolutions = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]
    trends = {}
    for res in resolutions:
        df = market_data_service.candles_cache.get(res, pd.DataFrame())
        if df.empty or len(df) < 25:
            df = market_data_service.fetch_candles_rest(resolution=res, count=100)
        
        if df.empty or len(df) < 5:
            trends[res] = {"direction": "RANGING", "rsi": 50.0, "status": "NO_DATA"}
            continue
            
        c = df['close']
        ema9 = c.ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = c.ewm(span=21, adjust=False).mean().iloc[-1]
        last_p = c.iloc[-1]
        
        # RSI 14
        delta = c.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-12)))) if loss > 0 else 50.0
        
        if ema9 > ema21 and last_p > ema21:
            dir_label = "BULLISH"
        elif ema9 < ema21 and last_p < ema21:
            dir_label = "BEARISH"
        else:
            dir_label = "RANGING"
            
        trends[res] = {
            "timeframe": res,
            "direction": dir_label,
            "ema9": round(float(ema9), 1),
            "ema21": round(float(ema21), 1),
            "rsi": round(float(rsi), 1),
            "last_price": round(float(last_p), 1)
        }
    return trends

@router.get("/market/orderbook")
def get_orderbook():
    state = market_data_service.get_market_state()
    return {
        "symbol": state["symbol"],
        "last_price": state["last_price"],
        "spread": state["spread"],
        "spread_bps": state["spread_bps"],
        "bids": state["bids"],
        "asks": state["asks"],
        "order_flow_imbalance": state["order_flow_imbalance"],
        "trade_flow_imbalance": state["trade_flow_imbalance"],
        "weighted_mid": state["weighted_mid"],
        "micro_price_dev": state["micro_price_dev"]
    }

# 2. Strategy Signals
@router.get("/signals/current")
def get_current_signal(resolution: str = Query("5m", pattern="^(1m|3m|5m|15m|30m|1h|4h|1d)$")):
    # Also support direct internal calls without a FastAPI dependency wrapper.
    if not isinstance(resolution, str):
        resolution = "5m"
    bar_seconds = timeframe_seconds(resolution)
    m_state = market_data_service.get_market_state()
    engine = decision_engine if resolution == "5m" else timeframe_engines[resolution]
    if resolution == "5m":
        candles = market_data_service.candles_5m
    else:
        candles = market_data_service.fetch_candles_rest(resolution=resolution, count=250)
        if candles.empty:
            candles = market_data_service.candles_cache.get(resolution, pd.DataFrame())
    if candles is not None and not candles.empty:
        candles = candles.sort_values('time').drop_duplicates('time')
        candles = candles[candles['time'] + bar_seconds <= time.time()]
        if not candles.empty and time.time() - float(candles.iloc[-1]['time']) > 2 * bar_seconds:
            return {"action": "WAIT / NO TRADE", "direction": 0, "strategy": "DATA SAFETY",
                    "resolution": resolution, "bar_seconds": bar_seconds,
                    "status": "STALE_CANDLES", "timestamp": int(time.time()),
                    "max_hold_bars": settings.SBR5_MAX_HOLD_BARS,
                    "max_hold_seconds": settings.SBR5_MAX_HOLD_BARS * bar_seconds,
                    "reasons": [f"Waiting for fresh completed {resolution} candles"],
                    "invalidation_risks": ["Selected-timeframe candle history is stale"]}
    return engine.evaluate(candles, m_state)

@router.get("/signals/history")
def get_signals_history(limit: int = 50):
    return get_recent_signals(limit=limit)

# 3. AI Predictions
@router.get("/predictions")
def get_predictions():
    df_5m = market_data_service.candles_5m
    last_price = market_data_service.last_price
    return prediction_engine.generate_predictions(df_5m, last_price)

@router.post("/predictions/retrain")
def retrain_predictions():
    df_5m = market_data_service.candles_5m
    if df_5m.empty:
        df_5m = market_data_service.fetch_candles_rest("5m", count=400)
    result = prediction_engine.train_models(df_5m)
    return result

# 4. Strategy Lab
@router.get("/strategies")
def get_strategies_status():
    m_state = market_data_service.get_market_state()
    df_5m = market_data_service.candles_5m
    
    a1 = alpha1_strategy.evaluate(m_state)
    a2 = alpha2_strategy.evaluate(df_5m, m_state)
    a3 = alpha3_strategy.evaluate(m_state)
    is_safe, msg, det = alpha4_dislocation.evaluate(df_5m, m_state)
    
    return {
        "alpha1_orderflow": a1,
        "alpha2_breakout": a2,
        "alpha3_basis": a3,
        "alpha4_dislocation": {
            "name": alpha4_dislocation.name,
            "is_safe": is_safe,
            "status": msg,
            "details": det
        },
        "alpha5_sbr5": {
            "name": "ALPHA-5: SBR-5 SWEEP & RECLAIM",
            "status": "PRIMARY ACTIVE RESEARCH STRATEGY",
            "parameters": {
                "lookback": settings.SBR5_LOOKBACK,
                "atr_lookback": settings.SBR5_ATR_LOOKBACK,
                "vol_multiplier": settings.SBR5_VOLUME_MULTIPLIER,
                "sweep_atr": settings.SBR5_SWEEP_ATR,
                "reclaim_min_atr": settings.SBR5_RECLAIM_ATR,
                "reclaim_max_atr": settings.SBR5_MAX_RECLAIM_ATR,
                "target_r": settings.SBR5_TARGET_R,
                "max_hold_bars": settings.SBR5_MAX_HOLD_BARS,
                "big_move_only": settings.SCALP5_BIG_MOVE_ONLY,
                "min_stop_pct": settings.SBR5_MIN_STOP_FRACTION * 100,
                "max_stop_pct": settings.SBR5_MAX_STOP_FRACTION * 100
            }
        }
    }

# 5. Paper Trading
@router.get("/paper-trade/portfolio")
def get_paper_portfolio():
    return paper_trading_service.get_portfolio_summary()

@router.post("/paper-trade/order")
def place_paper_order(req: PaperTradeRequest):
    m_state = market_data_service.get_market_state()
    sig = {
        "direction": req.direction,
        "entry_price": req.entry_price,
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit
    }
    trade = paper_trading_service.execute_signal(sig, m_state)
    if not trade:
        raise HTTPException(status_code=400, detail="Paper order rejected: Check risk limits, account halt, or existing open position.")
    return trade

# 6. Backtesting
@router.post("/backtest/run")
def run_backtest_endpoint(req: BacktestRequest):
    # Fetch historical candles for backtest
    df = market_data_service.candles_5m
    if df.empty or len(df) < 150:
        df = market_data_service.fetch_candles_rest("5m", count=1000)

    if df.empty or len(df) < 50:
        raise HTTPException(status_code=400, detail="Insufficient historical candles from exchange. Please retry.")

    cfg = BacktestConfig(
        lookback=req.lookback,
        vol_lookback=req.vol_lookback,
        atr_lookback=req.atr_lookback,
        volume_multiplier=req.volume_multiplier,
        sweep_atr=req.sweep_atr,
        reclaim_atr=req.reclaim_atr,
        max_reclaim_atr=req.max_reclaim_atr,
        stop_buffer_atr=req.stop_buffer_atr,
        target_r=req.target_r,
        max_hold_bars=req.max_hold_bars,
        slip_per_leg_bps=req.slip_per_leg_bps
    )
    res = run_sbr5_backtest(df, cfg, initial_equity=req.initial_equity)
    return res

# 7. Risk Center & Contract Calculator
@router.get("/risk/status")
def get_risk_status():
    r_state = get_risk_state()
    m_state = market_data_service.get_market_state()
    return {
        "risk_governor": {
            "is_halted": bool(r_state.get("is_halted")),
            "halt_reason": r_state.get("halt_reason", ""),
            "daily_loss_limit_pct": settings.DAILY_LOSS_LIMIT_FRACTION * 100,
            "peak_drawdown_limit_pct": settings.PEAK_DRAWDOWN_KILL_FRACTION * 100,
            "max_consecutive_losses": settings.MAX_CONSECUTIVE_LOSSES,
            "current_losing_streak": r_state.get("losing_streak", 0),
            "cooldown_until_ts": r_state.get("cooldown_until_ts", 0),
            "cooldown_remaining_sec": max(0, int(r_state.get("cooldown_until_ts", 0) - time.time()))
        },
        "funding_safety": {
            "next_funding_countdown_sec": m_state.get("next_funding_countdown_sec", 0),
            "funding_rate_pct": m_state.get("funding_rate_pct", 0),
            "is_funding_window_safe": m_state.get("next_funding_countdown_sec", 0) > (settings.SBR5_MAX_HOLD_BARS * 300 + settings.FUNDING_BUFFER_SEC)
        },
        "contract_spec": {
            "symbol": settings.SYMBOL,
            "contract_size_btc": settings.CONTRACT_SIZE,
            "tick_size_usd": settings.TICK_SIZE,
            "fee_taker_bps": settings.FEE_TAKER_BPS,
            "fee_maker_bps": settings.FEE_MAKER_BPS,
            "gst_pct": 18.0,
            "roundtrip_taker_fee_bps": settings.ROUNDTRIP_TAKER_FEE_BPS,
            "default_slippage_bps": settings.DEFAULT_SLIP_PER_LEG_BPS * 2
        }
    }

@router.post("/risk/calculate")
def calculate_risk(req: RiskCalculatorRequest):
    """Accurate contract sizing calculator for Delta Exchange India BTCUSD."""
    risk_usd = req.equity * (req.risk_pct / 100.0)
    stop_dist = abs(req.entry_price - req.stop_loss)
    stop_dist_frac = stop_dist / req.entry_price if req.entry_price > 0 else 0.0

    # Two-leg taker fees + slippage
    two_leg_fee_frac = 2 * (settings.FEE_TAKER_BPS / 10000.0) * settings.GST_MULTIPLIER
    two_leg_slip_frac = 2 * (settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0)
    total_cost_frac = two_leg_fee_frac + two_leg_slip_frac

    total_risk_frac_per_notional = stop_dist_frac + total_cost_frac
    max_notional_usd = min(risk_usd / total_risk_frac_per_notional, req.equity * req.leverage)
    
    # Lot size is 0.001 BTC
    lot_notional = req.entry_price * settings.CONTRACT_SIZE
    contracts = math.floor(max_notional_usd / lot_notional) if lot_notional > 0 else 0
    actual_notional_usd = contracts * lot_notional

    est_loss_at_stop = actual_notional_usd * stop_dist_frac
    est_fees_usd = actual_notional_usd * two_leg_fee_frac
    est_slippage_usd = actual_notional_usd * two_leg_slip_frac
    est_total_loss_usd = est_loss_at_stop + est_fees_usd + est_slippage_usd

    # Assuming 1.8R target
    target_price = req.entry_price + (1.8 * stop_dist if req.entry_price > req.stop_loss else -1.8 * stop_dist)
    gross_gain_usd = actual_notional_usd * (1.8 * stop_dist_frac)
    net_profit_usd = gross_gain_usd - est_fees_usd - est_slippage_usd
    net_rr = net_profit_usd / est_total_loss_usd if est_total_loss_usd > 0 else 0.0

    return {
        "contracts": contracts,
        "contract_size_btc": settings.CONTRACT_SIZE,
        "notional_usd": round(actual_notional_usd, 2),
        "btc_exposure": round(contracts * settings.CONTRACT_SIZE, 4),
        "estimated_loss_at_stop_usd": round(est_loss_at_stop, 2),
        "estimated_fees_usd": round(est_fees_usd, 2),
        "estimated_slippage_usd": round(est_slippage_usd, 2),
        "total_risk_at_stop_usd": round(est_total_loss_usd, 2),
        "total_risk_equity_pct": round((est_total_loss_usd / req.equity) * 100.0, 3),
        "target_price": round(target_price, 1),
        "estimated_net_profit_at_target_usd": round(net_profit_usd, 2),
        "net_reward_to_risk": round(net_rr, 2)
    }

# 8. Alerts & Engine Control
@router.post("/engine/toggle")
def toggle_engine():
    r_state = get_risk_state()
    if r_state.get("is_halted") and r_state.get("halt_reason") != "Manually paused by user":
        raise HTTPException(status_code=409, detail="Risk halt cannot be cleared by engine toggle")
    is_halted = 0 if r_state.get("is_halted") else 1
    halt_reason = "Manually paused by user" if is_halted else ""
    update_risk_state(
        equity=r_state.get("equity", 10000.0),
        losing_streak=r_state.get("losing_streak", 0),
        cooldown_until_ts=r_state.get("cooldown_until_ts", 0),
        is_halted=is_halted,
        halt_reason=halt_reason
    )
    insert_alert("ENGINE", f"Engine state changed: {'PAUSED' if is_halted else 'ACTIVE'}", "INFO")
    return {"is_halted": bool(is_halted), "status": "PAUSED" if is_halted else "RUNNING"}

@router.get("/alerts")
def get_alerts(limit: int = 50):
    return get_recent_alerts(limit=limit)
