'use client';

import React, { useState } from 'react';
import { useMarketData } from '@/hooks/useMarketData';
import { Navbar } from '@/components/Navbar';
import { TradingViewChart } from '@/components/TradingViewChart';
import { SignalCard } from '@/components/SignalCard';

export default function Home() {
  const [timeframe, setTimeframe] = useState('5m');
  const { market, signal, backendAvailable, utcTime, istTime, refreshData } = useMarketData(timeframe);

  return (
    <div className="min-h-screen bg-[#07090e] text-[#ededed] flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
      <Navbar market={market} utcTime={utcTime} istTime={istTime} />
      <main className="flex-1 p-3 sm:p-4 max-w-[1920px] w-full mx-auto">
        {!backendAvailable && (
          <div role="status" className="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs font-mono text-amber-300 flex items-center justify-between gap-3">
            <span>Live signal feed unavailable. Reconnecting automatically…</span>
            <button
              onClick={refreshData}
              className="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded text-[11px] font-bold uppercase shrink-0"
            >
              Retry
            </button>
          </div>
        )}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          <section aria-label="Live BTCUSD chart" className="lg:col-span-9 min-w-0 h-[75vh] min-h-[550px] lg:h-[calc(100dvh-110px)]">
            <TradingViewChart
              timeframe={timeframe}
              onTimeframeChange={setTimeframe}
              signal={signal}
              lastPrice={market?.last_price || 0}
            />
          </section>
          <aside aria-label="Current trading signal" className="lg:col-span-3 min-w-0">
            <SignalCard signal={signal} market={market} timeframe={timeframe} />
          </aside>
        </div>
      </main>
    </div>
  );
}
