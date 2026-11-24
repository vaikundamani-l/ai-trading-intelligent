"""Predeclared research alternatives, never selected on final-period results."""
PROFILES = ('baseline', 'trend_context', 'trend_and_extension')


def context_masks(d, atr, profile='baseline'):
    if profile not in PROFILES:
        raise ValueError(f'Unknown momentum context profile: {profile}')
    close = d['close']
    if profile == 'baseline':
        return close.notna(), close.notna()
    fast = close.ewm(span=9, adjust=False).mean()
    slow = close.ewm(span=21, adjust=False).mean()
    change = close - close.shift(12)
    path = close.diff().abs().rolling(12, min_periods=12).sum()
    efficient = change.abs() / path.replace(0, float('nan')) >= 0.25
    long = efficient & (fast > slow) & (slow > slow.shift(3))
    short = efficient & (fast < slow) & (slow < slow.shift(3))
    if profile == 'trend_and_extension':
        long &= close - slow <= 2 * atr
        short &= slow - close <= 2 * atr
    return long.fillna(False), short.fillna(False)
