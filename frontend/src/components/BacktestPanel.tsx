'use client';

import React, { useState } from 'react';
import { BacktestResults } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { formatISTFromUTC } from '@/lib/dateUtils';
import { LineChart, Play, AlertTriangle } from 'lucide-react';

export const BacktestPanel: React.FC = () => {
  const [params, setParams] = useState({
    lookback: 24,
    vol_lookback: 24,
    atr_lookback: 14,
    volume_multiplier: 1.25,
    sweep_atr: 0.12,
    reclaim_atr: 0.10,
    target_r: 1.80,
    slip_per_leg_bps: 1.0,
    initial_equity: 10000.0,
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>('');

  const handleRun = async () => {
    setIsLoading(true);
    setErrorMsg('');
    try {
      const { data, ok, error } = await apiFetch<BacktestResults>('/api/backtest/run', {
        method: 'POST',
        body: JSON.stringify(params),
      });
      if (!ok || !data) {
        setErrorMsg(error || 'Backtest failed');
      } else {
        setResults(data);
      }
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Network error running backtest');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <LineChart className="w-6 h-6 text-cyan-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Historical Backtesting & Cost Sensitivity Engine
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl font-mono">
            Execute conservative bar-level backtests on genuine Delta Exchange India BTCUSD historical candles.
            Uses next-bar open execution, conservative stop/target precedence, 2-leg taker fees with 18% GST, and adverse slippage.
          </p>
        </div>

        <button
          onClick={handleRun}
          disabled={isLoading}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-black font-mono font-bold text-xs uppercase tracking-wider rounded-lg shadow-lg shadow-cyan-500/20 transition-all disabled:opacity-50"
        >
          <Play className={`w-4 h-4 fill-current ${isLoading ? 'animate-spin' : ''}`} />
          {isLoading ? 'Running Backtest...' : 'Execute Backtest'}
        </button>
      </div>

      {errorMsg && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs font-mono text-rose-400 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Parameter Inputs Grid */}
      <div className="p-5 bg-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl">
        <h3 className="text-xs font-bold font-mono text-gray-300 uppercase tracking-wider mb-4">
          Research Parameters (SBR-5 Specification)
        </h3>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4 font-mono text-xs">
          <div>
            <label className="text-gray-400 block mb-1">Range Lookback (Bars)</label>
            <input
              type="number"
              value={params.lookback}
              onChange={(e) => setParams({ ...params, lookback: parseInt(e.target.value) || 24 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">ATR Lookback</label>
            <input
              type="number"
              value={params.atr_lookback}
              onChange={(e) => setParams({ ...params, atr_lookback: parseInt(e.target.value) || 14 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Volume Mult (&ge;)</label>
            <input
              type="number"
              step="0.05"
              value={params.volume_multiplier}
              onChange={(e) => setParams({ ...params, volume_multiplier: parseFloat(e.target.value) || 1.25 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Sweep ATR Threshold</label>
            <input
              type="number"
              step="0.01"
              value={params.sweep_atr}
              onChange={(e) => setParams({ ...params, sweep_atr: parseFloat(e.target.value) || 0.12 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Target R Multiple</label>
            <input
              type="number"
              step="0.1"
              value={params.target_r}
              onChange={(e) => setParams({ ...params, target_r: parseFloat(e.target.value) || 1.8 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Slippage Per Leg (bps)</label>
            <input
              type="number"
              step="0.5"
              value={params.slip_per_leg_bps}
              onChange={(e) => setParams({ ...params, slip_per_leg_bps: parseFloat(e.target.value) || 1.0 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Initial Capital ($)</label>
            <input
              type="number"
              value={params.initial_equity}
              onChange={(e) => setParams({ ...params, initial_equity: parseFloat(e.target.value) || 10000 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>
        </div>
      </div>

      {/* Results Display */}
      {results && (
        <div className="space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 font-mono">
            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Total Completed Trades</span>
              <span className="text-xl font-bold text-white mt-1 block">{results.trades_count}</span>
            </div>

            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Win Rate</span>
              <span
                className={`text-xl font-bold mt-1 block ${
                  results.win_rate_pct >= 50 ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {results.win_rate_pct.toFixed(1)}%
              </span>
            </div>

            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Net Strategy Return</span>
              <span
                className={`text-xl font-bold mt-1 block ${
                  results.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {results.total_return_pct >= 0 ? '+' : ''}
                {results.total_return_pct.toFixed(2)}%
              </span>
            </div>

            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Buy & Hold Return</span>
              <span className="text-xl font-bold text-gray-300 mt-1 block">
                {results.buy_and_hold_return_pct >= 0 ? '+' : ''}
                {results.buy_and_hold_return_pct.toFixed(2)}%
              </span>
            </div>

            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Profit Factor</span>
              <span className="text-xl font-bold text-cyan-400 mt-1 block">
                {results.profit_factor ? results.profit_factor.toFixed(2) : 'N/A'}
              </span>
            </div>

            <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
              <span className="text-[11px] text-gray-400 block">Max Drawdown</span>
              <span className="text-xl font-bold text-rose-400 mt-1 block">
                {results.max_drawdown_pct.toFixed(2)}%
              </span>
            </div>
          </div>

          {/* Cost Sensitivity Stress Test Table */}
          <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
            <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider mb-3">
              Cost Sensitivity & Friction Stress Test
            </h3>
            <p className="text-xs text-gray-400 font-mono mb-4">
              Evaluates net performance across different execution slippage assumptions (from 0 bp to 5 bp per leg).
            </p>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-[#1e2638] text-gray-400">
                    <th className="py-2 px-3">Assumed Slippage</th>
                    <th className="py-2 px-3">Round-Trip Friction</th>
                    <th className="py-2 px-3">Net P&L ($)</th>
                    <th className="py-2 px-3">Net Return (%)</th>
                    <th className="py-2 px-3">Viability Assessment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#161d2b]">
                  {results.cost_sensitivity.map((cs, idx) => {
                    const totalFriction = 11.8 + cs.slippage_bps * 2;
                    const isProfitable = cs.net_return_pct > 0;
                    return (
                      <tr key={idx} className="hover:bg-[#121721]">
                        <td className="py-2.5 px-3 text-white font-bold">{cs.slippage_bps.toFixed(1)} bp / leg</td>
                        <td className="py-2.5 px-3 text-gray-300">{totalFriction.toFixed(1)} bps</td>
                        <td className={`py-2.5 px-3 font-semibold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                          ${cs.total_pnl_usd.toFixed(2)}
                        </td>
                        <td className={`py-2.5 px-3 font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {cs.net_return_pct >= 0 ? '+' : ''}
                          {cs.net_return_pct.toFixed(2)}%
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              isProfitable
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                            }`}
                          >
                            {isProfitable ? 'Survives Friction' : 'Subsumed by Friction'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Trade Log Table */}
          <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
            <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider mb-3">
              Detailed Historical Trade Log ({results.trades.length} Trades)
            </h3>

            <div className="overflow-x-auto max-h-[400px]">
              <table className="w-full text-left font-mono text-xs">
                <thead className="sticky top-0 bg-[#121721] border-b border-[#1e2638] text-gray-400">
                  <tr>
                    <th className="py-2 px-3">Entry Time (IST)</th>
                    <th className="py-2 px-3">Side</th>
                    <th className="py-2 px-3">Entry Price</th>
                    <th className="py-2 px-3">Exit Price</th>
                    <th className="py-2 px-3">Exit Reason</th>
                    <th className="py-2 px-3">Duration</th>
                    <th className="py-2 px-3">Fees</th>
                    <th className="py-2 px-3">Net bps</th>
                    <th className="py-2 px-3">P&L ($)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#161d2b]">
                  {results.trades.map((t, idx) => {
                    const isWin = t.pnl_usd > 0;
                    return (
                      <tr key={idx} className="hover:bg-[#121721]">
                        <td className="py-2 px-3 text-cyan-300 font-mono text-[11px] whitespace-nowrap">{formatISTFromUTC(t.entry_utc)}</td>
                        <td className="py-2 px-3">
                          <span
                            className={`px-1.5 py-0.5 rounded font-bold text-[10px] ${
                              t.direction === 1
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-rose-500/10 text-rose-400'
                            }`}
                          >
                            {t.direction === 1 ? 'BUY' : 'SELL'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-white">${t.entry.toFixed(1)}</td>
                        <td className="py-2 px-3 text-white">${t.exit.toFixed(1)}</td>
                        <td className="py-2 px-3 text-gray-400 text-[11px]">{t.reason}</td>
                        <td className="py-2 px-3 text-gray-400">{t.holding_bars * 5}m</td>
                        <td className="py-2 px-3 text-amber-400">{t.fees_bps.toFixed(1)} bp</td>
                        <td className={`py-2 px-3 font-semibold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {t.net_bps >= 0 ? '+' : ''}{t.net_bps.toFixed(1)} bp
                        </td>
                        <td className={`py-2 px-3 font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                          ${t.pnl_usd.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
