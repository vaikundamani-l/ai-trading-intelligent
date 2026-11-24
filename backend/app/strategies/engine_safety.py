"""Shared numerical and execution checks; no network or account mutations."""
import math

import numpy as np
import pandas as pd

from app.config import settings


def completed_history(df, bar_seconds, as_of):
    required = ['time', 'open', 'high', 'low', 'close', 'volume']
    if df is None or not set(required).issubset(df.columns):
        raise ValueError('Candle history missing required OHLCV fields')
    d = df.copy()
    d[required] = d[required].apply(pd.to_numeric, errors='coerce')
    if not np.isfinite(d['time']).all():
        raise ValueError('Invalid candle timestamps')
    d = d[d['time'] + bar_seconds <= as_of].copy()
    if not np.isfinite(d[required]).all().all():
        raise ValueError('Candle history contains non-finite prices or volume')
    if d['time'].duplicated().any() or not d['time'].is_monotonic_increasing:
        raise ValueError('Candle timestamps are duplicated or unsorted')
    prices = d[['open', 'high', 'low', 'close']]
    valid = ((prices > 0).all(axis=1) & (d['volume'] >= 0)
             & (d['high'] >= prices[['open', 'close', 'low']].max(axis=1))
             & (d['low'] <= prices[['open', 'close', 'high']].min(axis=1)))
    if not valid.all():
        raise ValueError('Candle history has invalid OHLC ranges or negative volume')
    return d


def executable_quote(market, fallback):
    if 'best_bid' not in market and 'best_ask' not in market:
        return float(fallback), float(fallback)  # Explicit modeled quote for replay.
    try:
        bid, ask = float(market['best_bid']), float(market['best_ask'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Both executable bid and ask are required') from None
    if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask):
        raise ValueError('Executable bid/ask is invalid or crossed')
    return bid, ask


def maximum_stop_fraction(bar_seconds, atr, entry, baseline):
    if bar_seconds < 3600:
        return baseline
    return min(settings.HIGHER_TF_MAX_STOP_FRACTION,
               max(baseline, settings.HIGHER_TF_STOP_ATR_MULTIPLIER * atr / entry))


def resolve_bar_exit(bar, direction, stop, target, *, timeout=False):
    """OHLC cannot order two touches: adverse stop wins, including opening gaps."""
    if (direction == 1 and bar['low'] <= stop) or (direction == -1 and bar['high'] >= stop):
        price = min(stop, float(bar['open'])) if direction == 1 else max(stop, float(bar['open']))
        return price, 'STOP_HIT'
    if (direction == 1 and bar['high'] >= target) or (direction == -1 and bar['low'] <= target):
        return float(target), 'TARGET_HIT'
    if timeout:
        return float(bar['close']), 'TIME_EXIT'
    return None
