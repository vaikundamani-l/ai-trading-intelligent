'use client';

import React, { useState } from 'react';
import { MarketState } from '@/lib/types';
import { SlidersHorizontal, Globe, Bell, Shield, CheckCircle2 } from 'lucide-react';

interface SettingsPanelProps {
  market: MarketState | null;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ market }) => {
  const [audioAlerts, setAudioAlerts] = useState<boolean>(true);
  const [browserAlerts, setBrowserAlerts] = useState<boolean>(true);
  const [savedMsg, setSavedMsg] = useState<string>('');

  const handleSave = () => {
    setSavedMsg('Settings saved successfully.');
    setTimeout(() => setSavedMsg(''), 3000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-6 h-6 text-cyan-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Platform Configuration & Connectivity Settings
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 font-mono">
            Manage exchange endpoints, alert preferences, and operational safeguards.
          </p>
        </div>
      </div>

      {savedMsg && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{savedMsg}</span>
        </div>
      )}

      {/* Delta Exchange India Endpoints */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl font-mono text-xs space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-[#1e2638]">
          <Globe className="w-4 h-4 text-cyan-400" />
          <h3 className="font-bold text-white uppercase text-xs">Delta Exchange India API Configuration</h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-gray-400 block mb-1">REST API Base URL</label>
            <input
              type="text"
              readOnly
              value="https://api.india.delta.exchange"
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-2 text-gray-300 font-mono"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Public WebSocket URL</label>
            <input
              type="text"
              readOnly
              value="wss://public-socket.india.delta.exchange"
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-2 text-gray-300 font-mono"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Primary Instrument</label>
            <input
              type="text"
              readOnly
              value="BTCUSD (Bitcoin Perpetual Futures)"
              className="w-full bg-[#121721] border border-[#1e2638] rounded px-3 py-2 text-gray-300 font-mono"
            />
          </div>

          <div>
            <label className="text-gray-400 block mb-1">Current Feed Status</label>
            <div className="flex items-center gap-2 bg-[#121721] border border-[#1e2638] rounded px-3 py-2">
              <span className={`w-2 h-2 rounded-full ${market?.connection_status === 'LIVE' ? 'bg-emerald-400' : 'bg-rose-400'}`} />
              <span className="font-bold text-white">{market?.connection_status || 'DISCONNECTED'}</span>
              <span className="text-gray-500 text-[11px] ml-auto">
                Age: {market?.data_age_sec ? `${market.data_age_sec}s` : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Notification Preferences */}
      <div className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 shadow-xl font-mono text-xs space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-[#1e2638]">
          <Bell className="w-4 h-4 text-cyan-400" />
          <h3 className="font-bold text-white uppercase text-xs">Alert & Sound Preferences</h3>
        </div>

        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={browserAlerts}
              onChange={(e) => setBrowserAlerts(e.target.checked)}
              className="w-4 h-4 rounded bg-[#121721] border-[#1e2638] text-cyan-500 focus:ring-0"
            />
            <div>
              <span className="text-white block font-medium">Browser Push Notifications</span>
              <span className="text-gray-400 text-[11px]">Notify on valid SBR-5 BUY or SELL signal triggers</span>
            </div>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={audioAlerts}
              onChange={(e) => setAudioAlerts(e.target.checked)}
              className="w-4 h-4 rounded bg-[#121721] border-[#1e2638] text-cyan-500 focus:ring-0"
            />
            <div>
              <span className="text-white block font-medium">Audio Execution Beeps</span>
              <span className="text-gray-400 text-[11px]">Sound chime when stop-loss or take-profit level is reached</span>
            </div>
          </label>
        </div>
      </div>

      {/* Security & Non-Execution Safe Mode */}
      <div className="bg-[#0e131d] border border-cyan-500/20 rounded-xl p-5 shadow-xl font-mono text-xs space-y-3">
        <div className="flex items-center gap-2 pb-3 border-b border-[#1e2638]">
          <Shield className="w-4 h-4 text-emerald-400" />
          <h3 className="font-bold text-white uppercase text-xs">Institutional Non-Execution Guardrail</h3>
        </div>

        <p className="text-gray-300 leading-relaxed">
          This installation is configured strictly in <span className="text-emerald-400 font-bold">READ-ONLY RESEARCH & PAPER TRADING MODE</span>.
          No exchange API trading keys with order placement or withdrawal permissions are accepted or stored on this server. Real-money orders cannot be placed.
        </p>

        <div className="pt-2 flex justify-end">
          <button
            onClick={handleSave}
            className="px-5 py-2 bg-cyan-500 hover:bg-cyan-400 text-black font-bold rounded-lg uppercase tracking-wider text-xs transition-all shadow-lg shadow-cyan-500/20"
          >
            Save Preferences
          </button>
        </div>
      </div>
    </div>
  );
};
