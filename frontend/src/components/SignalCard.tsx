'use client';

import React, { useState } from 'react';
import { SignalDecision, MarketState } from '@/lib/types';
import {
  TrendingUp,
  TrendingDown,
  PauseCircle,
  AlertTriangle,
  Clock,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

interface SignalCardProps {
  signal: SignalDecision | null;
  market: MarketState | null;
  onPaperExecute?: () => void;
}

export const SignalCard: React.FC<SignalCardProps> = ({
  signal,
  market,
  onPaperExecute,
}) => {
  const [showDetails, setShowDetails] = useState<boolean>(true);

  const action = signal?.action || 'WAIT';
  const isBuy = action === 'BUY';
  const isSell = action === 'SELL';
  const isHalted = action.startsWith('HALTED') || market?.connection_status !== 'LIVE';
  const isWait = !isBuy && !isSell && !isHalted;

  return (
    <div className="flex flex-col bg-[#0e131d] border border-[#1e2638] rounded-xl overflow-hidden shadow-2xl">
      {/* Header */}
      <div className="px-4 py-3 bg-[#121721] border-b border-[#1e2638] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
          <h2 className="text-xs font-bold font-mono tracking-wider text-white uppercase">
            Trade Suggestion & Evidence
          </h2>
        </div>
        <span className="text-[11px] font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
          {signal?.strategy || 'ALPHA-5: SBR-5'}
        </span>
      </div>

      {/* Main Signal Display Banner */}
      <div
        className={`p-5 flex flex-col items-center justify-center text-center border-b transition-all ${
          isBuy
            ? 'bg-gradient-to-b from-emerald-950/40 to-[#0e131d] border-emerald-500/40'
            : isSell
            ? 'bg-gradient-to-b from-rose-950/40 to-[#0e131d] border-rose-500/40'
            : isHalted
            ? 'bg-gradient-to-b from-red-950/40 to-[#0e131d] border-red-500/40'
            : 'bg-gradient-to-b from-slate-900/40 to-[#0e131d] border-[#1e2638]'
        }`}
      >
        <div className="flex items-center gap-3">
          {isBuy && (
            <div className="p-3 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 shadow-lg shadow-emerald-500/20">
              <TrendingUp className="w-8 h-8" />
            </div>
          )}
          {isSell && (
            <div className="p-3 rounded-full bg-rose-500/20 border border-rose-500/40 text-rose-400 shadow-lg shadow-rose-500/20">
              <TrendingDown className="w-8 h-8" />
            </div>
          )}
          {isHalted && (
            <div className="p-3 rounded-full bg-red-500/20 border border-red-500/40 text-red-400">
              <AlertTriangle className="w-8 h-8" />
            </div>
          )}
          {isWait && (
            <div className="p-3 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <PauseCircle className="w-8 h-8" />
            </div>
          )}

          <div className="text-left">
            <div
              className={`text-2xl font-black font-mono tracking-tight ${
                isBuy
                  ? 'text-emerald-400'
                  : isSell
                  ? 'text-rose-400'
                  : isHalted
                  ? 'text-red-400'
                  : 'text-amber-400'
              }`}
            >
              {isBuy ? 'BUY / LONG' : isSell ? 'SELL / SHORT' : isHalted ? 'HALTED / UNSAFE' : 'WAIT / NO TRADE'}
            </div>
            <div className="text-xs text-gray-400 font-mono mt-0.5">
              {signal?.status || 'Awaiting completed 5m candle'}
            </div>
          </div>
        </div>

        {/* Action Button for Paper Trading */}
        {(isBuy || isSell) && onPaperExecute && (
          <button
            onClick={onPaperExecute}
            disabled={isHalted || !market?.is_data_safe}
            className={`mt-4 w-full py-2 px-4 rounded-lg font-mono font-bold text-xs uppercase tracking-wider transition-all shadow-lg ${
              isBuy
                ? 'bg-emerald-500 hover:bg-emerald-400 text-black shadow-emerald-500/25'
                : 'bg-rose-500 hover:bg-rose-400 text-white shadow-rose-500/25'
            }`}
          >
            Execute Simulated Paper {isBuy ? 'Buy' : 'Sell'} Order
          </button>
        )}
      </div>

      {signal?.quality && <div className="p-4 border-b border-slate-800 space-y-2 text-xs">
        <strong className={signal.quality.eligible_for_auto_paper ? 'text-emerald-400' : 'text-amber-400'}>{signal.quality.grade}</strong>
        {signal.quality.checks.map(check => <div key={check.label} className="flex justify-between text-gray-300"><span>{check.label}</span><span>{check.passed ? '✓ Pass' : '— Not met'}</span></div>)}
        <p className="text-gray-500">{signal.quality.explanation}</p>
      </div>}
      {/* Target, Stop, and Fee Statistics Grid */}
      {(isBuy || isSell) && (
        <div className="p-4 grid grid-cols-2 gap-3 bg-[#0b0e14] border-b border-[#1e2638] font-mono text-xs">
          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Suggested Entry:</span>
            <span className="text-white font-bold text-sm">
              ${signal?.entry_price?.toLocaleString('en-US', { minimumFractionDigits: 1 }) || '—'}
            </span>
          </div>

          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Target (1.8R):</span>
            <span className="text-emerald-400 font-bold text-sm">
              ${signal?.take_profit?.toLocaleString('en-US', { minimumFractionDigits: 1 }) || '—'}
            </span>
          </div>

          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Stop Loss:</span>
            <span className="text-rose-400 font-bold text-sm">
              ${signal?.stop_loss?.toLocaleString('en-US', { minimumFractionDigits: 1 }) || '—'}
            </span>
          </div>

          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Net Reward / Risk:</span>
            <span className="text-cyan-400 font-bold text-sm">
              {signal?.risk_reward ? `${signal.risk_reward.toFixed(2)} : 1` : '—'}
            </span>
          </div>

          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Taker Fees (2-leg + GST):</span>
            <span className="text-amber-400 font-semibold">
              {signal?.estimated_fees_bps?.toFixed(1) || '11.8'} bps
            </span>
          </div>

          <div className="bg-[#121721] p-2.5 rounded border border-[#1e2638]">
            <span className="text-gray-400 text-[11px] block">Net Reward at Target:</span>
            <span className="text-emerald-400 font-semibold">
              +{signal?.net_reward_bps?.toFixed(1) || '—'} bps
            </span>
          </div>
        </div>
      )}

      {/* Rationale and Risk Breakdown Accordion */}
      <div className="p-4 bg-[#0e131d]">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center justify-between w-full text-xs font-mono text-gray-400 hover:text-white mb-2"
        >
          <span className="font-bold flex items-center gap-1.5 uppercase">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            Decision Intelligence Rationale
          </span>
          {showDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showDetails && (
          <div className="space-y-3 mt-3 text-xs">
            {/* Supporting Reasons */}
            <div className="space-y-1.5">
              <span className="text-[11px] font-mono font-bold text-gray-400 uppercase tracking-wider block">
                Supporting Evidence:
              </span>
              {signal?.reasons && signal.reasons.length > 0 ? (
                signal.reasons.map((r, i) => (
                  <div key={i} className="flex items-start gap-2 text-gray-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                    <span>{r}</span>
                  </div>
                ))
              ) : (
                <div className="text-gray-500 italic">No active setup conditions met</div>
              )}
            </div>

            {/* Invalidation Risks */}
            {signal?.invalidation_risks && signal.invalidation_risks.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-[#1a2233]">
                <span className="text-[11px] font-mono font-bold text-amber-400 uppercase tracking-wider block">
                  Failure & Invalidation Risks:
                </span>
                {signal.invalidation_risks.map((risk, i) => (
                  <div key={i} className="flex items-start gap-2 text-gray-400">
                    <XCircle className="w-3.5 h-3.5 text-rose-400 mt-0.5 shrink-0" />
                    <span>{risk}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer Timing & Safety Gate */}
      <div className="px-4 py-2.5 bg-[#121721] border-t border-[#1e2638] flex items-center justify-between text-[11px] font-mono text-gray-400">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3 text-gray-400" />
          Regime: <span className="text-white font-semibold">{signal?.market_regime || 'RANGING'}</span>
        </span>
        <span className="text-gray-500">
          Max Hold: 25 min (5 bars)
        </span>
      </div>
    </div>
  );
};
