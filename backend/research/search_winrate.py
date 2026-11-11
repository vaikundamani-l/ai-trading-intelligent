"""Reproducible research search. Does not place orders or alter the trading ledger."""
import json
import math
import time
from pathlib import Path
import requests
import pandas as pd
from app.strategies.bollinger8h import completed_8h

ROOT = Path(__file__).resolve().parent


def summary(trades):
    values = [t['net_bps'] for t in trades]
    n = len(values)
    wins = sum(v > 0 for v in values)
    p = wins/n if n else 0
    z = 1.96
    center = (p+z*z/(2*n))/(1+z*z/n) if n else 0
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n) if n else 0
    gains, losses = sum(max(v,0) for v in values), -sum(min(v,0) for v in values)
    return dict(trades=n, wins=wins, win_rate_pct=100*p, win_rate_interval_95_pct=[100*max(0,center-half),100*min(1,center+half)], mean_net_bps=sum(values)/n if n else 0, sum_net_bps=sum(values), profit_factor=gains/losses if losses else None)


def simulate(bars, family, target, stop, begin, end, cost=13.8):
    """Long-only, next-open entry, 12-bar hold; conservative same-bar stop first."""
    trades=[]
    prev_high=bars.high.rolling(20).max().shift()
    position=None
    valid = bars[(bars.time >= begin) & (bars.time + bars.attrs['duration'] <= end)]
    if valid.empty:
        return trades
    last_time = valid.iloc[-1].time
    for i in range(21,len(bars)):
        bar, signal=bars.iloc[i],bars.iloc[i-1]
        # Exit any remaining position at the split boundary; no cross-split trades.
        if bar.time < begin or bar.time+bars.attrs['duration'] > end:
            continue
        condition=bool(signal.setup) if family=='BB_REENTRY' else signal.close>prev_high.iloc[i-1]
        if position is None and condition and signal.time>=begin and bar.time-signal.time==bars.attrs['duration']:
            entry=float(bar.open)
            if entry>stop*signal.atr and signal.atr>0:
                position=dict(entry=entry,sl=entry-stop*float(signal.atr),tp=entry+target*float(signal.atr),age=0)
        if position:
            position['age']+=1
            px=None
            if bar.open<=position['sl']: px=float(bar.open)
            elif bar.low<=position['sl']: px=position['sl']
            elif bar.high>=position['tp']: px=position['tp']
            elif position['age']>=12 or bar.time==last_time: px=float(bar.close)
            if px is not None:
                trades.append(dict(net_bps=(px/position['entry']-1)*10000-cost))
                position=None
    return trades


def run():
    end=int(time.time())//900*900
    start=end-90*86400
    rows=[]
    for left in range(start,end,900*900):
        r=requests.get('https://api.india.delta.exchange/v2/history/candles',params=dict(symbol='BTCUSD',resolution='15m',start=left,end=min(end,left+900*900)),timeout=30)
        r.raise_for_status()
        payload=r.json()
        if not payload.get('success'): raise RuntimeError('Exchange data request rejected')
        rows.extend(payload['result'])
    d=pd.DataFrame(rows).drop_duplicates('time').sort_values('time')
    d=d[(d.time>=start)&(d.time+900<=end)]
    if len(d)<8000: raise RuntimeError('Insufficient history; no candidate search performed')
    d.to_json(ROOT/'winrate_candles.json',orient='records')
    split=(start+int((end-start)*.6))//28800*28800
    candidates=[]
    for minutes in (15,45,240,480):
        bars=completed_8h(d,end,duration=minutes*60,base=900)
        bars.attrs['duration']=minutes*60
        if not bars.time.diff().dropna().eq(minutes*60).all(): raise RuntimeError(f'Missing {minutes}m bars; cannot reconstruct exits')
        for family in ('BB_REENTRY','BREAKOUT20'):
            for target,stop in ((2.,2.),(.75,2.5),(.5,3.)):
                spec=dict(minutes=minutes,family=family,target_atr=target,stop_atr=stop)
                train=summary(simulate(bars,family,target,stop,start,split))
                candidates.append(dict(spec=spec,train=train))
    eligible=[c for c in candidates if c['train']['trades']>=30]
    selected=max(eligible,key=lambda c:c['train']['mean_net_bps']) if eligible else None
    if selected:
        s=selected['spec']
        bars=completed_8h(d,end,duration=s['minutes']*60,base=900)
        bars.attrs['duration']=s['minutes']*60
        selected['heldout']=summary(simulate(bars,s['family'],s['target_atr'],s['stop_atr'],split,end))
        selected['heldout_double_cost']=summary(simulate(bars,s['family'],s['target_atr'],s['stop_atr'],split,end,cost=27.6))
    result=dict(generated_at=end,days=90,candles=len(d),train_start=start,split=split,test_end=end,candidates=candidates,selected=selected,promotion='NOT PROMOTED',limitations=['Exploratory research on one venue and 90-day window.', '13.8bps modeled round-trip costs; funding excluded, so net profitability is incomplete.', 'Wilson intervals assume independent trades; serial dependence and strategy selection add uncertainty.', 'Sum of trade bps is not a portfolio return.', 'All 24 training candidates disclosed; only the training-selected candidate is evaluated on the held-out period.'],sources=['https://www.bollingerbands.com/bollinger-band-rules','https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf'])
    (ROOT/'winrate_search.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='candidates'},indent=2))


if __name__=='__main__':
    run()
