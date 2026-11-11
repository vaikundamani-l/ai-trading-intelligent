"""Transparent setup confluence, deliberately not a probability of profit."""
import math
import time

def assess_setup(decision, market, candles):
    direction = decision.get('direction', 0)
    active = decision.get('status') == 'ACTIVE_SETUP' and direction in (-1, 1)
    try:
        rr = float(decision.get('risk_reward') or 0)
        spread = float(market.get('spread_bps', float('inf')))
    except (ValueError, TypeError):
        rr, spread = 0, float('inf')
    recent = False
    aligned = False
    if candles is not None and not candles.empty and {'time', 'close'}.issubset(candles.columns):
        completed = candles[candles['time'] + 300 <= time.time()]
        if len(completed) >= 50:
            recent = time.time() - float(completed.iloc[-1]['time']) <= 600
            close = completed['close']
            fast = close.ewm(span=9, adjust=False).mean().iloc[-1]
            slow = close.ewm(span=21, adjust=False).mean().iloc[-1]
            aligned = bool(direction * (fast - slow) > 0)
    checks = [
        dict(label='Completed SBR-5 setup', passed=active),
        dict(label='Fresh and safe market', passed=bool(market.get('is_data_safe')) and recent),
        dict(label='Spread at most 2 bps', passed=bool(math.isfinite(spread) and 0 <= spread <= 2)),
        dict(label='Net target reward/risk at least 1.2', passed=bool(math.isfinite(rr) and rr >= 1.2)),
        dict(label='Completed-bar EMA 9/21 alignment', passed=aligned),
    ]
    passed = sum(c['passed'] for c in checks)
    strong = all(c['passed'] for c in checks)
    return dict(grade='STRONG SETUP' if strong else ('WATCH' if active else 'NO TRADE'), checks=checks,
                checks_passed=passed, checks_total=len(checks), eligible_for_auto_paper=strong,
                explanation='Rule confluence only; not a win probability or validated predictive edge.')
