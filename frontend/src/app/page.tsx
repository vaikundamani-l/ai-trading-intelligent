'use client';

import React, { useState } from 'react';
import { useMarketData } from '@/hooks/useMarketData';
import { apiFetch } from '@/lib/api';
import { Navbar } from '@/components/Navbar';
import { TradingViewChart } from '@/components/TradingViewChart';
import { SignalCard } from '@/components/SignalCard';
import { OrderBookDepth } from '@/components/OrderBookDepth';
import { PredictionsPanel } from '@/components/PredictionsPanel';
import { StrategyLabPanel } from '@/components/StrategyLabPanel';
import { BacktestPanel } from '@/components/BacktestPanel';
import { PaperTradingPanel } from '@/components/PaperTradingPanel';
import { SignalHistoryPanel } from '@/components/SignalHistoryPanel';
import { RiskCenterPanel } from '@/components/RiskCenterPanel';
import { SettingsPanel } from '@/components/SettingsPanel';
import { TradeTimingPanel } from '@/components/TradeTimingPanel';

export default function Home() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [timeframe, setTimeframe] = useState<string>('5m');
  const { market, signal, predictions, portfolio, backendAvailable, utcTime, istTime, refreshData } =
    useMarketData();

  // Simulated paper trade from recommendation card
  const handlePaperExecute = async () => {
    if (!signal || !signal.entry_price || !signal.stop_loss || !signal.take_profit) return;
    try {
      const { ok } = await apiFetch<unknown>('/api/paper-trade/order', {
        method: 'POST',
        body: JSON.stringify({
          direction: signal.direction,
          entry_price: signal.entry_price,
          stop_loss: signal.stop_loss,
          take_profit: signal.take_profit,
        }),
      });
      if (ok) {
        refreshData();
      }
    } catch (e) {
      console.error('Error executing paper trade:', e);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090e] text-[#ededed] flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
      {/* Top Header & Navigation */}
      <Navbar
        market={market}
        utcTime={utcTime}
        istTime={istTime}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* Main Content Area */}
      <main className="flex-1 p-3 sm:p-4 max-w-[1920px] w-full mx-auto">
        {/* Backend Connection Alert Banner */}
        {!backendAvailable && (
          <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs font-mono text-amber-300 flex items-center justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
              <span>
                <strong>Connecting to Backend Engine:</strong> Start the backend service using <code className="bg-black/40 px-1.5 py-0.5 rounded text-amber-200">./run_dev.sh</code> or <code className="bg-black/40 px-1.5 py-0.5 rounded text-amber-200">uvicorn app.main:app --port 8000</code>. Reconnecting automatically...
              </span>
            </div>
            <button
              onClick={refreshData}
              className="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 rounded text-[11px] font-bold uppercase transition-colors shrink-0"
            >
              Retry
            </button>
          </div>
        )}
        {/* VIEW 1: Main Terminal (Dashboard) */}
        {activeTab === 'dashboard' && <TradeTimingPanel signal={signal} market={market} onChart={setTimeframe} />}
        {activeTab === 'dashboard' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-140px)] min-h-[750px]">
            {/* Center Main Financial Chart (8 cols) */}
            <div className="lg:col-span-8 xl:col-span-8 flex flex-col h-full">
              <TradingViewChart
                timeframe={timeframe}
                onTimeframeChange={setTimeframe}
                signal={signal}
                lastPrice={market?.last_price || 0}
              />
            </div>

            {/* Right Intelligence Panel (4 cols) */}
            <div className="lg:col-span-4 xl:col-span-4 flex flex-col gap-4 overflow-y-auto pr-1">
              {/* Prominent Recommendation Card */}
              <SignalCard
                signal={signal}
                market={market}
                onPaperExecute={handlePaperExecute}
              />

              {/* Order Book Depth & Microstructure Ladder */}
              <OrderBookDepth market={market} />
            </div>
          </div>
        )}

        {/* VIEW 2: AI Predictions */}
        {activeTab === 'predictions' && (
          <PredictionsPanel
            predictions={predictions}
            lastPrice={market?.last_price || 0}
            onRetrainSuccess={refreshData}
          />
        )}

        {/* VIEW 3: Strategy Lab */}
        {activeTab === 'strategies' && <StrategyLabPanel />}

        {/* VIEW 4: Order Flow */}
        {activeTab === 'orderflow' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-6xl mx-auto">
            <div className="lg:col-span-7">
              <OrderBookDepth market={market} />
            </div>
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="p-5 bg-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl font-mono text-xs space-y-3">
                <h3 className="font-bold text-white uppercase text-xs">Microstructure Theory & Rules</h3>
                <p className="text-gray-300 leading-relaxed text-[11px]">
                  Order-Book Imbalance (OBI) measures depth asymmetry across the top 10 limit order levels.
                  Trade Flow Imbalance (TFI) evaluates buyer vs seller aggressive market-order volume dominance.
                </p>
                <div className="p-3 bg-[#121721] rounded border border-[#1e2638] space-y-1">
                  <div className="text-gray-400">OBI Formula: (BidDepth - AskDepth) / (BidDepth + AskDepth)</div>
                  <div className="text-gray-400">TFI Formula: (BuyVol - SellVol) / (TotalVol + &epsilon;)</div>
                </div>
              </div>

              <div className="p-5 bg-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl font-mono text-xs space-y-3">
                <h3 className="font-bold text-white uppercase text-xs">Adverse Selection Guard</h3>
                <p className="text-gray-400 text-[11px] leading-relaxed">
                  Single-venue order books are subject to spoofing, instant cancellations, and queue jumping.
                  Passive limit fills are NOT assumed without queue replay validation.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* VIEW 5: Historical Backtesting */}
        {activeTab === 'backtest' && <BacktestPanel />}

        {/* VIEW 6: Paper Trading */}
        {activeTab === 'papertrading' && (
          <PaperTradingPanel
            portfolio={portfolio}
            market={market}
            onRefresh={refreshData}
          />
        )}

        {/* VIEW 7: Signal History */}
        {activeTab === 'signals' && <SignalHistoryPanel />}

        {/* VIEW 8: Risk Center */}
        {activeTab === 'risk' && <RiskCenterPanel market={market} />}

        {/* VIEW 9: Settings */}
        {activeTab === 'settings' && <SettingsPanel market={market} />}
      </main>
    </div>
  );
}
