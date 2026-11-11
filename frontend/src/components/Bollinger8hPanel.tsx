'use client';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';

interface Report {
  signal: { action: string; completed_bars: number; atr?: number; lower_band?: number; entry_price?: number; stop_loss?: number; take_profit?: number; checks?: Record<string, boolean>; reasons: string[] };
  simulation: { total_trades: number; net_bps_sum: number; assumptions: string; trades: {entry_time: number; entry: number; exit: number; reason: string; net_bps: number}[] };
}

export function Bollinger8hPanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    async function load() {
      const result = await apiFetch<Report>('/api/strategies/bollinger8h');
      if (active) { setReport(result.data); setError(result.error || ''); }
    }
    void load();
    const timer = setInterval(load, 60000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  return <section className="bg-[#0e131d] border border-cyan-500/30 rounded-xl p-5 space-y-4">
    <div className="flex justify-between gap-3"><h2 className="text-white font-mono font-bold">BB-8H · BOLLINGER RE-ENTRY</h2><span className="text-amber-300 text-xs">RESEARCH · LONG ONLY</span></div>
    <p className="text-gray-400 text-xs">UTC 8H · SMA 20 · deviation 1.8 · Wilder ATR 14 · SL/TP ±2 ATR · 96h maximum hold · 1× simulation</p>
    <p className="text-gray-400 text-xs">A closes below its lower band, B closes green inside its own band, then enter at C open. SELL means exit the long position.</p>
    <p className="text-cyan-200 text-xs">முந்தைய candle Lower Band கீழே close → அடுத்த green candle Band உள்ளே close → அடுத்த candle open-ல் Long. Wick மட்டும் போதாது; candle முழுவதும் முடியும் வரை காத்திருக்கவும்.</p>
    {error && <p className="text-rose-300 text-xs">{error}</p>}
    {!report && !error && <p className="text-gray-400 text-xs">Loading complete 8-hour candles…</p>}
    {report && <>
      <div className="text-cyan-300 font-mono">{report.signal.action} · {report.signal.completed_bars} completed bars</div>
      <div className="grid sm:grid-cols-2 gap-2">{Object.entries(report.signal.checks || {}).map(([key, pass]) => <div key={key} className="bg-[#121721] p-2 text-xs text-gray-300 flex justify-between gap-2"><span>{key.replaceAll('_', ' ')}</span><b className={pass ? 'text-emerald-400' : 'text-amber-400'}>{pass ? 'PASS' : 'WAIT'}</b></div>)}</div>
      <p className="text-xs text-gray-300">ATR: {report.signal.atr?.toFixed(2) || '—'} · Lower band: {report.signal.lower_band?.toFixed(2) || '—'} · Entry: {report.signal.entry_price?.toFixed(2) || '—'} · SL: {report.signal.stop_loss?.toFixed(2) || '—'} · TP: {report.signal.take_profit?.toFixed(2) || '—'}</p>
      {report.signal.reasons.map(reason => <p key={reason} className="text-xs text-gray-400">{reason}</p>)}
      <p className="text-xs text-gray-300">Historical simulation: {report.simulation.total_trades} closed trades · Sum of trade returns: {report.simulation.net_bps_sum.toFixed(1)} bps</p>
      <p className="text-xs text-amber-300">{report.simulation.assumptions}</p>
      <div className="overflow-auto"><table className="w-full text-xs text-gray-400"><thead><tr><th className="text-left">Entry UTC</th><th>Entry</th><th>Exit</th><th>Reason</th><th>Net bps</th></tr></thead><tbody>{report.simulation.trades.slice(-10).map(t => <tr key={t.entry_time} className="border-t border-[#1e2638]"><td className="py-2">{new Date(t.entry_time*1000).toISOString().slice(0,16)}</td><td>{t.entry.toFixed(1)}</td><td>{t.exit.toFixed(1)}</td><td>{t.reason}</td><td>{t.net_bps.toFixed(1)}</td></tr>)}</tbody></table></div>
    </>}
  </section>;
}
