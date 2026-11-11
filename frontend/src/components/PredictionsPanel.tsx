'use client';

import React, { useState } from 'react';
import { AIPredictions } from '@/lib/types';
import { apiFetch } from '@/lib/api';
import { BrainCircuit, RefreshCw, CheckCircle2, AlertCircle, ShieldCheck } from 'lucide-react';

interface PredictionsPanelProps {
  predictions: AIPredictions | null;
  lastPrice: number;
  onRetrainSuccess?: () => void;
}

export const PredictionsPanel: React.FC<PredictionsPanelProps> = ({
  predictions,
  onRetrainSuccess,
}) => {
  const [isRetraining, setIsRetraining] = useState<boolean>(false);
  const [retrainMsg, setRetrainMsg] = useState<string>('');

  const handleRetrain = async () => {
    setIsRetraining(true);
    setRetrainMsg('');
    try {
      const { data, ok, error } = await apiFetch<{status: string; reason?: string}>('/api/predictions/retrain', {
        method: 'POST',
      });
      if (ok && data?.status === 'SUCCESS') {
        setRetrainMsg('Models successfully retrained using chronological walk-forward split.');
        if (onRetrainSuccess) onRetrainSuccess();
      } else {
        setRetrainMsg(`Retraining response: ${data?.reason || data?.status || error || 'Failed'}`);
      }
    } catch {
      setRetrainMsg('Failed to trigger retraining.');
    } finally {
      setIsRetraining(false);
    }
  };

  const horizons = predictions?.horizons ? Object.values(predictions.horizons) : [];

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="p-6 bg-gradient-to-r from-[#121721] to-[#0e131d] border border-[#1e2638] rounded-xl shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-6 h-6 text-cyan-400" />
            <h1 className="text-xl font-bold font-mono text-white tracking-wide">
              Statistical AI Price Prediction Engine
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-1 max-w-2xl font-mono">
            Chronologically validated multi-horizon forecasting models (Logistic Regression & Volatility Scaling).
            Probabilities are strictly calibrated against out-of-sample Brier scores.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRetrain}
            disabled={isRetraining}
            className="flex items-center gap-2 px-4 py-2 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-mono font-semibold transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRetraining ? 'animate-spin' : ''}`} />
            {isRetraining ? 'Retraining Models...' : 'Retrain Models (Walk-Forward)'}
          </button>
        </div>
      </div>

      {retrainMsg && (
        <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono rounded-lg flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          <span>{retrainMsg}</span>
        </div>
      )}

      {/* Epistemic Transparency Disclaimer */}
      <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-lg text-xs font-mono text-amber-300/90 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold uppercase tracking-wider block text-amber-400">
            Research & Calibration Integrity Notice:
          </span>
          <span>
            Predictions represent statistical directional likelihoods conditioned on historical return distributions.
            They are NOT guaranteed profit forecasts and do not guarantee executable fill prices after taker fees and book-walking slippage.
          </span>
        </div>
      </div>

      {/* Multi-Horizon Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {horizons.length > 0 ? (
          horizons.map((h, i) => {
            if (!h.is_validated) return <div key={i} className="p-5 text-amber-400">{h.horizon}: prediction unavailable — insufficient validation evidence.</div>;
            const bull = h.bullish_probability || 50;
            const bear = h.bearish_probability || 50;
            const isBull = bull > 52;
            const isBear = bear > 52;

            return (
              <div
                key={i}
                className="bg-[#0e131d] border border-[#1e2638] rounded-xl p-5 flex flex-col justify-between shadow-xl"
              >
                <div>
                  {/* Horizon Tag */}
                  <div className="flex items-center justify-between pb-3 border-b border-[#1a2233]">
                    <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded border border-cyan-500/20">
                      Next {h.horizon} ({h.horizon_minutes}m)
                    </span>
                    <span
                      className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded ${
                        isBull
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : isBear
                          ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                      }`}
                    >
                      {h.directional_bias}
                    </span>
                  </div>

                  {/* Probability Bar */}
                  <div className="mt-4">
                    <div className="flex justify-between text-xs font-mono mb-1.5 font-bold">
                      <span className="text-emerald-400">Bullish: {bull.toFixed(1)}%</span>
                      <span className="text-rose-400">Bearish: {bear.toFixed(1)}%</span>
                    </div>
                    <div className="h-2.5 w-full bg-[#161d2b] rounded-full overflow-hidden flex">
                      <div
                        className="bg-emerald-500 transition-all duration-500"
                        style={{ width: `${bull}%` }}
                      />
                      <div
                        className="bg-rose-500 transition-all duration-500"
                        style={{ width: `${bear}%` }}
                      />
                    </div>
                  </div>

                  {/* Forecast Range & Volatility */}
                  <div className="mt-5 space-y-2.5 font-mono text-xs">
                    <div className="flex justify-between py-1.5 border-b border-[#161d2b]">
                      <span className="text-gray-400">Expected Move:</span>
                      <span className="text-white font-bold">±${h.expected_move_usd.toFixed(1)}</span>
                    </div>

                    <div className="flex justify-between py-1.5 border-b border-[#161d2b]">
                      <span className="text-gray-400">Expected Vol:</span>
                      <span className="text-cyan-400">{h.expected_volatility_pct.toFixed(3)}%</span>
                    </div>

                    <div className="flex justify-between py-1.5 border-b border-[#161d2b]">
                      <span className="text-gray-400">Projected Range:</span>
                      <span className="text-gray-300 font-semibold">
                        ${h.range_forecast.lower.toFixed(0)} - ${h.range_forecast.upper.toFixed(0)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Model Validation & Calibration Footer */}
                <div className="mt-5 pt-3 border-t border-[#1a2233] font-mono text-[10px] space-y-1">
                  <div className="text-gray-500">
                    Model: <span className="text-gray-300">{h.model_version}</span>
                  </div>
                  <div className="text-gray-500">
                    Trained: <span className="text-gray-300">{h.training_date}</span>
                  </div>
                  <div className="text-emerald-400 font-semibold mt-1">
                    {h.calibration_status}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="col-span-full p-8 text-center bg-[#0e131d] border border-[#1e2638] rounded-xl text-gray-400 font-mono text-xs">
            <AlertCircle className="w-8 h-8 text-amber-400 mx-auto mb-2" />
            <p className="font-bold text-white text-sm">PREDICTION UNAVAILABLE — MODEL NOT VALIDATED</p>
            <p className="mt-1">
              Click &quot;Retrain Models&quot; above to train and validate historical logistic regression models.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
