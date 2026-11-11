#!/usr/bin/env python3
"""BTC SBR-5: conservative OHLC research backtester for Delta India BTCUSD.

RESEARCH ONLY. No live trading or order placement. This is not proof of profitability.
Input 5m CSV: time,open,high,low,close,volume (time = UTC candle START,
Unix seconds, or an ISO-8601 UTC timestamp). Download API candles via 'fetch'.

pip install pandas numpy requests
python btc_sbr5_backtest.py fetch --start 2026-01-01 --end 2026-07-01 --out btc_5m.csv
python btc_sbr5_backtest.py test --csv btc_5m.csv --out trades.csv
"""
from __future__ import annotations
import argparse
import math
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

BARS_SEC = 300
FUNDING_SEC = 8 * 3600  # BTCUSD India examples: 05:30/13:30/21:30 IST = 00/08/16 UTC


@dataclass(frozen=True)
class Config:
    lookback: int = 24                 # previous 2 hours at 5m
    vol_lookback: int = 24
    atr_lookback: int = 14
    volume_multiplier: float = 1.25   # proposed, not calibrated
    sweep_atr: float = 0.12
    reclaim_atr: float = 0.10
    max_reclaim_atr: float = 1.20
    stop_buffer_atr: float = 0.10
    target_r: float = 1.80
    max_hold_bars: int = 5             # <= 25 min, conditional Scalper Offer may apply
    minimum_stop_fraction: float = 0.0015  # stop 15bp away minimum
    maximum_stop_fraction: float = 0.0080  # stop 80bp away maximum
    max_risk_fraction: float = 0.0025     # 0.25% of equity per trade, including fees
    max_notional_equity_multiple: float = 2.0
    daily_loss_limit_fraction: float = 0.01
    peak_drawdown_kill_fraction: float = 0.05
    max_consecutive_losses: int = 4
    cooldown_bars: int = 12
    fee_taker_fraction: float = 0.0005   # 0.05% each leg, BASELINE; not promo
    gst_multiplier: float = 1.18
    slip_per_leg_bps: float = 1.0        # stress test +/-; not an observed estimate
    tick_size: float = 0.5
    funding_buffer_seconds: int = 120


def fetch_candles(start_date: str, end_date: str, destination: str) -> pd.DataFrame:
    """Public 5m OHLC API. Downloads <=1900 bars/request; API may change."""
    import requests
    start = int(pd.Timestamp(start_date, tz='UTC').timestamp())
    end = int(pd.Timestamp(end_date, tz='UTC').timestamp())
    if end <= start:
        raise ValueError('End date must be strictly after start date')
    endpoint = 'https://api.india.delta.exchange/v2/history/candles'
    all_rows = []
    cursor = start
    while cursor < end:
        until = min(end, cursor + 1900 * BARS_SEC)
        for attempt in range(5):
            try:
                res = requests.get(endpoint, params={'resolution': '5m', 'symbol':'BTCUSD',
                                'start': cursor, 'end': until},timeout=20)
                if res.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f'HTTP {res.status_code}')
                res.raise_for_status()
                payload = res.json()
                if not payload.get('success', False):
                    raise RuntimeError(f'API success=false: {payload}')
                all_rows.extend(payload.get('result', []))
                break
            except (requests.RequestException, ValueError) as e:
                if attempt == 4:
                    raise RuntimeError(f'Fetch failed for {cursor}-{until}') from e
                time.sleep(2 ** attempt)
        cursor = until
        time.sleep(0.15)
    df = pd.DataFrame(all_rows)
    if df.empty:
        raise RuntimeError('No candles received; verify the date range/symbol.')
    df = df[['time','open','high','low','close','volume']].copy()
    # Paging boundaries may be inclusive: accept only literally identical overlaps.
    duplicate_rows = df[df.duplicated('time', keep=False)]
    if len(duplicate_rows):
        for _, block in duplicate_rows.groupby('time'):
            if len(block.drop_duplicates()) != 1:
                raise ValueError('Conflicting duplicate API candles: check exchange data.')
        df = df.drop_duplicates('time', keep='first')
    df = df.sort_values('time').reset_index(drop=True)
    df.to_csv(destination, index=False)
    return df


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = ['time','open','high','low','close','volume']
    if not set(needed).issubset(df.columns):
        raise ValueError(f'Missing columns {set(needed)-set(df.columns)}')
    if pd.api.types.is_numeric_dtype(df['time']):
        # Delta's candle 'time' field is Unix seconds; reject ms/microseconds.
        secs = pd.to_numeric(df['time'], errors='raise')
        if (secs.abs() > 1e11).any():
            raise ValueError('Time must be Unix seconds, not milliseconds/microseconds.')
        df['dt'] = pd.to_datetime(secs, unit='s', utc=True)
    else:
        dt = pd.to_datetime(df['time'], utc=True, errors='raise')
        df['dt'] = dt
    for c in needed[1:]:
        df[c] = pd.to_numeric(df[c], errors='raise')
    if df['dt'].duplicated().any():
        raise ValueError('Duplicate candle timestamps; do not silently deduplicate.')
    df = df.sort_values('dt').reset_index(drop=True)
    if len(df) < 100:
        raise ValueError('Need >=100 five-minute candles; months of data required for research.')
    gaps = df['dt'].diff().dt.total_seconds().dropna()
    if not gaps.eq(BARS_SEC).all():
        raise ValueError(f'Missing/irregular 5m candles: {int((gaps!=BARS_SEC).sum())} gaps. Reject data until repaired.')
    if ((df['low'] <= 0) | (df['volume'] < 0) | (df['high'] < df[['open','close','low']].max(axis=1)) |
         (df['low'] > df[['open','close','high']].min(axis=1))).any():
        raise ValueError('Corrupt prices or negative volumes in candles.')
    if (df['volume'] == 0).mean() > 0.01:
        raise ValueError('More than 1% zero-volume bars; inspect missing trades/data.')
    return df


def funding_in_window(entry_unix_s: int, holding_bars: int, buffer_sec: int) -> bool:
    """Conservatively avoid a funding snapshot anywhere in possible holding interval.
    Uses published 8h BTCUSD schedule. Verify actual schedule before live deployment.
    """
    left = entry_unix_s - buffer_sec
    right = entry_unix_s + holding_bars * BARS_SEC + buffer_sec
    next_snapshot = ((left - 1) // FUNDING_SEC + 1) * FUNDING_SEC
    return next_snapshot <= right


def get_signals(df: pd.DataFrame, c: Config) -> pd.DataFrame:
    d = df.copy()
    prev_close = d['close'].shift(1)
    true_range = pd.concat([d['high']-d['low'], (d['high']-prev_close).abs(),
                            (d['low']-prev_close).abs()],axis=1).max(axis=1)
    # All *normalizations* are calculated on bars before the signal bar.
    d['atr_prior'] = true_range.rolling(c.atr_lookback, min_periods=c.atr_lookback).mean().shift(1)
    d['prev_low'] = d['low'].rolling(c.lookback, min_periods=c.lookback).min().shift(1)
    d['prev_high'] = d['high'].rolling(c.lookback, min_periods=c.lookback).max().shift(1)
    d['vol_prior'] = d['volume'].rolling(c.vol_lookback,min_periods=c.vol_lookback).mean().shift(1)
    atr = d['atr_prior']
    active = (d['volume'] >= c.volume_multiplier * d['vol_prior']) & (atr > 0)
    d['long_signal'] = (
        active & (d['low'] < d['prev_low'] - np.maximum(c.tick_size, c.sweep_atr*atr)) &
        (d['close'] > d['prev_low'] + c.reclaim_atr * atr) &
        (d['close'] < d['prev_low'] + c.max_reclaim_atr * atr) &
        (d['close'] > d['open'])
    ).fillna(False)
    d['short_signal'] = (
        active & (d['high'] > d['prev_high'] + np.maximum(c.tick_size,c.sweep_atr*atr)) &
        (d['close'] < d['prev_high'] - c.reclaim_atr * atr) &
        (d['close'] > d['prev_high'] - c.max_reclaim_atr * atr) &
        (d['close'] < d['open'])
    ).fillna(False)
    return d


def process_trade(d: pd.DataFrame, signal_idx: int, direction: int, c: Config,
                  equity: float) -> dict | None:
    """Enter at next bar's open, exit at worse of stop/target when both hit.
    Bar-level model cannot reproduce spread/queue, exact mark triggers or intrabar path.
    """
    i = signal_idx+1
    if i >= len(d):
        return None
    sig = d.iloc[signal_idx]
    entry_bar = d.iloc[i]
    entry_t = int(entry_bar['dt'].timestamp())
    if funding_in_window(entry_t, c.max_hold_bars, c.funding_buffer_seconds):
        return None
    slip = c.slip_per_leg_bps / 10000
    entry = float(entry_bar['open']) * (1 + direction*slip)
    # Swing-stop from signal bar, then minimum stop distance; guard the max distance.
    if direction == 1:
        raw_stop = float(sig['low']) - c.stop_buffer_atr*float(sig['atr_prior'])
        stop = min(raw_stop, entry * (1-c.minimum_stop_fraction))
        stop = math.floor(stop/c.tick_size)*c.tick_size
    else:
        raw_stop = float(sig['high']) + c.stop_buffer_atr*float(sig['atr_prior'])
        stop = max(raw_stop, entry * (1+c.minimum_stop_fraction))
        stop = math.ceil(stop/c.tick_size)*c.tick_size
    risk_move = direction*(entry-stop)
    if risk_move <= 0 or risk_move/entry > c.maximum_stop_fraction:
        return None
    target = entry + direction * c.target_r * risk_move
    target = (math.ceil(target/c.tick_size)*c.tick_size if direction==1
              else math.floor(target/c.tick_size)*c.tick_size)
    # Include adverse execution slippage in sizing and two taker fees, no promotion.
    risk_per_notional = risk_move/entry + 2*c.fee_taker_fraction*c.gst_multiplier + 2*slip
    notional = min(equity*c.max_risk_fraction/risk_per_notional,
                   equity*c.max_notional_equity_multiple)
    # Delta India BTCUSD contract size: 0.001 BTC. Round DOWN, never up-risk.
    lot_notional = entry * 0.001
    notional = math.floor((notional + 1e-12) / lot_notional) * lot_notional
    if notional <= 0:
        return None
    exit_px = float('nan')
    exit_reason = ''
    exit_i = i
    # Entry bar is evaluated after its open; both-hit ambiguity resolved against us.
    for j in range(i, min(i+c.max_hold_bars,len(d))):
        bar = d.iloc[j]
        # If gap across stop, execute at worse of stop / open.
        opened_past_stop = (direction==1 and bar['open'] <= stop) or (direction==-1 and bar['open'] >= stop)
        stop_hit = (direction==1 and bar['low'] <= stop) or (direction==-1 and bar['high'] >= stop)
        target_hit = (direction==1 and bar['high'] >= target) or (direction==-1 and bar['low'] <= target)
        if opened_past_stop or stop_hit:
            base = (min(stop,float(bar['open'])) if direction==1
                    else max(stop,float(bar['open'])))
            exit_px = base * (1-direction*slip)
            exit_reason = 'stop_or_ambiguous_both_hit'
        elif target_hit:
            # Gap improvements intentionally ignored; target is a conservative cap.
            exit_px = float(target) * (1-direction*slip)
            exit_reason = 'target'
        elif j == min(i+c.max_hold_bars,len(d))-1:
            exit_px = float(bar['close'])*(1-direction*slip)
            exit_reason = 'time_or_dataset_end'
        else:
            continue
        exit_i = j
        break
    if not math.isfinite(exit_px):
        raise AssertionError('Trade exited without price.')
    gross_fraction = direction*(exit_px-entry)/entry
    # Exact per-leg fees normalized to entry notional: exit notional differs with price.
    fees_fraction = c.fee_taker_fraction*c.gst_multiplier*(1 + exit_px/entry)
    net_fraction = gross_fraction-fees_fraction  # funding gated; not applicable
    pnl = notional*net_fraction
    return {'signal_utc':sig['dt'].isoformat(),'entry_utc':entry_bar['dt'].isoformat(),
            'exit_utc':d.iloc[exit_i]['dt'].isoformat(),'direction':direction,
            'entry':entry,'stop':stop,'target':target,'exit':exit_px,
            'reason':exit_reason,'holding_bars':exit_i-i+1,
            'notional_usd_equivalent':notional,'gross_bps':gross_fraction*10000,
            'fees_bps':fees_fraction*10000,'net_bps':net_fraction*10000,
            'pnl_equity_units':pnl,'exit_idx':exit_i}


def run_backtest(df: pd.DataFrame, c: Config = Config(), initial_equity: float=10000) -> tuple[pd.DataFrame,dict]:
    if initial_equity<=0:
        raise ValueError('Equity must be positive')
    d = get_signals(df,c)
    equity, peak = initial_equity, initial_equity
    records = []
    i = max(c.lookback,c.vol_lookback,c.atr_lookback)+1
    losing_streak = 0
    cooldown_end = -1
    daily_start_equity = initial_equity
    day = None
    while i < len(d)-1:
        current_day = d.iloc[i]['dt'].date()
        if current_day != day:
            day = current_day
            daily_start_equity = equity
        if (i < cooldown_end or
            equity <= daily_start_equity*(1-c.daily_loss_limit_fraction)):
            i+=1
            continue
        if equity <= peak*(1-c.peak_drawdown_kill_fraction):
            break  # capital protection kill-switch: no restart without review
        direction = (1 if d.iloc[i]['long_signal'] else
                     -1 if d.iloc[i]['short_signal'] else 0)
        if direction==0:
            i+=1
            continue
        trade = process_trade(d,i,direction,c,equity)
        if trade is None:
            i+=1
            continue
        equity += trade['pnl_equity_units']
        peak=max(peak,equity)
        trade['equity_after']=equity
        records.append(trade)
        losing_streak = losing_streak+1 if trade['pnl_equity_units']<=0 else 0
        i = trade['exit_idx']+1  # no overlapping positions, no new signal on exit bar
        if losing_streak>=c.max_consecutive_losses:
            cooldown_end=i+c.cooldown_bars
            losing_streak=0
    trades=pd.DataFrame(records)
    if trades.empty:
        return trades, {'trades':0,'start_equity':initial_equity,'end_equity':equity,
                        'total_return_pct':0.0,'win_rate_pct':None,'profit_factor':None,
                        'max_closed_trade_drawdown_pct':None,'avg_net_bps':None,
                        'status':'NO TRADES: not evidence of profit'}
    series=pd.Series([initial_equity]+trades['equity_after'].tolist())
    drawdowns=series/series.cummax()-1
    wins=trades.loc[trades['pnl_equity_units']>0,'pnl_equity_units']
    losses=trades.loc[trades['pnl_equity_units']<0,'pnl_equity_units']
    # Without losses PF is undefined, NOT evidence of infinite profitability.
    profit_factor = (wins.sum()/abs(losses.sum()) if len(losses)>0 else None)
    summary={'trades':len(trades),'start_equity':initial_equity,'end_equity':float(equity),
             'total_return_pct':(equity/initial_equity-1)*100,
             'win_rate_pct':100*float((trades['pnl_equity_units']>0).mean()),
             'profit_factor':float(profit_factor) if profit_factor is not None else None,
             'max_closed_trade_drawdown_pct':float(100*drawdowns.min()),
             'avg_net_bps':float(trades['net_bps'].mean()),
             'status':'BAR-LEVEL RESEARCH ONLY; not forward/paper validated'}
    return trades,summary


def main() -> None:
    parser=argparse.ArgumentParser(description='BTC SBR-5 research-only engine')
    sub=parser.add_subparsers(dest='cmd',required=True)
    fetch=sub.add_parser('fetch',help='Download Delta India BTCUSD 5m OHLC')
    fetch.add_argument('--start',required=True,help='UTC inclusive YYYY-MM-DD')
    fetch.add_argument('--end',required=True,help='UTC exclusive YYYY-MM-DD')
    fetch.add_argument('--out',default='btc_5m.csv')
    back=sub.add_parser('test',help='Run conservative research replay')
    back.add_argument('--csv',required=True)
    back.add_argument('--out',default='trades.csv')
    back.add_argument('--slip-bps',type=float,default=1.0,help='Per-leg assumed slippage bps')
    args=parser.parse_args()
    if args.cmd=='fetch':
        df=fetch_candles(args.start,args.end,args.out)
        print(f'Downloaded {len(df)} candles to {args.out}; audit gaps before research.')
    else:
        if args.slip_bps < 0:
            raise ValueError('slippage must be >=0')
        from dataclasses import replace
        c=replace(Config(),slip_per_leg_bps=args.slip_bps)
        df=load_data(args.csv)
        trades,summary=run_backtest(df,c)
        trades.to_csv(args.out,index=False)
        print('Research-only summary:',summary)
        print('Trade log:',args.out)
        print('Missing: bid/ask spread, true fill latency, queue, mark-price, '
              'funding overrides, partial fills. Not live-deployable.')


if __name__=='__main__':
    main()
