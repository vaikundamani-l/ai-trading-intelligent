import time
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

class Alpha4RDislocationProtection:
    """ALPHA-4R: Market Dislocation Protection and Risk Governor.
    Acts as a safety gate for the entire trading engine.
    Blocks all strategy recommendations when unsafe market conditions or jumps are detected.
    """
    def __init__(self):
        self.name = "ALPHA-4R: MARKET DISLOCATION PROTECTION"
        self.cooldown_until_ts = 0
        self.last_halt_reason = ""
        self.cooldown_duration_sec = 600  # 2 completed 5m candles (10 minutes)

    def evaluate(self, df_5m: pd.DataFrame, market_state: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """Returns: (is_safe: bool, status_message: str, details: dict)"""
        now = time.time()
        
        # 1. Check if currently in cooldown
        if now < self.cooldown_until_ts:
            remaining = int(self.cooldown_until_ts - now)
            return False, f"HALTED — In Dislocation Cooldown ({remaining}s remaining): {self.last_halt_reason}", {
                "is_dislocated": True,
                "reason": self.last_halt_reason,
                "cooldown_remaining_sec": remaining
            }

        # 2. Check Data Freshness and Exchange Status
        if market_state.get("connection_status") != "LIVE":
            return False, f"HALTED — Data status is {market_state.get('connection_status')}", {
                "is_dislocated": True,
                "reason": f"Connection not LIVE: {market_state.get('connection_status')}"
            }

        if market_state.get("exchange_status") != "operational":
            return False, f"HALTED — Exchange status is {market_state.get('exchange_status')}", {
                "is_dislocated": True,
                "reason": f"Exchange not operational: {market_state.get('exchange_status')}"
            }

        # 3. Check Extreme Spread Expansion (> 15 bps)
        spread_bps = market_state.get("spread_bps", 0.0)
        if spread_bps > 15.0:
            self._trigger_cooldown(f"Abnormal spread expansion ({spread_bps:.1f} bps > 15.0 bps)")
            return False, f"HALTED — Extreme spread expansion ({spread_bps:.1f} bps)", {
                "is_dislocated": True,
                "reason": "Extreme spread expansion",
                "spread_bps": spread_bps
            }

        # 4. Check Mark-to-Mid Dislocation (> 50 bps)
        last_p = market_state.get("last_price", 0.0)
        mark_p = market_state.get("mark_price", 0.0)
        if last_p > 0 and mark_p > 0:
            mark_dev_bps = abs(last_p - mark_p) / last_p * 10000.0
            if mark_dev_bps > 50.0:
                self._trigger_cooldown(f"Severe Mark/Price dislocation ({mark_dev_bps:.1f} bps > 50.0 bps)")
                return False, f"HALTED — Mark/Price dislocation ({mark_dev_bps:.1f} bps)", {
                    "is_dislocated": True,
                    "reason": "Severe Mark/Price dislocation",
                    "mark_dev_bps": mark_dev_bps
                }

        # 5. Check 5m Sudden Return Jump (> 2.5 * ATR / close)
        if df_5m is not None and len(df_5m) >= 15:
            last_bar = df_5m.iloc[-1]
            prev_bar = df_5m.iloc[-2]
            bar_ret = abs(last_bar['close'] - prev_bar['close']) / prev_bar['close']
            
            prev_close = df_5m['close'].shift(1)
            tr = pd.concat([
                df_5m['high'] - df_5m['low'],
                (df_5m['high'] - prev_close).abs(),
                (df_5m['low'] - prev_close).abs()
            ], axis=1).max(axis=1)
            atr14 = tr.rolling(14).mean().iloc[-2]
            
            if atr14 > 0 and prev_bar['close'] > 0:
                jump_threshold = 2.5 * (atr14 / prev_bar['close'])
                if bar_ret > jump_threshold:
                    self._trigger_cooldown(f"Sudden 5m price jump ({bar_ret*100:.2f}% > {jump_threshold*100:.2f}%)")
                    return False, f"HALTED — Sudden price shock jump ({bar_ret*100:.2f}%)", {
                        "is_dislocated": True,
                        "reason": "Sudden price shock jump",
                        "jump_pct": bar_ret * 100
                    }

        return True, "NORMAL MARKET CONDITIONS", {
            "is_dislocated": False,
            "reason": "All dislocation and risk filters clear",
            "spread_bps": spread_bps
        }

    def _trigger_cooldown(self, reason: str):
        self.cooldown_until_ts = time.time() + self.cooldown_duration_sec
        self.last_halt_reason = reason

alpha4_dislocation = Alpha4RDislocationProtection()
