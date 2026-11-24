"""Causal filters shared by the live SBR evaluator and historical research."""
import pandas as pd


def opposing_trend_masks(df: pd.DataFrame, atr: pd.Series):
    """Block fading an established trend using only bars before the setup.

    Flat ranges still permit sweep/reclaim reversals. Require 50 bars of
    history, EMA alignment and a meaningful three-bar EMA21 slope.
    """
    close = df['close'].shift(1)
    fast = close.ewm(span=9, adjust=False).mean()
    medium = close.ewm(span=21, adjust=False).mean()
    slow = close.ewm(span=50, adjust=False, min_periods=50).mean()
    slope = medium - medium.shift(3)
    bullish = (close > fast) & (fast > medium) & (medium > slow) & (slope > 0.15 * atr)
    bearish = (close < fast) & (fast < medium) & (medium < slow) & (slope < -0.15 * atr)
    # Fast reversals need protection before the slow EMA50 can realign.
    impulse = close - close.shift(3)
    bullish |= (fast > medium) & (close > medium) & (impulse > 1.5 * atr) & (slope > 0)
    bearish |= (fast < medium) & (close < medium) & (impulse < -1.5 * atr) & (slope < 0)
    return bearish.fillna(False), bullish.fillna(False)
