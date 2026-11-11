"""Long-only BB(20, 1.8), Wilder ATR(14), UTC-aligned 8h research strategy."""
import time
import math
import pandas as pd


def completed_8h(hourly, now=None, deviation=1.8, duration=28800, base=3600):
    now = time.time() if now is None else now
    if hourly is None or hourly.empty:
        return pd.DataFrame()
    d = hourly.copy().sort_values('time').drop_duplicates('time')
    for col in ('time', 'open', 'high', 'low', 'close'):
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=['time', 'open', 'high', 'low', 'close'])
    d = d[d[['time','open','high','low','close']].apply(lambda c: c.map(math.isfinite)).all(axis=1)]
    d = d[(d.low > 0) & (d.high >= d[['open','close','low']].max(axis=1)) & (d.low <= d[['open','close']].min(axis=1))]
    if duration < base or duration % base:
        raise ValueError('Timeframe must be a multiple of the source candle interval')
    d = d[(d.time % base == 0) & (d.time + base <= now)]
    d['bucket'] = (d.time // duration) * duration
    groups = d.groupby('bucket')
    bars = groups.agg(time=('time', 'min'), open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
    bars = bars[(groups.size() == duration // base) & (bars.time + duration <= now)].copy()
    close = bars.close
    bars['lower'] = close.rolling(20).mean() - deviation * close.rolling(20).std(ddof=0)
    tr = pd.concat([bars.high-bars.low, (bars.high-close.shift()).abs(), (bars.low-close.shift()).abs()], axis=1).max(axis=1)
    # Wilder seed: simple mean of first 14 true ranges, followed by RMA.
    atr = pd.Series(float('nan'), index=bars.index)
    if len(bars) >= 14:
        atr.iloc[13] = tr.iloc[:14].mean()
        for i in range(14, len(bars)):
            atr.iloc[i] = (atr.iloc[i-1]*13 + tr.iloc[i])/14
    bars['atr'] = atr
    # A gap invalidates indicator context until 21 contiguous bars rebuild it.
    bars['contiguous'] = bars.time.diff().eq(duration).rolling(20).sum().eq(20)
    bars['setup'] = (close.shift() < bars.lower.shift()) & (close >= bars.lower) & (close > bars.open) & bars.contiguous & (atr > 0)
    return bars


def analyze(hourly, market, now=None, duration=28800, base=3600):
    now = time.time() if now is None else now
    bars = completed_8h(hourly, now, duration=duration, base=base)
    result = dict(strategy=f'BB-{duration//60}m RE-ENTRY', timeframe_minutes=duration//60, venue='Delta India BTCUSD', mode='RESEARCH ONLY', action='WAIT', long_only=True, max_hold_hours=12*duration/3600, completed_bars=len(bars), parameters=dict(length=20, deviation=1.8, atr_period=14, stop_atr=2, target_atr=2), reasons=[])
    if len(bars) < 21 or not bool(bars.iloc[-1].contiguous):
        result['reasons'] = [f'Need at least 21 consecutive complete {duration//60}m candles; incomplete groups are excluded.']
        return result
    prev, last = bars.iloc[-2], bars.iloc[-1]
    fresh = 0 <= now - (last.time + duration) <= min(900, duration/20)
    checks = dict(previous_close_below_band=bool(prev.close < prev.lower), current_close_reentered=bool(last.close >= last.lower), current_candle_green=bool(last.close > last.open), entry_within_15_minutes=bool(fresh), feed_live=market.get('connection_status') == 'LIVE')
    result.update(checks=checks, signal_time=int(last.time+duration), valid_until_ts=int(last.time+duration+min(900,duration/20)), atr=float(last.atr), lower_band=float(last.lower))
    ask = float(market.get('best_ask') or 0)
    if all(checks.values()) and math.isfinite(ask) and ask > 2*last.atr:
        result.update(action='BUY CANDIDATE', entry_price=ask, stop_loss=float(ask-2*last.atr), take_profit=float(ask+2*last.atr))
    result['reasons'] = ['A closes below its lower band → B closes green back inside → enter at C open.', f'Entry window: {min(900,duration/20):.0f} seconds after close; historical simulation uses exact next open.', 'Research signal only; execution requires separate timeframe validation.']
    return result


def replay(hourly, now=None, cost_bps=13.8, deviation=1.8, duration=28800, base=3600):
    """Next-open simulation, one position, pessimistic stop-first same-bar exits."""
    bars = completed_8h(hourly, now, deviation, duration, base)
    trades = []
    position = None
    if len(bars) > 1 and not bars.time.diff().iloc[1:].eq(duration).all():
        return dict(trades=[], total_trades=0, open_position=None, net_bps_sum=0, assumptions='Simulation withheld: missing 8h bars prevent reliable stop/target replay.')
    for i in range(21, len(bars)):
        bar, signal = bars.iloc[i], bars.iloc[i-1]
        if position is None and bool(signal.setup) and bar.time-signal.time == duration:
            entry = float(bar.open)
            if entry > 2*signal.atr:
                position = dict(entry=entry, stop=entry-2*float(signal.atr), target=entry+2*float(signal.atr), entry_time=int(bar.time))
        if position:
            px, reason = None, None
            if bar.open <= position['stop']:
                px, reason = float(bar.open), 'GAP STOP'
            elif bar.low <= position['stop']:
                px, reason = position['stop'], 'STOP'
            elif bar.high >= position['target']:
                px, reason = position['target'], 'TARGET'
            elif bar.time+duration-position['entry_time'] >= 12*duration:
                px, reason = float(bar.close), 'TIME'
            if px is not None:
                trades.append(dict(**position, exit=px, reason=reason, net_bps=(px/position['entry']-1)*10000-cost_bps))
                position = None
    return dict(trades=trades, total_trades=len(trades), open_position=position, net_bps_sum=sum(t['net_bps'] for t in trades), assumptions='Fixed 1x notional returns; Delta fees/GST and 1bp slippage per side; funding excluded. Not a portfolio return or reproduced CoinDCX result.')
