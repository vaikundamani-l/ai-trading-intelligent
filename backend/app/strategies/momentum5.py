"""Completed-bar momentum candidates shared by chart, live and replay."""
import pandas as pd
from app.strategies.big_move import big_move_masks
from app.strategies.momentum_context import context_masks


def momentum_candidates(d: pd.DataFrame, atr: pd.Series, volume_prior: pd.Series, *, big_move_only=False, context_profile='baseline'):
    close, opened = d['close'], d['open']
    fast = close.ewm(span=9, adjust=False).mean()
    medium = close.ewm(span=21, adjust=False).mean()
    high = d['high'].rolling(6, min_periods=6).max().shift(1)
    low = d['low'].rolling(6, min_periods=6).min().shift(1)
    body = close - opened
    span = (d['high'] - d['low']).replace(0, float('nan'))
    active = (atr > 0) & (volume_prior > 0)
    volume = d['volume'] >= 1.25 * volume_prior
    # A decisive six-bar breakout can detect the start of a reversal before
    # EMA50 catches up. Small pokes and long rejection wicks do not qualify.
    up = active & volume & (body >= 0.6 * atr) & ((close - d['low']) / span >= 0.75)
    down = active & volume & (-body >= 0.6 * atr) & ((d['high'] - close) / span >= 0.75)
    break_long = up & (close > high + 0.1 * atr) & (close > medium)
    break_short = down & (close < low - 0.1 * atr) & (close < medium)

    # Continuations require an actual pullback into EMA9 on the previous bar,
    # then a close through that bar's extreme in the established direction.
    pull_long = (active & (d['volume'] >= volume_prior) & (fast.shift(1) > medium.shift(1))
                 & (medium.shift(1) > medium.shift(4))
                 & (d['low'].shift(1) <= fast.shift(1))
                 & (close > d['high'].shift(1) + 0.1 * atr)
                 & (close > fast) & (body >= 0.4 * atr)
                 & ((close - d['low']) / span >= 0.65))
    pull_short = (active & (d['volume'] >= volume_prior) & (fast.shift(1) < medium.shift(1))
                  & (medium.shift(1) < medium.shift(4))
                  & (d['high'].shift(1) >= fast.shift(1))
                  & (close < d['low'].shift(1) - 0.1 * atr)
                  & (close < fast) & (-body >= 0.4 * atr)
                  & ((d['high'] - close) / span >= 0.65))
    if big_move_only:
        big_long, big_short = big_move_masks(d, atr, volume_prior)
        break_long &= big_long
        pull_long &= big_long
        break_short &= big_short
        pull_short &= big_short
    context_long, context_short = context_masks(d, atr, context_profile)
    break_long &= context_long
    pull_long &= context_long
    break_short &= context_short
    pull_short &= context_short
    raw = (break_long | break_short | pull_long | pull_short).fillna(False)
    recent = raw.shift(1).rolling(3, min_periods=1).max().fillna(0).astype(bool)
    return pd.DataFrame({
        'momentum_long': ((break_long | pull_long) & ~recent).fillna(False),
        'momentum_short': ((break_short | pull_short) & ~recent).fillna(False),
        'momentum_kind': ['BREAKOUT' if b else 'PULLBACK' for b in (break_long | break_short)],
    }, index=d.index)
