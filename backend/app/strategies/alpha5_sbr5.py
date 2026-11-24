import math
import time
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from app.config import settings
from app.timeframes import timeframe_seconds
from app.strategies.engine_safety import completed_history, executable_quote, maximum_stop_fraction
from app.strategies.sbr_filters import opposing_trend_masks
from app.strategies.momentum5 import momentum_candidates
from app.strategies.big_move import BIG_MOVE_POLICY, substantial_target

def funding_in_window(entry_unix_s: int, holding_bars: int = 5, buffer_sec: int = 120, bar_seconds: int = 300) -> bool:
    """Conservatively check if a funding snapshot lies in entry..holding window."""
    funding_sec = settings.FUNDING_INTERVAL_SEC
    bars_sec = bar_seconds
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

    def evaluate(self, df: pd.DataFrame, current_market: Dict[str, Any], *, as_of: Optional[float] = None, resolution: str = "5m", context_profile: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate only completed bars of the requested timeframe."""
        bar_seconds = timeframe_seconds(resolution)
        hold_seconds = self.max_hold_bars * bar_seconds
        hold_label = f"{hold_seconds // 60} minutes" if hold_seconds < 3600 else f"{hold_seconds / 3600:g} hours"
        min_bars = max(self.lookback, self.vol_lookback, self.atr_lookback) + 2
        if df is None or len(df) < min_bars:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Insufficient completed {resolution} candles: have {len(df) if df is not None else 0}, need >= {min_bars}"],
                "invalidation_risks": ["Historical context building"],
                "is_setup": False
            }

        try:
            d = completed_history(df, bar_seconds, time.time() if as_of is None else as_of)
        except ValueError as exc:
            return {"action": "WAIT", "direction": 0, "strategy": self.name,
                    "is_setup": False, "reasons": [str(exc)],
                    "invalidation_risks": ["Invalid candle data; setup cannot be trusted"]}
        if len(d) < min_bars:
            return {"is_setup": False, "reasons": ["Awaiting completed candles"]}
        if not d['time'].tail(min_bars).diff().dropna().eq(bar_seconds).all():
            return {"action": "WAIT", "direction": 0, "strategy": self.name,
                    "is_setup": False,
                    "reasons": [f"Waiting for consecutive {resolution} candles; history has gaps or incompatible spacing"],
                    "invalidation_risks": ["Unreliable selected-timeframe history"]}
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

        if settings.SCALP5_BIG_MOVE_ONLY:
            long_cond = short_cond = False
        direction = 1 if long_cond else (-1 if short_cond else 0)
        momentum_kind = None
        if settings.SCALP5_MOMENTUM_ENABLED:
            momentum = momentum_candidates(d, d['atr_prior'], d['vol_prior'],
                                           big_move_only=settings.SCALP5_BIG_MOVE_ONLY,
                                           context_profile=context_profile or settings.SCALP5_CONTEXT_PROFILE).iloc[-1]
            if momentum['momentum_long'] or momentum['momentum_short']:
                direction = 1 if momentum['momentum_long'] else -1
                momentum_kind = momentum['momentum_kind']

        if direction and momentum_kind is None and settings.SBR5_TREND_FILTER:
            block_long, block_short = opposing_trend_masks(d, d['atr_prior'])
            if bool(block_long.iloc[-1] if direction == 1 else block_short.iloc[-1]):
                return {
                    "action": "WAIT", "direction": 0, "strategy": self.name,
                    "candle_time": t, "is_setup": False,
                    "reasons": ["Sweep/reclaim blocked: established opposing EMA9/21/50 trend with EMA21 momentum"],
                    "invalidation_risks": ["Countertrend reversal may fail while momentum persists"],
                }
        
        if direction == 0:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "candle_time": t,
                "reasons": [
                    ("Big-move mode: waiting for at least 0.35% directional movement over 3 completed bars, a 1 ATR / 0.15% body, 1.75x volume and efficient momentum"
                     if settings.SCALP5_BIG_MOVE_ONLY else
                     f"No confirmed sweep/reclaim, momentum breakout or pullback continuation (close ${c_close:.1f})"),
                    f"Volume: {c_vol:.1f} vs required {(BIG_MOVE_POLICY.min_volume_ratio if settings.SCALP5_BIG_MOVE_ONLY else self.vol_multiplier) * vol_prior:.1f} (Ratio: {c_vol/vol_prior if vol_prior > 0 else 0:.2f}x)",
                    f"Current ATR14: ${atr:.1f}"
                ],
                "invalidation_risks": ["Market in normal range oscillation"],
                "is_setup": False
            }

        # We have a candidate setup! Now calculate executable price, stop, target, and risk gates.
        try:
            best_bid, best_ask = executable_quote(current_market, c_close)
        except ValueError as exc:
            return {"action": "WAIT", "direction": 0, "strategy": self.name,
                    "is_setup": False, "reasons": [str(exc)],
                    "invalidation_risks": ["Unsafe executable quote"]}
        quote = best_ask if direction == 1 else best_bid
        deviation = abs(quote / c_close - 1)
        if deviation > settings.MAX_ENTRY_DEVIATION_FRACTION:
            return {"action": "WAIT", "direction": 0, "strategy": self.name,
                    "is_setup": False,
                    "reasons": [f"Entry drift {deviation*100:.3f}% exceeds {settings.MAX_ENTRY_DEVIATION_FRACTION*100:.2f}% limit; do not chase"],
                    "invalidation_risks": ["Signal price has moved before executable entry"]}
        slip = settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0

        # Modeled entry is next available executable ask for long, bid for short
        entry = (best_ask if direction == 1 else best_bid) * (1 + direction * slip)
        
        # Funding safety gate: check next bar entry timestamp against funding snapshots
        entry_ts = int(current_market.get("entry_time", t + bar_seconds))
        # A hold spanning a full funding interval cannot avoid every snapshot.
        # Disclose funding exposure instead of permanently blocking daily bars
        # whose closes coincide with scheduled funding snapshots.
        funding_exposure = hold_seconds >= settings.FUNDING_INTERVAL_SEC - 2 * settings.FUNDING_BUFFER_SEC
        funding_bars = 0 if funding_exposure else self.max_hold_bars
        if not funding_exposure and funding_in_window(entry_ts, funding_bars, settings.FUNDING_BUFFER_SEC, bar_seconds):
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Funding snapshot within the {hold_label} holding window or entry buffer; setup gated"],
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
        max_stop_frac = maximum_stop_fraction(bar_seconds, atr, entry, self.max_stop_frac)
        if stop_dist_frac > max_stop_frac:
            return {
                "action": "WAIT",
                "direction": 0,
                "strategy": self.name,
                "reasons": [f"Stop distance {stop_dist_frac*100:.2f}% exceeds maximum allowed limit {max_stop_frac*100:.2f}% for {resolution}"],
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

        if settings.SCALP5_BIG_MOVE_ONLY and not substantial_target(gross_reward_bps / 10000, total_costs_bps / 10000):
            return {
                "action": "WAIT", "direction": 0, "strategy": "BIG MOVE ONLY",
                "is_setup": False,
                "reasons": [f"Small target ignored: gross {gross_reward_bps:.1f} bps, net {net_reward_bps:.1f} bps; require at least 50 bps gross, 35 bps net and 3x execution costs"],
                "invalidation_risks": ["Insufficient projected movement after costs"],
            }

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
            f"Stop distance {stop_dist_frac*100:.2f}% is within {self.min_stop_frac*100:.2f}% - {max_stop_frac*100:.2f}% bounds for {resolution}",
            f"Net reward ({net_reward_bps:.1f} bps) clears conservative 2-leg taker fee & slippage ({total_costs_bps:.1f} bps)"
        ]

        if momentum_kind:
            reasons[:2] = [
                f"Completed {resolution} momentum {momentum_kind.lower()} confirmed in {'bullish' if direction == 1 else 'bearish'} direction",
                "Directional candle body, close location and relative volume confirmed; no future candles used",
            ]
        strategy_name = f"ALPHA-5: MOMENTUM {momentum_kind}" if momentum_kind else self.name
        if settings.SCALP5_BIG_MOVE_ONLY:
            strategy_name += " — BIG MOVE ONLY"
            reasons.append(f"Big-move filter passed: >= {BIG_MOVE_POLICY.min_volume_ratio:.2f}x volume and >= {100 * BIG_MOVE_POLICY.min_move_fraction:.2f}% directional movement; small setups ignored")

        risks = [
            "Signal expires if executable price deviates > 0.10% from modeled entry",
            f"Maximum holding period: {hold_label} ({self.max_hold_bars} {resolution} candles)",
            "Stop loss gap risk exists during extreme market jumps",
            "Historical bar-level backtest does not guarantee live execution fills"
        ]

        if funding_exposure:
            risks.append("Holding window crosses funding snapshots; displayed net target excludes future funding charges")

        return {
            "resolution": resolution,
            "bar_seconds": bar_seconds,
            "max_hold_bars": self.max_hold_bars,
            "max_hold_seconds": hold_seconds,
            "funding_exposure": funding_exposure,
            "context_profile": context_profile or settings.SCALP5_CONTEXT_PROFILE,
            "max_stop_fraction": max_stop_frac,
            "action": action,
            "direction": direction,
            "strategy": strategy_name,
            "entry_price": round(entry, 1),
            "stop_loss": round(stop, 1),
            "take_profit": round(target, 1),
            "risk_reward": round(net_rr, 2),
            "gross_reward_bps": round(gross_reward_bps, 1),
            "estimated_fees_bps": round(fee_fraction * 10000.0, 1),
            "estimated_slippage_bps": round(slip_fraction * 10000.0, 1),
            "net_reward_bps": round(net_reward_bps, 1),
            "candle_timestamp": t,
            "valid_until_ts": t + bar_seconds + min(120, bar_seconds),  # At most one entry candle
            "reasons": reasons,
            "invalidation_risks": risks,
            "is_setup": True
        }

sbr5_strategy = Alpha5SBR5()
