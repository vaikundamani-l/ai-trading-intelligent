'use client';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { MarketState, SignalDecision } from '@/lib/types';

type SlowReport = {generated_at: number; signal: {action: string; timeframe_minutes: number; completed_bars: number; reasons: string[]; valid_until_ts?: number; checks: Record<string, boolean>; next_close_ts?: number; entry_price?: number; stop_loss?: number; take_profit?: number}; stress_tests: {deviation: number; cost_bps: number; trades: number; net_bps_sum: number}[]};
const price = (value?: number) => value ? `$${value.toLocaleString('en-US', {maximumFractionDigits: 1})}` : '—';
const checkLabels: Record<string,string> = {previous_close_below_band:'A closed below its band',current_close_reentered:'B closed back inside',current_candle_green:'B closed green',entry_within_15_minutes:'Entry window still open',feed_live:'Feed is live',safe_feed:'Fresh, safe exchange feed',safe_quote:'Valid bid / ask',spread_within_limit:'Spread ≤ 2 bps',risk_governor_clear:'Risk limits clear'};

export function TradeTimingPanel({signal,market,onChart}: {signal: SignalDecision | null; market: MarketState | null; onChart: (tf:string)=>void}) {
  const [slow,setSlow] = useState<SlowReport | null>(null);
  const [error,setError] = useState('');
  const [now,setNow] = useState(0);
  const [minutes,setMinutes] = useState(480);
  const [custom,setCustom] = useState('60');
  const [customError,setCustomError] = useState('');
  const timeframeLabel = minutes % 60 === 0 ? `${minutes/60}h` : `${minutes}m`;
  useEffect(()=>{
    let active=true;
    const load=async()=>{const response=await apiFetch<SlowReport>(`/api/strategies/bollinger?minutes=${minutes}`);if(active){setSlow(response.ok?response.data:null);setError(response.error || '');}};
    void load();
    const poll=setInterval(load,60000), clock=setInterval(()=>setNow(Date.now()/1000),1000);
    return ()=>{active=false;clearInterval(poll);clearInterval(clock);};
  },[minutes]);
  const safe=market?.connection_status==='LIVE' && market.is_data_safe && market.data_age_sec<=5;
  const fresh=!!signal && now-signal.timestamp<=15 && (!signal.valid_until_ts || now<=signal.valid_until_ts);
  const fastReady=safe && fresh && signal?.quality?.eligible_for_auto_paper && ['BUY','SELL'].includes(signal.action);
  const slowFresh=!!slow && slow.signal.timeframe_minutes===minutes && now-slow.generated_at<75;
  const slowReady=safe && slowFresh && slow?.signal.action==='BUY CANDIDATE' && !!slow.signal.valid_until_ts && now<=slow.signal.valid_until_ts && Object.values(slow.signal.checks).every(Boolean);
  const clockText=(seconds:number)=>{if(!now)return 'syncing…';const remaining=Math.max(0,Math.ceil(seconds-now));return `${Math.floor(remaining/3600)}h ${Math.floor(remaining%3600/60)}m ${remaining%60}s`;};
  return <section className="mb-4 p-4 sm:p-5 rounded-xl border border-[#26354c] bg-gradient-to-r from-[#101b28] to-[#0e131d]">
    <div className="flex flex-wrap justify-between gap-2 mb-4"><div><h2 className="text-lg font-bold text-white">When should I trade?</h2><p className="text-xs text-gray-400 mt-1">Choose the strategy timeframe. Each card explains the next step for paper research.</p></div><span className="text-xs text-cyan-300">எப்போது trade? · எந்த timeframe?</span></div>
    <div className="grid md:grid-cols-2 gap-3">
      <article className="rounded-lg border border-[#26354c] bg-[#0a1019] p-4">
        <div className="flex justify-between text-xs text-gray-400"><span>SBR-5 · FAST SETUP</span><button className="text-cyan-300 underline" onClick={()=>onChart('5m')}>View 5m chart ↗</button></div>
        <div className={`text-3xl font-black mt-3 ${fastReady ? signal?.action==='BUY'?'text-emerald-400':'text-rose-400':'text-amber-300'}`}>{fastReady ? signal?.action==='BUY'?'BUY / LONG':'SELL / SHORT':'WAIT'}</div>
        <p className="text-sm text-white mt-2">Use the <b>5-minute</b> chart · hold up to 25 minutes</p>
        <p className="text-xs text-gray-400 mt-2">{fastReady?'All setup and safety checks pass. Review entry, stop and target below.':!safe?'Waiting for a fresh, safe feed.':!fresh?'Waiting for an updated engine decision.':signal?.reasons?.[0] || 'Waiting for a completed sweep-and-reclaim setup.'}</p>
        <p className="text-xs text-cyan-200 mt-2">5 நிமிட candle முடிந்து எல்லா checks PASS ஆனால் மட்டும் paper trade.</p>
        <div className="grid grid-cols-3 gap-2 text-xs mt-4 text-gray-400"><span>Entry<br/><b className="text-white">{fastReady?price(signal?.entry_price):'—'}</b></span><span>Stop<br/><b className="text-rose-300">{fastReady?price(signal?.stop_loss):'—'}</b></span><span>Target<br/><b className="text-emerald-300">{fastReady?price(signal?.take_profit):'—'}</b></span></div>
        <p className="text-xs text-gray-500 mt-3">Next 5m close in {clockText((Math.floor(now/300)+1)*300)} · candle timer, not a promised entry</p>
      </article>
      <article className="rounded-lg border border-[#26354c] bg-[#0a1019] p-4">
        <div className="flex justify-between text-xs text-gray-400"><span>BB RE-ENTRY · {timeframeLabel.toUpperCase()}</span><span className="text-amber-300">Research only</span></div>
        <div className="flex flex-wrap gap-2 mt-3" aria-label="Strategy timeframe">{[15,45,240,480].map(value=><button key={value} aria-pressed={minutes===value} onClick={()=>setMinutes(value)} className={`px-3 py-1.5 rounded border text-xs ${minutes===value?'border-cyan-400 text-cyan-200 bg-cyan-500/10':'border-[#26354c] text-gray-400'}`}>{value%60===0?`${value/60}h`:`${value}m`}</button>)}</div>
        <form className="flex flex-wrap gap-2 items-center mt-2" onSubmit={event=>{event.preventDefault();const value=Number(custom);if(!Number.isInteger(value)||value<5||value>1440||value%5){setCustomError('Use multiples of 5 minutes, from 5 to 1440.');return;}setCustomError('');setMinutes(value);}}><label className="text-xs text-gray-400" htmlFor="custom-timeframe">Custom minutes</label><input id="custom-timeframe" type="number" min="5" max="1440" step="5" value={custom} onChange={event=>setCustom(event.target.value)} className="w-20 bg-[#121721] text-white border border-[#26354c] p-1 rounded text-xs"/><button className="text-xs text-cyan-300 px-2 py-1 border border-[#26354c] rounded" type="submit">Apply</button></form>
        {customError && <p role="alert" className="text-xs text-rose-300 mt-1">{customError}</p>}
        <div className={`text-3xl font-black mt-3 ${slowReady?'text-emerald-400':'text-amber-300'}`}>{slowReady?'BUY CANDIDATE':'WAIT'}</div>
        <p className="text-sm text-white mt-2">Use the <b>{timeframeLabel}</b> signal · hold up to 12 candles ({minutes/5} hours)</p>
        <p className="text-xs text-gray-400 mt-2">{error?'Data unavailable. Retrying automatically.':!slowFresh?'Updating timeframe evidence…':slowReady?'Completed re-entry confirmed. Forward paper observation only.':slow && slow.signal.completed_bars<21?slow.signal.reasons[0]:'Wait for A below band → B green inside band → next candle open.'}</p>
        <p className="text-xs text-cyan-200 mt-2">{timeframeLabel} candle முடியும் வரை காத்திருக்கவும். SELL என்பது Long exit; Short signal இல்லை.</p>
        <div className="grid grid-cols-3 gap-2 text-xs mt-4 text-gray-400"><span>Entry<br/><b className="text-white">{slowReady?price(slow?.signal.entry_price):'—'}</b></span><span>Stop<br/><b className="text-rose-300">{slowReady?price(slow?.signal.stop_loss):'—'}</b></span><span>Target<br/><b className="text-emerald-300">{slowReady?price(slow?.signal.take_profit):'—'}</b></span></div>
        <p className="text-xs text-gray-500 mt-3">Next {timeframeLabel} close in {clockText((Math.floor(now/(minutes*60))+1)*minutes*60)} · UTC epoch-aligned candles</p>
        <details className="mt-3 text-xs text-gray-400"><summary className="cursor-pointer text-cyan-300">Why wait? See checks & research</summary><div className="mt-2 space-y-2">{Object.entries(slow?.signal.checks || {}).map(([key,pass])=><div className="flex justify-between gap-3" key={key}><span>{checkLabels[key] || key}</span><b className={pass?'text-emerald-400':'text-amber-300'}>{pass?'PASS':'WAIT'}</b></div>)}<p>Nearby band settings and doubled costs are checked without selecting a new winner. Funding and out-of-sample validation are still required.</p>{slow?.stress_tests?.map(t=><p key={`${t.deviation}-${t.cost_bps}`}>Band {t.deviation} · costs {t.cost_bps} bps · {t.trades} trades · summed {t.net_bps_sum.toFixed(1)} bps</p>)}</div></details>
      </article>
    </div>
    <p className="text-xs text-gray-500 mt-3">Green/red timeframe dots show trend context. Only a completed strategy setup can qualify a suggestion. 1s trend is a momentum display.</p>
  </section>;
}
