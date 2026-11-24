"""Shared, causal selection policy for substantial moves, not small noise."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BigMovePolicy:
    min_move_fraction: float = 0.0035  # 0.35% directional move over three bars
    min_body_fraction: float = 0.0015  # 0.15% signal candle body
    min_body_atr: float = 1.0
    min_volume_ratio: float = 1.75
    min_efficiency: float = 0.70
    min_gross_target_fraction: float = 0.005  # 0.50% modeled target distance
    min_net_target_fraction: float = 0.0035
    min_target_cost_multiple: float = 3.0


BIG_MOVE_POLICY = BigMovePolicy()


def big_move_masks(d, atr, volume_prior):
    p = BIG_MOVE_POLICY
    close = d['close']
    move = close - close.shift(3)
    path = close.diff().abs().rolling(3, min_periods=3).sum()
    efficiency = move.abs() / path.replace(0, float('nan'))
    body = close - d['open']
    fraction = move / close.shift(3)
    strong = ((body.abs() >= p.min_body_atr * atr)
              & (body.abs() / d['open'] >= p.min_body_fraction)
              & (d['volume'] >= p.min_volume_ratio * volume_prior)
              & (volume_prior > 0) & (atr > 0)
              & (efficiency >= p.min_efficiency))
    return ((strong & (body > 0) & (fraction >= p.min_move_fraction)).fillna(False),
            (strong & (body < 0) & (fraction <= -p.min_move_fraction)).fillna(False))


def substantial_target(gross_fraction, cost_fraction):
    p = BIG_MOVE_POLICY
    return (gross_fraction >= p.min_gross_target_fraction
            and gross_fraction - cost_fraction >= p.min_net_target_fraction
            and gross_fraction >= p.min_target_cost_multiple * cost_fraction)
