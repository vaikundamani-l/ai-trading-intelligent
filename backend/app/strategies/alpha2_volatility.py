import math
import time
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from app.config import settings

def funding_in_window(entry_unix_s: int, holding_bars: int = 6, buffer_sec: int = 120) -> bool:
    """Conservatively check if a funding snapshot lies in entry..holding window."""
    funding_sec = settings.FUNDING_INTERVAL_SEC
    bars_sec = 300  # 5 minutes
    left = entry_unix_s - buffer_sec
    right = entry_unix_s + holding_bars * bars_sec + buffer_sec
    next_snapshot = ((left - 1) // funding_sec + 1) * funding_sec
    return next_snapshot <= right

def compute_alpha2_signals(
    df: pd.DataFrame,
    compression_threshold: float = 0.75,
    vol_multiplier: float = 1.20,
    lookback: int = 12
) -> pd.DataFrame:
    """Vectorized calculation of Volatility Compression Breakouts across candles.
    Catches explosive directional moves after range contractions.
    """
    d = df.copy()
    if len(d) < 55:
        d['alpha2_long'] = False
        d['alpha2_short'] = False
        d['vcr'] = np.nan
        d['atr_prior'] = np.nan
        return d

    d['log_ret'] = np.log(d['close'] / d['close'].shift(1))
    rv_6 = d['log_ret'].rolling(6).std()
    rv_med = rv_6.rolling(48).median().shift(1)
    d['vcr'] = (rv_6 / (rv_med + 1e-12)).shift(1)

    prev_close = d['close'].shift(1)
    tr = pd.concat([
        d['high'] - d['low'],
        (d['high'] - prev_close).abs(),
        (d['low'] - prev_close).abs()
    ], axis=1).max(axis=1)
    d['atr_prior'] = tr.rolling(14).mean().shift(1)
    d['high_12'] = d['high'].rolling(lookback).max().shift(1)
    d['low_12'] = d['low'].rolling(lookback).min().shift(1)
    d['vol_prior'] = d['volume'].rolling(24).mean().shift(1)

    # Volatility was compressed recently (in current or prior bar)
    is_compressed = (d['vcr'] < compression_threshold) | (d['vcr'].shift(1) < compression_threshold)
    breakout_dist = np.maximum(0.20 * d['atr_prior'], 2.0 * settings.TICK_SIZE)
    vol_ok = d['volume'] >= vol_multiplier * d['vol_prior']

    d['alpha2_long'] = (
        is_compressed &
        (d['close'] > d['high_12'] + breakout_dist) &
        vol_ok &
        (d['close'] > d['open'])
    ).fillna(False)

    d['alpha2_short'] = (
        is_compressed &
        (d['close'] < d['low_12'] - breakout_dist) &
        vol_ok &
        (d['close'] < d['open'])
    ).fillna(False)

    return d


class Alpha2RVolatilityBreakout:
    """ALPHA-2: High-Momentum Volatility Compression Breakout.
    Engineered to capture major directional expansions ('high up or down')
    following volatility coiling cycles on Bitcoin perpetual contracts.
    """
    def __init__(self):
        self.name = "ALPHA-2: VOLATILITY BREAKOUT"
        self.status = "ACTIVE"
        self.compression_threshold = 0.75
        self.vcr_short_window = 6
        self.vcr_long_window = 48
        self.breakout_lookback = 12
        self.atr_lookback = 14
        self.vol_lookback = 24
        self.target_r = 2.20           # 2.2R target to ride high moves
        self.min_stop_frac = 0.0020    # 20 bps min stop
        self.max_stop_frac = 0.0120    # 1.20% max stop
        self.max_hold_bars = settings.SBR5_MAX_HOLD_BARS
        self.tick_size = settings.TICK_SIZE

    def evaluate(self, df: pd.DataFrame, market_state: Dict[str, Any], resolution: str = "5m", as_of: Optional[float] = None) -> Dict[str, Any]:
        min_bars = self.vcr_long_window + self.vcr_short_window + 5
        if df is None or len(df) < min_bars:
            return {
                "strategy": self.name,
                "status": "INITIALIZING",
                "action": "WAIT",
                "direction": 0,
                "is_setup": False,
                "reasons": [f"Insufficient bars for VCR calculation ({len(df) if df is not None else 0}/{min_bars})"]
            }

        from app.timeframes import timeframe_seconds
        bar_seconds = timeframe_seconds(resolution)
        current_time = as_of if as_of is not None else time.time()
        d = df[df["time"] + bar_seconds <= current_time].copy() if "time" in df.columns else df.copy()
        if len(d) < min_bars:
            return {"strategy": self.name, "action": "WAIT", "direction": 0, "is_setup": False, "reasons": ["Awaiting completed candles"]}

        sig_df = compute_alpha2_signals(
            d,
            compression_threshold=self.compression_threshold,
            vol_multiplier=1.20,
            lookback=self.breakout_lookback
        )

        last_bar = sig_df.iloc[-1]
        t = int(last_bar['time']) if 'time' in last_bar else int(time.time())
        vcr = float(last_bar['vcr']) if pd.notnull(last_bar['vcr']) else 1.0
        atr = float(last_bar['atr_prior']) if pd.notnull(last_bar['atr_prior']) else 50.0
        h12 = float(last_bar['high_12']) if pd.notnull(last_bar['high_12']) else float(last_bar['high'])
        l12 = float(last_bar['low_12']) if pd.notnull(last_bar['low_12']) else float(last_bar['low'])
        c_close = float(last_bar['close'])
        c_low = float(last_bar['low'])
        c_high = float(last_bar['high'])
        c_vol = float(last_bar['volume'])
        vol_prior = float(last_bar['vol_prior']) if pd.notnull(last_bar['vol_prior']) else c_vol
        spread = float(market_state.get("spread", 0.5) or 0.5)

        long_breakout = bool(last_bar['alpha2_long'])
        short_breakout = bool(last_bar['alpha2_short'])

        direction = 1 if long_breakout else (-1 if short_breakout else 0)

        if direction == 0:
            return {
                "strategy": self.name,
                "status": self.status,
                "action": "WAIT",
                "direction": 0,
                "is_setup": False,
                "vcr": round(vcr, 3),
                "reasons": [
                    f"Volatility Compression: VCR={vcr:.2f} (Threshold < {self.compression_threshold:.2f})",
                    f"12-bar Range: [${l12:.1f} - ${h12:.1f}]",
                    f"Awaiting decisive breakout through 12-bar channel with volume impulse"
                ],
                "invalidation_risks": ["Normal range fluctuation"]
            }

        # Executable price modeling
        best_bid = float(market_state.get("best_bid", c_close) or c_close)
        best_ask = float(market_state.get("best_ask", c_close) or c_close)
        slip = settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0
        entry = (best_ask if direction == 1 else best_bid) * (1.0 + direction * slip)

        # Funding snapshot check
        if funding_in_window(int(time.time()), self.max_hold_bars, settings.FUNDING_BUFFER_SEC):
            return {
                "strategy": self.name,
                "action": "WAIT",
                "direction": 0,
                "is_setup": False,
                "reasons": ["Scheduled 8h funding snapshot within holding window; trade blocked for funding safety"]
            }

        # Stop loss calculation: Placed at channel midline / recent swing extreme with ATR buffer
        if direction == 1:
            channel_mid = (h12 + l12) / 2.0
            raw_stop = max(channel_mid, c_low - 0.20 * atr)
            stop = min(raw_stop, entry * (1.0 - self.min_stop_frac))
            stop = math.floor(stop / self.tick_size) * self.tick_size
        else:
            channel_mid = (h12 + l12) / 2.0
            raw_stop = min(channel_mid, c_high + 0.20 * atr)
            stop = max(raw_stop, entry * (1.0 + self.min_stop_frac))
            stop = math.ceil(stop / self.tick_size) * self.tick_size

        risk_move = direction * (entry - stop)
        if risk_move <= 0:
            return {"strategy": self.name, "action": "WAIT", "direction": 0, "is_setup": False, "reasons": ["Invalid stop distance"]}

        stop_dist_frac = risk_move / entry
        if stop_dist_frac > self.max_stop_frac:
            return {
                "strategy": self.name,
                "action": "WAIT",
                "direction": 0,
                "is_setup": False,
                "reasons": [f"Breakout stop distance {stop_dist_frac*100:.2f}% exceeds {self.max_stop_frac*100:.2f}% max allowed limit"]
            }

        # Target calculation (2.2R for strong high up/down trend ride)
        target = entry + direction * self.target_r * risk_move
        target = (math.ceil(target / self.tick_size) * self.tick_size if direction == 1
                  else math.floor(target / self.tick_size) * self.tick_size)

        # Fee & Net Edge calculation
        fee_fraction = 2.0 * (settings.FEE_TAKER_BPS / 10000.0) * settings.GST_MULTIPLIER
        slip_fraction = 2.0 * slip
        total_costs_bps = (fee_fraction + slip_fraction) * 10000.0
        gross_reward_bps = (abs(target - entry) / entry) * 10000.0
        net_reward_bps = gross_reward_bps - total_costs_bps
        risk_bps = (risk_move / entry) * 10000.0
        net_rr = net_reward_bps / (risk_bps + total_costs_bps) if (risk_bps + total_costs_bps) > 0 else 0.0

        if net_reward_bps <= total_costs_bps:
            return {"strategy": self.name, "action": "WAIT", "direction": 0, "is_setup": False, "reasons": ["Gross reward does not clear taker fees"]}

        action = "BUY" if direction == 1 else "SELL"
        reasons = [
            f"Volatility Compression confirmed: VCR={vcr:.2f} (< {self.compression_threshold:.2f} threshold)",
            f"12-bar {'channel high break' if direction == 1 else 'channel low breakdown'}: Close ${c_close:.1f} vs [${l12:.1f} - ${h12:.1f}]",
            f"Volume impulse surge: {c_vol:.1f} ({c_vol/vol_prior:.2f}x prior 24-bar mean)",
            f"Asymmetric Target: 2.2R target (${target:.1f}) offers {net_reward_bps:.1f} bps net reward",
            "Breakeven ratchet active: Stop moves to Entry + fees once +1.0R is achieved"
        ]

        risks = [
            "Breakout pullbacks can retest channel boundary before secondary impulse",
            f"Maximum holding period: {self.max_hold_bars * 5}m ({self.max_hold_bars} candles)",
            "Stop loss gap risk exists during extreme slippage/jump events"
        ]

        return {
            "resolution": resolution,
            "bar_seconds": bar_seconds,
            "max_hold_bars": self.max_hold_bars,
            "max_hold_seconds": self.max_hold_bars * bar_seconds,
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
            "valid_until_ts": t + 300 + 120,
            "reasons": reasons,
            "invalidation_risks": risks,
            "is_setup": True,
            "status": "ACTIVE_SETUP",
            "trail_after_r": 1.0,
            "breakeven_lock": True
        }

alpha2_strategy = Alpha2RVolatilityBreakout()
