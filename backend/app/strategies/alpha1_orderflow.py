from typing import Dict, Any

class Alpha1ROrderFlow:
    """ALPHA-1R: Order-Flow Intelligence (Microstructure Impulse).
    Status: RESEARCH ONLY - No live order execution until queue priority
    and adverse selection are empirically calibrated.
    """
    def __init__(self):
        self.name = "ALPHA-1R: ORDER-FLOW INTELLIGENCE"
        self.status = "RESEARCH ONLY"

    def evaluate(self, market_state: Dict[str, Any]) -> Dict[str, Any]:
        ofi = market_state.get("order_flow_imbalance", 0.0)
        tfi = market_state.get("trade_flow_imbalance", 0.0)
        micro_dev = market_state.get("micro_price_dev", 0.0)
        buy_vol = market_state.get("aggressive_buy_vol", 0.0)
        sell_vol = market_state.get("aggressive_sell_vol", 0.0)
        spread_bps = market_state.get("spread_bps", 0.0)

        # Pressure classification
        # OFI in [-1, 1], TFI in [-1, 1]
        score = (ofi * 0.4) + (tfi * 0.6)
        
        if score > 0.25:
            regime = "BUY PRESSURE"
            action = "BUY BIAS (RESEARCH ONLY)"
        elif score < -0.25:
            regime = "SELL PRESSURE"
            action = "SELL BIAS (RESEARCH ONLY)"
        else:
            regime = "NEUTRAL"
            action = "NEUTRAL"

        return {
            "strategy": self.name,
            "status": self.status,
            "pressure_regime": regime,
            "action": action,
            "metrics": {
                "order_flow_imbalance": round(ofi, 4),
                "trade_flow_imbalance": round(tfi, 4),
                "composite_score": round(score, 4),
                "micro_price_deviation_usd": round(micro_dev, 2),
                "aggressive_buy_notional": round(buy_vol, 2),
                "aggressive_sell_notional": round(sell_vol, 2),
                "spread_bps": round(spread_bps, 2)
            },
            "rationale": [
                f"OFI is {round(ofi, 3)} measuring top-10 book liquidity asymmetry",
                f"TFI is {round(tfi, 3)} measuring aggressor trade volume dominance",
                f"Micro-price deviation is ${round(micro_dev, 2)} relative to mid",
                "Passive limit orders face adverse selection during directional bursts"
            ],
            "limitations": [
                "L2 orderbook snapshots do not reproduce exchange FIFO queue priority",
                "Visible depth can be canceled instantly before marketable order arrival",
                "Single-venue order flow ignores global price leadership across larger venues"
            ]
        }

alpha1_strategy = Alpha1ROrderFlow()
