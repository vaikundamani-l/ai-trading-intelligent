import math
from typing import Dict, Any
import pandas as pd
import numpy as np

from app.config import settings

class Alpha2RVolatilityBreakout:
    """ALPHA-2R: Corrected Volatility Compression Breakout.
    Status: RESEARCH ONLY.
    Requires absolute breakout distance in ATR, spread, and ticks.
    """
    def __init__(self):
        self.name = "ALPHA-2R: VOLATILITY COMPRESSION BREAKOUT"
        self.status = "RESEARCH ONLY"
        self.compression_threshold = 0.65
        self.vcr_short_window = 6
        self.vcr_long_window = 48
        self.breakout_lookback = 12
        self.atr_lookback = 14
        self.vol_lookback = 24

    def evaluate(self, df: pd.DataFrame, market_state: Dict[str, Any]) -> Dict[str, Any]:
        min_bars = self.vcr_long_window + self.vcr_short_window + 5
        if df is None or len(df) < min_bars:
            return {
                "strategy": self.name,
                "status": self.status,
                "action": "WAIT",
                "is_setup": False,
                "reasons": [f"Insufficient bars for VCR calculation ({len(df) if df is not None else 0}/{min_bars})"]
            }

        d = df.copy()
        d['log_ret'] = np.log(d['close'] / d['close'].shift(1))
        
        # Realized Volatility over 6 bars
        rv_6 = d['log_ret'].rolling(self.vcr_short_window).std()
        # Median RV over prior 48 bars
        rv_median = rv_6.rolling(self.vcr_long_window).median().shift(1)
        
        # Compression ratio
        d['vcr'] = (rv_6 / (rv_median + 1e-12)).shift(1)
        
        # ATR 14
        prev_close = d['close'].shift(1)
        true_range = pd.concat([
            d['high'] - d['low'],
            (d['high'] - prev_close).abs(),
            (d['low'] - prev_close).abs()
        ], axis=1).max(axis=1)
        d['atr_prior'] = true_range.rolling(self.atr_lookback).mean().shift(1)
        d['high_12'] = d['high'].rolling(self.breakout_lookback).max().shift(1)
        d['low_12'] = d['low'].rolling(self.breakout_lookback).min().shift(1)
        d['vol_prior'] = d['volume'].rolling(self.vol_lookback).mean().shift(1)

        last_bar = d.iloc[-1]
        vcr = float(last_bar['vcr'])
        atr = float(last_bar['atr_prior'])
        h12 = float(last_bar['high_12'])
        l12 = float(last_bar['low_12'])
        c_close = float(last_bar['close'])
        c_vol = float(last_bar['volume'])
        vol_prior = float(last_bar['vol_prior'])
        spread = market_state.get("spread", 0.5)

        is_compressed = vcr < self.compression_threshold
        breakout_dist_req = max(0.30 * atr, 3.0 * spread, 2.0 * settings.TICK_SIZE)
        vol_ok = c_vol >= 1.25 * vol_prior

        long_breakout = is_compressed and (c_close > h12 + breakout_dist_req) and vol_ok
        short_breakout = is_compressed and (c_close < l12 - breakout_dist_req) and vol_ok

        action = "WAIT"
        direction = 0
        if long_breakout:
            action = "BULLISH BREAKOUT (RESEARCH)"
            direction = 1
        elif short_breakout:
            action = "BEARISH BREAKOUT (RESEARCH)"
            direction = -1

        reasons = [
            f"VCR: {vcr:.2f} (Compression threshold < {self.compression_threshold}) -> {'COMPRESSED' if is_compressed else 'NORMAL'}",
            f"Breakout distance requirement: ${breakout_dist_req:.1f} (max of 0.3 ATR, 3x spread, 2 ticks)",
            f"Close: ${c_close:.1f} vs 12-bar Range [${l12:.1f} - ${h12:.1f}]",
            f"Volume: {c_vol:.1f} vs required {1.25 * vol_prior:.1f}"
        ]

        return {
            "strategy": self.name,
            "status": self.status,
            "action": action,
            "direction": direction,
            "is_setup": (direction != 0),
            "vcr": round(vcr, 3),
            "is_compressed": is_compressed,
            "breakout_required_distance_usd": round(breakout_dist_req, 2),
            "reasons": reasons,
            "failure_risks": [
                "Breakouts often fail into mean-reverting chop after fee deductions",
                "High slippage during fast expansion moves increases adverse execution cost"
            ]
        }

alpha2_strategy = Alpha2RVolatilityBreakout()
