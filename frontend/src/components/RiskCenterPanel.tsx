'use client';

import React, { useState, useEffect } from 'react';
import { MarketState } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { ShieldAlert, Calculator, Flame, AlertTriangle, ShieldCheck } from 'lucide-react';

interface RiskCenterPanelProps {
  market: MarketState | null;
}

export const RiskCenterPanel: React.FC<RiskCenterPanelProps> = ({ market }) => {
  const [riskStatus, setRiskStatus] = useState<{risk_governor: {is_halted: boolean; current_losing_streak: number}; funding_safety: {is_funding_window_safe: boolean}} | null>(null);
  
  // Calculator inputs
  const [calcInputs, setCalcInputs] = useState({
    equity: 10000.0,
    risk_pct: 0.25,
    entry_price: market?.last_price || 80000.0,
    stop_loss: (market?.last_price || 80000.0) * 0.997,
    leverage: 2.0,
  });

  const [calcResult, setCalcResult] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    let isMounted = true;
    apiFetch<{risk_governor: {is_halted: boolean; current_losing_streak: number}; funding_safety: {is_funding_window_safe: boolean}}>('/api/risk/status').then(({ data, ok }) => {
      if (isMounted && ok && data) setRiskStatus(data);
    });
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    let active = true;
    apiFetch<Record<string, number>>("/api/risk/calculate", {method: "POST", body: JSON.stringify(calcInputs)}).then(({data, ok}) => { if (active && ok && data) setCalcResult(data); });
    return () => { active = false; };
  }, [calcInputs]);

  const governor = riskStatus?.risk_governor;
  const funding = riskStatus?.funding_safety;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-rose-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Capital Preservation & Institutional Risk Center
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl font-mono">
            Enforces strict capital protection constraints: daily loss shutoff, peak-to-trough drawdown kill-switches,
            losing streak cooldowns, and snapshot-aware funding gates.
          </p>
        </div>

        <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs font-mono text-emerald-400 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4" />
          <span>Risk Governor State: {governor?.is_halted ? 'HALTED' : 'OPERATIONAL'}</span>
        </div>
      </div>

      {/* Risk Limits Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 font-mono text-xs">
        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-gray-400 text-[11px] block">Max Risk Per Trade</span>
          <span className="text-lg font-bold text-white mt-1 block">0.25% of Equity</span>
          <span className="text-[10px] text-gray-500 mt-1 block">Including fees + 2x slippage</span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-gray-400 text-[11px] block">Max Exposure Multiple</span>
          <span className="text-lg font-bold text-white mt-1 block">2.0x Equity</span>
          <span className="text-[10px] text-gray-500 mt-1 block">Linear notional cap</span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-gray-400 text-[11px] block">Daily Loss Shutoff Limit</span>
          <span className="text-lg font-bold text-rose-400 mt-1 block">1.0% of Day Start</span>
          <span className="text-[10px] text-gray-500 mt-1 block">Halts new trades until next day</span>
        </div>

        <div className="bg-[#0e131d] p-4 rounded-xl border border-[#1e2638]">
          <span className="text-gray-400 text-[11px] block">Peak Drawdown Hard Kill</span>
          <span className="text-lg font-bold text-rose-400 mt-1 block">5.0% Peak-to-Trough</span>
          <span className="text-[10px] text-gray-500 mt-1 block">Requires manual audit to reset</span>
        </div>
      </div>

      {/* Funding Protection & Cooldown Tracker */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
        <div className="bg-[#0e131d] p-5 rounded-xl border border-[#1e2638]">
          <div className="flex items-center gap-2 mb-3">
            <Flame className="w-4 h-4 text-amber-400" />
            <h3 className="font-bold text-white uppercase text-xs">Funding Snapshot Protection</h3>
          </div>
          <p className="text-gray-400 text-[11px] mb-3">
            Trades are gated if the maximum 25-minute holding period overlaps an 8-hour funding snapshot: 05:30, 13:30, 21:30 IST (00:00, 08:00, 16:00 UTC).
          </p>
          <div className="p-3 bg-[#121721] rounded border border-[#1e2638] flex justify-between items-center">
            <span className="text-gray-400">Current Window Status:</span>
            <span
              className={`font-bold ${
                funding?.is_funding_window_safe ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {funding?.is_funding_window_safe ? 'SAFE TO ENTER' : 'GATED — FUNDING IMMINENT'}
            </span>
          </div>
        </div>

        <div className="bg-[#0e131d] p-5 rounded-xl border border-[#1e2638]">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-cyan-400" />
            <h3 className="font-bold text-white uppercase text-xs">Consecutive Loss Cooldown</h3>
          </div>
          <p className="text-gray-400 text-[11px] mb-3">
            4 consecutive losses automatically trigger a 12-candle (60 min) cool-off period.
          </p>
          <div className="p-3 bg-[#121721] rounded border border-[#1e2638] flex justify-between items-center">
            <span className="text-gray-400">Current Losing Streak:</span>
            <span className="font-bold text-white">
              {governor?.current_losing_streak || 0} / 4 Trades
            </span>
          </div>
        </div>
      </div>

      {/* Delta Exchange India Contract Sizing Calculator */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl">
        <div className="flex items-center gap-2 mb-4">
          <Calculator className="w-5 h-5 text-cyan-400" />
          <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
            Delta India Contract Sizing & Risk Calculator
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 font-mono text-xs mb-6">
          <div>
            <label className="text-gray-400 block mb-1">Simulated Capital ($)</label>
            <input
              type="number"
              value={calcInputs.equity}
              onChange={(e) => setCalcInputs({ ...calcInputs, equity: parseFloat(e.target.value) || 10000 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Max Risk (% Equity)</label>
            <input
              type="number"
              step="0.05"
              value={calcInputs.risk_pct}
              onChange={(e) => setCalcInputs({ ...calcInputs, risk_pct: parseFloat(e.target.value) || 0.25 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Entry Price ($)</label>
            <input
              type="number"
              value={calcInputs.entry_price}
              onChange={(e) => setCalcInputs({ ...calcInputs, entry_price: parseFloat(e.target.value) || 80000 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Stop Loss Price ($)</label>
            <input
              type="number"
              value={calcInputs.stop_loss}
              onChange={(e) => setCalcInputs({ ...calcInputs, stop_loss: parseFloat(e.target.value) || 79700 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Max Leverage Cap</label>
            <input
              type="number"
              step="0.5"
              value={calcInputs.leverage}
              onChange={(e) => setCalcInputs({ ...calcInputs, leverage: parseFloat(e.target.value) || 2.0 })}
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-1.5 text-white"
            />
          </div>
        </div>

        {calcResult && (
          <div className="p-4 bg-[#121721] rounded-lg border border-[#1e2638] grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
            <div>
              <span className="text-gray-400 block text-[10px]">Permitted Contract Lots:</span>
              <span className="text-cyan-400 font-bold text-sm">
                {calcResult.contracts} Lots ({calcResult.btc_exposure} BTC)
              </span>
            </div>

            <div>
              <span className="text-gray-400 block text-[10px]">Permitted Notional:</span>
              <span className="text-white font-bold text-sm">${calcResult.notional_usd.toLocaleString()}</span>
            </div>

            <div>
              <span className="text-gray-400 block text-[10px]">Total Risk at Stop:</span>
              <span className="text-rose-400 font-bold text-sm">
                ${calcResult.total_risk_at_stop_usd} ({calcResult.total_risk_equity_pct}%)
              </span>
            </div>

            <div>
              <span className="text-gray-400 block text-[10px]">Net Profit at 1.8R Target:</span>
              <span className="text-emerald-400 font-bold text-sm">
                ${calcResult.estimated_net_profit_at_target_usd} (R:R {calcResult.net_reward_to_risk})
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
