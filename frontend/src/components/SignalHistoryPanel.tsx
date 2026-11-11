'use client';

import React, { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { formatISTFromUTC } from '@/lib/dateUtils';
import { History, Search, RefreshCw } from 'lucide-react';

export const SignalHistoryPanel: React.FC = () => {
  const [signals, setSignals] = useState<(import('@/lib/types').SignalDecision & {id: number})[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [filterAction, setFilterAction] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchHistory = async () => {
    setIsLoading(true);
    const { data, ok } = await apiFetch<(import('@/lib/types').SignalDecision & {id: number})[]>('/api/signals/history?limit=100');
    if (ok && data) {
      setSignals(data);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    const initial = setTimeout(fetchHistory, 0);
    return () => clearTimeout(initial);
  }, []);

  const filteredSignals = signals.filter((s) => {
    if (filterAction !== 'ALL' && s.action !== filterAction) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        s.strategy?.toLowerCase().includes(q) ||
        s.action?.toLowerCase().includes(q) ||
        s.datetime_utc?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <History className="w-6 h-6 text-cyan-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Persistent Signal History & Recommendation Ledger
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl font-mono">
            Unmodified record of all generated quant signals. Every active setup preserves its original entry, stop,
            target, fee calculation, and reasoning rather than rewriting history after observing price outcomes.
          </p>
        </div>

        <button
          onClick={fetchHistory}
          className="flex items-center gap-2 px-4 py-2 bg-[#121721] hover:bg-[#1a2233] text-gray-300 border border-[#1e2638] rounded-lg text-xs font-mono transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh Ledger
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-[#0e131d] border border-[#1e2638] rounded-xl font-mono text-xs">
        <div className="flex items-center gap-2">
          {['ALL', 'BUY', 'SELL', 'WAIT'].map((act) => (
            <button
              key={act}
              onClick={() => setFilterAction(act)}
              className={`px-3 py-1.5 rounded transition-colors ${
                filterAction === act
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 font-bold'
                  : 'text-gray-400 hover:text-white bg-[#121721] border border-[#1e2638]'
              }`}
            >
              {act}
            </button>
          ))}
        </div>

        <div className="relative w-64">
          <Search className="w-4 h-4 text-gray-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search signals..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#121721] border border-[#1e2638] rounded pl-9 pr-3 py-1.5 text-white"
          />
        </div>
      </div>

      {/* Signals Ledger Table */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto max-h-[500px]">
          <table className="w-full text-left font-mono text-xs">
            <thead className="sticky top-0 bg-[#121721] border-b border-[#1e2638] text-gray-400">
              <tr>
                <th className="py-2.5 px-3">ID</th>
                <th className="py-2.5 px-3">Time (IST)</th>
                <th className="py-2.5 px-3">Strategy</th>
                <th className="py-2.5 px-3">Action</th>
                <th className="py-2.5 px-3">Entry ($)</th>
                <th className="py-2.5 px-3">Stop Loss</th>
                <th className="py-2.5 px-3">Target (1.8R)</th>
                <th className="py-2.5 px-3">Net R:R</th>
                <th className="py-2.5 px-3">Fees & Slip</th>
                <th className="py-2.5 px-3">Regime</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#161d2b]">
              {filteredSignals.length > 0 ? (
                filteredSignals.map((s) => (
                  <tr key={s.id} className="hover:bg-[#121721] transition-colors">
                    <td className="py-2.5 px-3 text-gray-500">#{s.id}</td>
                    <td className="py-2.5 px-3 text-cyan-300 font-mono text-[11px] whitespace-nowrap">{formatISTFromUTC(s.datetime_utc)}</td>
                    <td className="py-2.5 px-3 text-cyan-400 font-semibold">{s.strategy}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          s.action === 'BUY'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : s.action === 'SELL'
                            ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                            : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                        }`}
                      >
                        {s.action}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-white font-bold">
                      {s.entry_price ? `$${s.entry_price.toFixed(1)}` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-rose-400">
                      {s.stop_loss ? `$${s.stop_loss.toFixed(1)}` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-emerald-400">
                      {s.take_profit ? `$${s.take_profit.toFixed(1)}` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-cyan-400 font-bold">
                      {s.risk_reward ? `${s.risk_reward.toFixed(2)}:1` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-amber-400">
                      {s.estimated_fees_bps ? `${(s.estimated_fees_bps + (s.estimated_slippage_bps || 2)).toFixed(1)} bp` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-gray-400">{s.market_regime || 'RANGING'}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-gray-500">
                    No signals found matching your filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
