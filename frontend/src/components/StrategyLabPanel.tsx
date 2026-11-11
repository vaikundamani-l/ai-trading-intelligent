'use client';

import React, { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Layers, ShieldCheck, CheckCircle2, Activity } from 'lucide-react';
import { Bollinger8hPanel } from './Bollinger8hPanel';

export const StrategyLabPanel: React.FC = () => {
  const [strategies, setStrategies] = useState<{alpha1_orderflow: {pressure_regime: string; metrics: {order_flow_imbalance: number; trade_flow_imbalance: number}}; alpha2_breakout: {vcr: number; is_compressed: boolean}; alpha3_basis: {basis_bps: number; basis_usd: number; basis_regime: string}; alpha4_dislocation: {status: string}} | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;
    apiFetch<{alpha1_orderflow: {pressure_regime: string; metrics: {order_flow_imbalance: number; trade_flow_imbalance: number}}; alpha2_breakout: {vcr: number; is_compressed: boolean}; alpha3_basis: {basis_bps: number; basis_usd: number; basis_regime: string}; alpha4_dislocation: {status: string}}>('/api/strategies').then(({ data, ok }) => {
      if (isMounted) {
        if (ok && data) setStrategies(data);
        setIsLoading(false);
      }
    });
    return () => { isMounted = false; };
  }, []);

  if (isLoading) return <p className="p-6 text-gray-400">Loading strategy diagnostics…</p>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl">
        <div className="flex items-center gap-2">
          <Layers className="w-6 h-6 text-cyan-400" />
          <h1 className="text-xl font-bold font-mono text-white tracking-wide">
            Quantitative Strategy Lab & Parameter Inspection
          </h1>
        </div>
        <p className="text-xs text-gray-400 mt-1 max-w-3xl font-mono">
          Inspection interface for all 5 research modules specified in Stage 3. Each strategy operates with independent
          cost models, data gates, and failure hypotheses. Unvalidated modules are explicitly tagged as RESEARCH ONLY.
        </p>
      </div>

      {/* Strategies Grid */}
      <Bollinger8hPanel />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ALPHA-5: SBR-5 Sweep and Reclaim (PRIMARY) */}
        <div className="bg-[#0e131d] border-2 border-cyan-500/40 rounded-xl p-5 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-cyan-500 text-black text-[10px] font-mono font-bold px-3 py-1 rounded-bl">
            PRIMARY SPECIFICATION
          </div>

          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-bold font-mono text-white">
              ALPHA-5: SBR-5 SWEEP & RECLAIM
            </h2>
          </div>
          <div className="text-xs text-cyan-400 font-mono mt-1">
            Completed 5-minute Candle Liquidity Formations
          </div>

          <p className="text-xs text-gray-300 mt-3 leading-relaxed">
            Identifies when a 5m bar sweeps the previous 24-candle low or high by at least 0.12 ATR, then reclaims the prior range
            on elevated volume (&ge; 1.25x 24-bar mean). Evaluates next-bar execution at executable ask/bid with 2-leg taker fee (11.8 bps) and slippage.
          </p>

          <div className="mt-4 p-3 bg-[#121721] rounded-lg border border-[#1e2638] font-mono text-xs space-y-1.5">
            <span className="font-bold text-gray-400 text-[11px] block uppercase">Default Research Parameters:</span>
            <div className="grid grid-cols-2 gap-2 text-gray-300">
              <div>Lookback: <span className="text-white">24 bars (2 hours)</span></div>
              <div>ATR Lookback: <span className="text-white">14 periods</span></div>
              <div>Volume Mult: <span className="text-white">&ge; 1.25x</span></div>
              <div>Sweep Distance: <span className="text-white">&ge; 0.12 ATR</span></div>
              <div>Reclaim Window: <span className="text-white">[0.10, 1.20] ATR</span></div>
              <div>Stop Buffer: <span className="text-white">0.10 ATR</span></div>
              <div>Target Multiple: <span className="text-white">1.80 R</span></div>
              <div>Max Holding: <span className="text-white">25 min (5 bars)</span></div>
            </div>
          </div>
        </div>

        {/* ALPHA-1R: Order-Flow Intelligence */}
        <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold font-mono text-white">
              ALPHA-1R: ORDER-FLOW INTELLIGENCE
            </h2>
            <span className="text-[10px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded">
              RESEARCH ONLY
            </span>
          </div>

          <p className="text-xs text-gray-300 mt-3 leading-relaxed">
            Computes Order-Book Imbalance (OBI), Trade Flow Imbalance (TFI), and Weighted Micro-Price deviation.
            Classifies immediate buying/selling pressure without assuming order-book depth alone guarantees directional edge.
          </p>

          <div className="mt-4 p-3 bg-[#121721] rounded-lg border border-[#1e2638] font-mono text-xs space-y-1">
            <div className="text-gray-400 text-[11px] uppercase font-bold">Active Live Telemetry:</div>
            <div className="text-gray-300">
              Pressure State:{' '}
              <span className="text-white font-bold">
                {strategies?.alpha1_orderflow?.pressure_regime || 'NEUTRAL'}
              </span>
            </div>
            <div className="text-gray-300">
              OBI: <span className="text-cyan-400">{strategies?.alpha1_orderflow?.metrics?.order_flow_imbalance || '0.00'}</span> |{' '}
              TFI: <span className="text-cyan-400">{strategies?.alpha1_orderflow?.metrics?.trade_flow_imbalance || '0.00'}</span>
            </div>
          </div>
        </div>

        {/* ALPHA-2R: Volatility Compression Breakout */}
        <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold font-mono text-white">
              ALPHA-2R: VOLATILITY COMPRESSION BREAKOUT
            </h2>
            <span className="text-[10px] font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded">
              RESEARCH ONLY
            </span>
          </div>

          <p className="text-xs text-gray-300 mt-3 leading-relaxed">
            Measures Volatility Compression Ratio (VCR = 6-bar RV / median(6-bar RV, 48 bars)). Rejects breakouts unless the completed
            5m bar exceeds the 12-bar high by at least max(0.30 ATR, 3x spread, 2 ticks) to ensure execution costs are covered.
          </p>

          <div className="mt-4 p-3 bg-[#121721] rounded-lg border border-[#1e2638] font-mono text-xs space-y-1">
            <div className="text-gray-400 text-[11px] uppercase font-bold">State:</div>
            <div className="text-gray-300">
              VCR Ratio: <span className="text-white font-bold">{strategies?.alpha2_breakout?.vcr || '1.0'}</span> (Threshold &lt; 0.65)
            </div>
            <div className="text-gray-300">
              Compression Active: <span className="text-amber-400">{strategies?.alpha2_breakout?.is_compressed ? 'YES' : 'NO'}</span>
            </div>
          </div>
        </div>

        {/* ALPHA-3R: BTC Basis Analysis */}
        <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold font-mono text-white">
              ALPHA-3R: BTC BASIS ANALYSIS
            </h2>
            <span className="text-[10px] font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-0.5 rounded">
              HEDGED ONLY / DISABLED
            </span>
          </div>

          <p className="text-xs text-gray-300 mt-3 leading-relaxed">
            Tracks Perpetual vs Spot price basis (B_t = ln(P_perp) - ln(P_spot)) and estimates Ornstein-Uhlenbeck (OU) half-life.
            Hedged basis trading is strictly disabled unless an executable spot hedge leg is legally and technically verified.
          </p>

          <div className="mt-4 p-3 bg-[#121721] rounded-lg border border-[#1e2638] font-mono text-xs space-y-1">
            <div className="text-gray-400 text-[11px] uppercase font-bold">Status:</div>
            <div className="text-gray-300">
              Basis: <span className="text-white font-bold">{strategies?.alpha3_basis?.basis_bps || '0.0'} bps</span> (${strategies?.alpha3_basis?.basis_usd || '0.0'})
            </div>
            <div className="text-gray-300">
              Regime: <span className="text-cyan-400">{strategies?.alpha3_basis?.basis_regime || 'FAIR BASIS'}</span>
            </div>
          </div>
        </div>

        {/* ALPHA-4R: Market Dislocation Protection (RISK GOVERNOR) */}
        <div className="col-span-full bg-[#0e131d] border border-rose-500/30 rounded-xl p-5 shadow-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-rose-400" />
              <h2 className="text-sm font-bold font-mono text-white">
                ALPHA-4R: MARKET DISLOCATION PROTECTION & JUMP GOVERNOR
              </h2>
            </div>
            <span className="text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
              SYSTEM RISK GOVERNOR ACTIVE
            </span>
          </div>

          <p className="text-xs text-gray-300 mt-2 leading-relaxed">
            Protects capital by continuously monitoring for abnormal mark-to-mid dislocation (&gt; 50 bps), sudden 5m return jumps
            (&gt; 2.5x ATR/Close), and extreme order-book spread expansion (&gt; 15 bps). Triggers HALTED and enforces a 2-candle (10-minute) cooldown.
          </p>

          <div className="mt-3 p-3 bg-[#121721] rounded-lg border border-[#1e2638] font-mono text-xs text-emerald-400 flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>Governor Status: {strategies?.alpha4_dislocation?.status || 'NORMAL MARKET CONDITIONS'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
