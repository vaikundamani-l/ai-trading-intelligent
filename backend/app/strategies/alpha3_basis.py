import math
from typing import Dict, Any, List
import numpy as np

class Alpha3RBasisAnalysis:
    """ALPHA-3R: BTC Perpetual / Spot Basis Analysis.
    Status: HEDGED ONLY (Disabled unless both spot and perp execution legs are verified).
    Acts primarily as basis monitor and funding risk governor.
    """
    def __init__(self):
        self.name = "ALPHA-3R: BTC BASIS ANALYSIS"
        self.status = "MONITOR ONLY / HEDGED LEGS REQUIRED"
        self.basis_history: List[float] = []

    def evaluate(self, market_state: Dict[str, Any]) -> Dict[str, Any]:
        last_p = market_state.get("last_price", 0.0)
        spot_p = market_state.get("spot_price", 0.0)
        funding_rate = market_state.get("funding_rate", 0.0)
        
        if spot_p <= 0 or last_p <= 0:
            return {
                "strategy": self.name,
                "status": self.status,
                "action": "DISABLED — SPOT REFERENCE UNAVAILABLE",
                "basis_bps": 0.0,
                "basis_usd": 0.0,
                "half_life_min": None,
                "regime": "UNKNOWN",
                "reasons": ["Spot reference price not available from exchange ticker"]
            }

        basis_usd = last_p - spot_p
        basis_bps = (basis_usd / spot_p) * 10000.0
        
        self.basis_history.append(basis_bps)
        if len(self.basis_history) > 100:
            self.basis_history.pop(0)

        # Estimate AR(1) OU Half-life if enough history
        half_life_min = None
        if len(self.basis_history) >= 20:
            y = np.array(self.basis_history[1:])
            x = np.array(self.basis_history[:-1])
            if np.std(x) > 1e-6:
                # Regress y on x
                slope, intercept = np.polyfit(x, y, 1)
                if 0.0 < slope < 1.0:
                    # delta_t is roughly 2s sampling
                    half_life_sec = math.log(2) * 2.0 / (-math.log(slope))
                    half_life_min = round(half_life_sec / 60.0, 1)

        # Classification
        if basis_bps > 15.0:
            regime = "RICH PREMIUM"
            action = "ARBITRAGE DISABLED — SPOT LEG UNAVAILABLE"
        elif basis_bps < -15.0:
            regime = "DEEP DISCOUNT"
            action = "ARBITRAGE DISABLED — SPOT LEG UNAVAILABLE"
        else:
            regime = "FAIR BASIS"
            action = "NEUTRAL"

        return {
            "strategy": self.name,
            "status": self.status,
            "action": action,
            "basis_usd": round(basis_usd, 2),
            "basis_bps": round(basis_bps, 2),
            "funding_rate_8h_pct": round(funding_rate * 100, 4),
            "estimated_ou_half_life_min": half_life_min,
            "basis_regime": regime,
            "reasons": [
                f"Perp ${last_p:.1f} vs Spot ${spot_p:.1f} = Basis of {basis_bps:+.1f} bps (${basis_usd:+.1f})",
                f"8-Hour funding rate is {funding_rate * 100:+.4f}%",
                "Hedged basis arbitrage requires two executable legs: long spot + short perp",
                "Spot leg execution is currently disabled for this account type"
            ],
            "risk_notes": [
                "Perp-only basis trading carries unhedged directional market risk",
                "Never present basis deviation as risk-free arbitrage"
            ]
        }

alpha3_strategy = Alpha3RBasisAnalysis()
