'use client';

import React, { useState } from 'react';
import { MarketState } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import {
  Activity,
  Radio,
  Clock,
  ShieldAlert,
  SlidersHorizontal,
  Flame,
  LineChart,
  BrainCircuit,
  Layers,
  History,
  Terminal,
  RotateCcw,
  Play,
  Pause,
  BookOpen,
} from 'lucide-react';

interface NavbarProps {
  market: MarketState | null;
  utcTime: string;
  istTime: string;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  market,
  utcTime,
  istTime,
  activeTab,
  setActiveTab,
}) => {
  const connStatus = market?.connection_status || 'DISCONNECTED';
  const lastPrice = market?.last_price || 0;
  const change24h = market?.change_24h_pct || 0;
  const isPositive = change24h >= 0;

  // Format funding countdown
  const fundingCountdown = market?.next_funding_countdown_sec || 0;
  const hours = Math.floor(fundingCountdown / 3600);
  const minutes = Math.floor((fundingCountdown % 3600) / 60);
  const seconds = fundingCountdown % 60;
  const fundingStr = `${hours.toString().padStart(2, '0')}h ${minutes
    .toString()
    .padStart(2, '0')}m ${seconds.toString().padStart(2, '0')}s`;

  const [isEnginePaused, setIsEnginePaused] = useState<boolean>(false);
  const [isToggling, setIsToggling] = useState<boolean>(false);

  const handleToggleEngine = async () => {
    setIsToggling(true);
    const { data, ok } = await apiFetch<{is_halted: boolean}>('/api/engine/toggle', { method: 'POST' });
    if (ok && data) {
      setIsEnginePaused(data.is_halted);
    }
    setIsToggling(false);
  };

  return (
    <header className="border-b border-[#1e2638] bg-[#0b0e14] sticky top-0 z-50">
      {/* Top Bar */}
      <div className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-4 border-b border-[#161d2b]">
        {/* Logo and Instrument */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <Activity className="w-5 h-5 text-black font-bold" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold tracking-wider text-white text-base">
                  BTC QUANTUM
                </span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  INTELLIGENCE
                </span>
              </div>
              <div className="text-[11px] text-gray-400 font-mono">
                Delta Exchange India • BTCUSD Perp
              </div>
            </div>
          </div>

          <div className="h-6 w-[1px] bg-[#1e2638] mx-2 hidden sm:block" />

          {/* Live Price Display */}
          <div className="flex items-baseline gap-2.5 font-mono">
            <span
              className={`text-xl font-bold tracking-tight ${
                isPositive ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              ${lastPrice.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
            </span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded font-semibold flex items-center gap-0.5 ${
                isPositive
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
              }`}
            >
              {isPositive ? '+' : ''}
              {change24h.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Live Metrics & Indicators */}
        <div className="flex items-center flex-wrap gap-4 text-xs font-mono">
          {/* Mark vs Spot Basis */}
          <div className="hidden lg:flex items-center gap-2 bg-[#121721] px-2.5 py-1.5 rounded border border-[#1e2638]">
            <span className="text-gray-400">Mark:</span>
            <span className="text-white font-medium">
              ${market?.mark_price ? market.mark_price.toFixed(1) : '—'}
            </span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">Basis:</span>
            <span
              className={
                (market?.basis_bps || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }
            >
              {market?.basis_bps ? `${market.basis_bps > 0 ? '+' : ''}${market.basis_bps.toFixed(1)} bp` : '—'}
            </span>
          </div>

          {/* Funding Countdown */}
          <div className="hidden md:flex items-center gap-1.5 bg-[#121721] px-2.5 py-1.5 rounded border border-[#1e2638]">
            <Flame className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-gray-400">Funding:</span>
            <span className="text-amber-400 font-medium">
              {market?.funding_rate_pct ? `${market.funding_rate_pct > 0 ? '+' : ''}${market.funding_rate_pct.toFixed(4)}%` : '0.0000%'}
            </span>
            <span className="text-gray-500 text-[10px]">({fundingStr})</span>
          </div>

          {/* UTC & IST Clocks */}
          <div className="flex items-center gap-2 bg-[#121721] px-2.5 py-1.5 rounded border border-[#1e2638]">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-gray-300">{istTime || '—'}</span>
            <span className="text-gray-500">|</span>
            <span className="text-gray-400">{utcTime || '—'}</span>
          </div>

          {/* Connection Status Badge */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded border font-semibold">
            {connStatus === 'LIVE' && (
              <span className="flex items-center gap-1.5 text-emerald-400 bg-emerald-500/10 border-emerald-500/20">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                LIVE FEED
              </span>
            )}
            {connStatus === 'DELAYED' && (
              <span className="flex items-center gap-1.5 text-amber-400 bg-amber-500/10 border-amber-500/20">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                DELAYED
              </span>
            )}
            {connStatus === 'DISCONNECTED' && (
              <span className="flex items-center gap-1.5 text-rose-400 bg-rose-500/10 border-rose-500/20">
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                DISCONNECTED
              </span>
            )}
          </div>

          {/* Engine Start/Stop Quick Control Toggle */}
          <button
            onClick={handleToggleEngine}
            disabled={isToggling}
            className={`flex items-center gap-1.5 px-3 py-1 rounded border font-mono font-bold text-xs uppercase tracking-wide transition-all shadow-sm ${
              isEnginePaused
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/40 hover:bg-amber-500/25'
                : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/25'
            }`}
            title="Start or Stop strategy signal and paper trading execution"
          >
            {isEnginePaused ? (
              <>
                <Play className="w-3 h-3 fill-current text-amber-400" />
                <span>Resume Engine</span>
              </>
            ) : (
              <>
                <Pause className="w-3 h-3 fill-current text-emerald-400" />
                <span>Stop Engine</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <nav className="px-4 flex items-center gap-1 overflow-x-auto scrollbar-none bg-[#0e121a]">
        {[
          { id: 'dashboard', label: 'Terminal', icon: Terminal },
          { id: 'predictions', label: 'AI Predictions', icon: BrainCircuit },
          { id: 'strategies', label: 'Strategy Lab', icon: Layers },
          { id: 'orderflow', label: 'Order Flow', icon: Radio },
          { id: 'backtest', label: 'Backtesting', icon: LineChart },
          { id: 'papertrading', label: 'Paper Trading', icon: RotateCcw },
          { id: 'signals', label: 'Signal History', icon: History },
          { id: 'risk', label: 'Risk Center', icon: ShieldAlert },
          { id: 'settings', label: 'Settings', icon: SlidersHorizontal },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-xs font-medium tracking-wide transition-all border-b-2 whitespace-nowrap ${
                isActive
                  ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-[#121721]'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
        <a
          href="/about.html"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3.5 py-2.5 text-xs font-medium tracking-wide border-b-2 border-transparent text-cyan-400 hover:text-cyan-300 hover:bg-[#121721] whitespace-nowrap transition-all"
          title="Open complete architectural & operational project guide with Tamil explanation"
        >
          <BookOpen className="w-4 h-4 text-cyan-400" />
          About Project
        </a>
      </nav>
    </header>
  );
};
