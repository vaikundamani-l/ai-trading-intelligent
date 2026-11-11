'use client';

import React from 'react';
import { MarketState } from '@/lib/types';
import { ArrowDown, ArrowUp, Radio } from 'lucide-react';

interface OrderBookDepthProps {
  market: MarketState | null;
}

export const OrderBookDepth: React.FC<OrderBookDepthProps> = ({ market }) => {
  const bids = market?.bids || [];
  const asks = market?.asks || [];
  const maxBidVol = bids.length ? Math.max(...bids.map((b) => b.size)) : 1;
  const maxAskVol = asks.length ? Math.max(...asks.map((a) => a.size)) : 1;
  const maxVol = Math.max(maxBidVol, maxAskVol, 1);

  const ofi = market?.order_flow_imbalance || 0;
  const tfi = market?.trade_flow_imbalance || 0;
  const microDev = market?.micro_price_dev || 0;

  return (
    <div className="flex flex-col bg-[#0e131d] border border-[#1e2638] rounded-xl overflow-hidden shadow-xl">
      {/* Header */}
      <div className="px-4 py-3 bg-[#121721] border-b border-[#1e2638] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-cyan-400 animate-pulse" />
          <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
            Order Book & Microstructure (L2 Top 15)
          </h3>
        </div>
        <span className="text-[11px] font-mono text-gray-400">
          Spread:{' '}
          <span className="text-white font-bold">
            ${market?.spread ? market.spread.toFixed(1) : '0.5'}
          </span>{' '}
          ({market?.spread_bps ? market.spread_bps.toFixed(2) : '0.06'} bp)
        </span>
      </div>

      {/* Microstructure Metrics Banner */}
      <div className="p-3 bg-[#0b0e14] border-b border-[#1e2638] grid grid-cols-3 gap-2 text-center font-mono text-xs">
        {/* Order Book Imbalance (OBI) */}
        <div className="bg-[#121721] p-2 rounded border border-[#1e2638]">
          <span className="text-[10px] text-gray-400 block">Book Imbalance (OBI)</span>
          <span
            className={`font-bold ${
              ofi > 0.1 ? 'text-emerald-400' : ofi < -0.1 ? 'text-rose-400' : 'text-gray-300'
            }`}
          >
            {ofi > 0 ? '+' : ''}
            {(ofi * 100).toFixed(1)}%
          </span>
        </div>

        {/* Trade Flow Imbalance (TFI) */}
        <div className="bg-[#121721] p-2 rounded border border-[#1e2638]">
          <span className="text-[10px] text-gray-400 block">Trade Flow (TFI)</span>
          <span
            className={`font-bold ${
              tfi > 0.1 ? 'text-emerald-400' : tfi < -0.1 ? 'text-rose-400' : 'text-gray-300'
            }`}
          >
            {tfi > 0 ? '+' : ''}
            {(tfi * 100).toFixed(1)}%
          </span>
        </div>

        {/* Micro-Price Deviation */}
        <div className="bg-[#121721] p-2 rounded border border-[#1e2638]">
          <span className="text-[10px] text-gray-400 block">Micro-Price Dev</span>
          <span
            className={`font-bold ${
              microDev > 0 ? 'text-emerald-400' : microDev < 0 ? 'text-rose-400' : 'text-gray-300'
            }`}
          >
            {microDev > 0 ? '+' : ''}${microDev.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Depth Ladder */}
      <div className="p-3 font-mono text-[11px] grid grid-cols-2 gap-3 max-h-[360px] overflow-y-auto">
        {/* Bids Side */}
        <div>
          <div className="flex justify-between text-gray-500 pb-1 border-b border-[#1a2233] font-semibold text-[10px]">
            <span>BID PRICE</span>
            <span>SIZE (LOTS)</span>
          </div>
          <div className="space-y-1 mt-1">
            {bids.slice(0, 10).map((b, i) => {
              const widthPct = Math.min(100, (b.size / maxVol) * 100);
              return (
                <div key={i} className="relative flex justify-between py-0.5 px-1 rounded overflow-hidden">
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-emerald-500/10 pointer-events-none"
                    style={{ width: `${widthPct}%` }}
                  />
                  <span className="text-emerald-400 font-bold z-10">${b.price.toFixed(1)}</span>
                  <span className="text-gray-300 z-10">{b.size.toLocaleString()}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Asks Side */}
        <div>
          <div className="flex justify-between text-gray-500 pb-1 border-b border-[#1a2233] font-semibold text-[10px]">
            <span>ASK PRICE</span>
            <span>SIZE (LOTS)</span>
          </div>
          <div className="space-y-1 mt-1">
            {asks.slice(0, 10).map((a, i) => {
              const widthPct = Math.min(100, (a.size / maxVol) * 100);
              return (
                <div key={i} className="relative flex justify-between py-0.5 px-1 rounded overflow-hidden">
                  <div
                    className="absolute left-0 top-0 bottom-0 bg-rose-500/10 pointer-events-none"
                    style={{ width: `${widthPct}%` }}
                  />
                  <span className="text-rose-400 font-bold z-10">${a.price.toFixed(1)}</span>
                  <span className="text-gray-300 z-10">{a.size.toLocaleString()}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recent Executions Strip */}
      <div className="px-4 py-2 bg-[#121721] border-t border-[#1e2638] flex items-center justify-between text-[11px] font-mono text-gray-400">
        <span>Aggressive Flow:</span>
        <div className="flex items-center gap-3">
          <span className="text-emerald-400 flex items-center gap-0.5">
            <ArrowUp className="w-3 h-3" /> Buy: ${((market?.aggressive_buy_vol || 0) / 1000).toFixed(1)}k
          </span>
          <span className="text-rose-400 flex items-center gap-0.5">
            <ArrowDown className="w-3 h-3" /> Sell: ${((market?.aggressive_sell_vol || 0) / 1000).toFixed(1)}k
          </span>
        </div>
      </div>
    </div>
  );
};
