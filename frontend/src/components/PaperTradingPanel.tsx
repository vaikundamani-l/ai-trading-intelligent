'use client';

import React, { useState } from 'react';
import { PaperPortfolio, MarketState } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { formatISTFromUTC } from '@/lib/dateUtils';
import { RotateCcw, ShieldAlert, CheckCircle2 } from 'lucide-react';

interface PaperTradingPanelProps {
  portfolio: PaperPortfolio | null;
  market: MarketState | null;
  onRefresh?: () => void;
}

export const PaperTradingPanel: React.FC<PaperTradingPanelProps> = ({
  portfolio,
  market,
  onRefresh,
}) => {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [orderMsg, setOrderMsg] = useState<string>('');

  const [stopPercent, setStopPercent] = useState(0.3);
  const [targetR, setTargetR] = useState(1.8);
  const safeToTrade = !!portfolio && market?.connection_status === "LIVE" && market.is_data_safe && !portfolio?.is_halted && !portfolio?.is_cooldown_active;
  const lastPrice = market?.last_price || 80000;
  const currentEquity = portfolio?.current_equity || 10000;
  const totalReturn = portfolio?.total_return_pct || 0;
  const winRate = portfolio?.win_rate_pct || 0;
  const openPos = portfolio?.open_position;

  const executableExit = openPos?.direction === 1 ? market?.best_bid : market?.best_ask;
  const unrealized = market?.connection_status === "LIVE" && openPos && executableExit ? openPos.direction * (executableExit - openPos.entry_price) * openPos.contracts * 0.001 : null;

  // Manual order submission
  const handlePlaceOrder = async (manualDirection: number) => {
    if (!safeToTrade || isSubmitting) return;
    setIsSubmitting(true);
    setOrderMsg('');
    try {
      const stopDist = lastPrice * stopPercent / 100; // 0.3% stop
      const targetDist = stopDist * targetR;
      const stopPrice = manualDirection === 1 ? lastPrice - stopDist : lastPrice + stopDist;
      const targetPrice = manualDirection === 1 ? lastPrice + targetDist : lastPrice - targetDist;

      const { data, ok, error } = await apiFetch<{id: number}>('/api/paper-trade/order', {
        method: 'POST',
        body: JSON.stringify({
          direction: manualDirection,
          entry_price: lastPrice,
          stop_loss: stopPrice,
          take_profit: targetPrice,
        }),
      });

      if (!ok || !data) {
        setOrderMsg(`Order rejected: ${error || 'Check risk limits'}`);
      } else {
        setOrderMsg(`Paper position opened successfully (#${data.id})`);
        if (onRefresh) onRefresh();
      }
    } catch (e: unknown) {
      setOrderMsg(`Error placing order: ${e instanceof Error ? e.message : "Request failed"}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <RotateCcw className="w-6 h-6 text-cyan-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Paper Trading Simulation & Virtual Portfolio
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl font-mono">
            Zero-risk execution simulation environment. Fills use real Delta Exchange India live bid/ask quotes with
            conservative taker fees (11.8 bps roundtrip) and adverse slippage. No real capital at risk.
          </p>
        </div>

        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs font-mono text-amber-400 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4" />
          <span>SIMULATED PAPER TRADING — NOT REAL MONEY</span>
        </div>
      </div>

      {orderMsg && (
        <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-lg text-xs font-mono text-cyan-400 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{orderMsg}</span>
        </div>
      )}

      <div className="p-4 rounded-xl border border-cyan-500/30 bg-cyan-950/20 text-sm space-y-3">
        <h2 className="font-bold text-cyan-300">Live paper trading · virtual funds</h2>
        <p className="text-gray-400">Automatic entries require all five setup checks. Manual trades use live quotes with risk limits.</p>
        <div className="flex flex-wrap gap-5">
          <label>Stop distance (%) <input aria-label="Stop distance percent" type="number" min="0.15" max="0.8" step="0.05" value={stopPercent} onChange={e => setStopPercent(Math.min(0.8, Math.max(0.15, Number(e.target.value))))} className="w-20 p-2 bg-slate-900 rounded" /></label>
          <label>Target multiple (R) <input aria-label="Target risk multiple" type="number" min="1.2" max="3" step="0.1" value={targetR} onChange={e => setTargetR(Math.min(3, Math.max(1.2, Number(e.target.value))))} className="w-20 p-2 bg-slate-900 rounded" /></label>
          <span className={safeToTrade ? 'text-emerald-400' : 'text-amber-400'}>{safeToTrade ? 'Live quotes available' : 'New entries blocked — check feed and risk status'}</span>
        </div>
        {openPos && <p>Unrealized P&amp;L before fees: {unrealized === null ? 'Unavailable' : `$${unrealized.toFixed(2)}`} · Maximum hold: 25 minutes</p>}
      </div>
      {/* Portfolio Equity Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 font-mono">
        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Simulated Equity</span>
          <span className="text-xl font-bold text-white mt-1 block">
            ${currentEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Total Return</span>
          <span
            className={`text-xl font-bold mt-1 block ${
              totalReturn >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {totalReturn >= 0 ? '+' : ''}
            {totalReturn.toFixed(2)}%
          </span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Win Rate</span>
          <span className="text-xl font-bold text-cyan-400 mt-1 block">
            {winRate.toFixed(1)}%
          </span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Profit Factor</span>
          <span className="text-xl font-bold text-emerald-400 mt-1 block">
            {portfolio?.profit_factor ? portfolio.profit_factor.toFixed(2) : '—'}
          </span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Max Drawdown</span>
          <span className="text-xl font-bold text-rose-400 mt-1 block">
            {portfolio?.max_drawdown_pct ? portfolio.max_drawdown_pct.toFixed(2) : '0.00'}%
          </span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-[11px] text-gray-400 block">Net Expectancy</span>
          <span className="text-xl font-bold text-gray-300 mt-1 block">
            {portfolio?.average_net_expectancy_bps ? `${portfolio.average_net_expectancy_bps.toFixed(1)} bp` : '0 bp'}
          </span>
        </div>
      </div>

      {/* Open Position Card */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
        <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider mb-4 flex items-center justify-between">
          <span>Active Simulated Position</span>
          {openPos ? (
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
              POSITION OPEN
            </span>
          ) : (
            <span className="text-gray-500 text-[11px]">FLAT (No Open Positions)</span>
          )}
        </h3>

        {openPos ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
            <div className="bg-[#121721] p-3 rounded border border-[#1e2638]">
              <span className="text-gray-400 block text-[10px]">Direction & Size:</span>
              <span
                className={`font-bold text-sm ${
                  openPos.direction === 1 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {openPos.direction === 1 ? 'BUY / LONG' : 'SELL / SHORT'} ({openPos.contracts} lots)
              </span>
            </div>

            <div className="bg-[#121721] p-3 rounded border border-[#1e2638]">
              <span className="text-gray-400 block text-[10px]">Entry Price:</span>
              <span className="text-white font-bold text-sm">${openPos.entry_price.toFixed(1)}</span>
            </div>

            <div className="bg-[#121721] p-3 rounded border border-[#1e2638]">
              <span className="text-gray-400 block text-[10px]">Stop Loss:</span>
              <span className="text-rose-400 font-bold text-sm">${openPos.stop_loss.toFixed(1)}</span>
            </div>

            <div className="bg-[#121721] p-3 rounded border border-[#1e2638]">
              <span className="text-gray-400 block text-[10px]">Take Profit:</span>
              <span className="text-emerald-400 font-bold text-sm">${openPos.take_profit.toFixed(1)}</span>
            </div>
          </div>
        ) : (
          <div className="p-6 text-center border border-dashed border-[#1e2638] rounded-lg">
            <p className="text-xs font-mono text-gray-400">
              No active paper position. Positions are automatically opened when valid SBR-5 signals trigger,
              or you can manually open a simulated trade below.
            </p>

            <div className="mt-4 flex items-center justify-center gap-3">
              <button
                onClick={() => {
                  handlePlaceOrder(1);
                }}
                disabled={isSubmitting || !safeToTrade}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-black font-mono font-bold text-xs uppercase rounded transition-all shadow-lg shadow-emerald-500/20"
              >
                Simulate Paper BUY
              </button>

              <button
                onClick={() => {
                  handlePlaceOrder(-1);
                }}
                disabled={isSubmitting || !safeToTrade}
                className="px-4 py-2 bg-rose-500 hover:bg-rose-400 text-white font-mono font-bold text-xs uppercase rounded transition-all shadow-lg shadow-rose-500/20"
              >
                Simulate Paper SELL
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Closed Trades History Table */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
        <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider mb-4">
          Simulated Closed Trades History ({portfolio?.closed_trades?.length || 0})
        </h3>

        <div className="overflow-x-auto max-h-[350px]">
          <table className="w-full text-left font-mono text-xs">
            <thead className="sticky top-0 bg-[#121721] border-b border-[#1e2638] text-gray-400">
              <tr>
                <th className="py-2 px-3">Entry Time (IST)</th>
                <th className="py-2 px-3">Side</th>
                <th className="py-2 px-3">Entry</th>
                <th className="py-2 px-3">Exit</th>
                <th className="py-2 px-3">Exit Reason</th>
                <th className="py-2 px-3">Fees</th>
                <th className="py-2 px-3">Net Return</th>
                <th className="py-2 px-3">P&L ($)</th>
                <th className="py-2 px-3">Equity After</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#161d2b]">
              {portfolio?.closed_trades && portfolio.closed_trades.length > 0 ? (
                portfolio.closed_trades.map((t, idx) => {
                  const isWin = (t.pnl_usd || 0) > 0;
                  return (
                    <tr key={idx} className="hover:bg-[#121721]">
                      <td className="py-2 px-3 text-cyan-300 font-mono text-[11px] whitespace-nowrap">{formatISTFromUTC(t.entry_time)}</td>
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
                      <td className="py-2 px-3 text-white">${t.entry_price.toFixed(1)}</td>
                      <td className="py-2 px-3 text-white">${t.exit_price?.toFixed(1) || '—'}</td>
                      <td className="py-2 px-3 text-gray-400 text-[11px]">{t.exit_reason || '—'}</td>
                      <td className="py-2 px-3 text-amber-400">{t.fees_bps?.toFixed(1) || '11.8'} bp</td>
                      <td className={`py-2 px-3 font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {t.net_bps ? `${t.net_bps > 0 ? '+' : ''}${t.net_bps.toFixed(1)} bp` : '—'}
                      </td>
                      <td className={`py-2 px-3 font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                        ${t.pnl_usd?.toFixed(2) || '0.00'}
                      </td>
                      <td className="py-2 px-3 text-gray-300">${t.equity_after?.toFixed(2) || '—'}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-gray-500">
                    No closed paper trades yet.
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
