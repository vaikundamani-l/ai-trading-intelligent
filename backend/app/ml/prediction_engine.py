import math
import time
import logging
import threading
from functools import wraps

def synchronized(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapped

from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier, VotingClassifier
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score
from sklearn.calibration import CalibratedClassifierCV

logger = logging.getLogger("PredictionEngine")

class StatisticalAIPredictionEngine:
    def __init__(self):
        self._lock = threading.RLock()
        self.last_attempt = 0.0
        self.model_version = "BTC-QUANTUM-ML-v2-PURGED-ENSEMBLE"
        self.last_training_date = ""
        self.horizons = {
            "5m": 1,    # 1 bar of 5m
            "15m": 3,   # 3 bars
            "30m": 6,   # 6 bars
            "1h": 12    # 12 bars
        }
        self.models: Dict[str, Any] = {}
        self.model_metrics: Dict[str, Dict[str, Any]] = {}
        self.is_validated: Dict[str, bool] = {}
        self._is_trained = False

    @staticmethod
    def build_features(df_5m):
        df = df_5m[df_5m["time"] + 300 <= time.time()].copy()
        df['ret_1'] = df['close'].pct_change(1)
        df['ret_2'] = df['close'].pct_change(2)
        df['ret_3'] = df['close'].pct_change(3)
        df['ret_6'] = df['close'].pct_change(6)
        
        # Normalized ATR
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - prev_close).abs(),
            (df['low'] - prev_close).abs()
        ], axis=1).max(axis=1)
        df['atr_norm'] = (tr.rolling(14).mean() / df['close']).shift(1)
        
        # Realized Volatility
        df['rv_6'] = df['ret_1'].rolling(6).std().shift(1)
        
        # Volume impulse
        df['vol_ratio'] = (df['volume'] / (df['volume'].rolling(24).mean().shift(1) + 1e-6)).shift(1)
        
        feature_cols = ['ret_1', 'ret_2', 'ret_3', 'ret_6', 'atr_norm', 'rv_6', 'vol_ratio']
        
        return df, feature_cols

    @synchronized
    def train_models(self, df_5m: pd.DataFrame) -> Dict[str, Any]:
        """Trains directional and volatility models using strict walk-forward historical data.
        Never uses future bars for training.
        """
        self.last_attempt = time.time()
        if df_5m is None or len(df_5m) < 150:
            logger.warning(f"Not enough clean candles for training: have {len(df_5m) if df_5m is not None else 0}, need >= 150")
            self._is_trained = False
            return {"status": "FAILED", "reason": "Insufficient historical candles"}

        logger.info(f"Training Statistical AI models on {len(df_5m)} candles...")
        results = {}
        self.models = {}
        self.is_validated = {}
        self.model_metrics = {}
        
        df, feature_cols = self.build_features(df_5m)

        for h_name, h_bars in self.horizons.items():
            # Target is future sign of return over horizon h: 1 if positive, 0 if negative
            future_ret = (df['close'].shift(-h_bars) - df['close']) / df['close']
            df[f'target_{h_name}'] = (future_ret > 0).astype(float).where(future_ret.notna())
            
            # Drop NaN rows
            sub_df = df[feature_cols + [f'target_{h_name}']].dropna()
            if len(sub_df) < 100:
                continue

            # Chronological 70% Train, 30% Out-of-Sample Holdout
            split_idx = int(len(sub_df) * 0.70)
            train_df = sub_df.iloc[:split_idx - h_bars]
            test_df = sub_df.iloc[split_idx:]
            
            X_train = train_df[feature_cols]
            y_train = train_df[f'target_{h_name}']
            X_test = test_df[feature_cols]
            y_test = test_df[f'target_{h_name}']
            
            # Baseline: logistic regression with L2 regularization
            base_model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
            ensemble = VotingClassifier(estimators=[("linear", base_model), ("nonlinear", HistGradientBoostingClassifier(max_iter=60, max_leaf_nodes=7, min_samples_leaf=30, l2_regularization=10, random_state=42))], voting="soft")
            calibrated_model = CalibratedClassifierCV(ensemble, method='sigmoid', cv=TimeSeriesSplit(n_splits=3, gap=h_bars))
            try:
                calibrated_model.fit(X_train, y_train)
            except ValueError:
                self.is_validated[h_name] = False
                continue
            
            # Out-of-sample evaluation
            probs = calibrated_model.predict_proba(X_test)[:, 1]
            preds = (probs > 0.5).astype(int)
            
            brier = brier_score_loss(y_test, probs)
            acc = accuracy_score(y_test, preds)
            loss = log_loss(y_test, probs, labels=[0, 1])
            
            # A valid model should have Brier score <= 0.26 and realistic calibration
            baseline = brier_score_loss(y_test, np.full(len(y_test), y_train.mean()))
            is_valid = bool(brier < min(0.25, baseline * 0.98) and len(y_test) >= 100)
            
            self.models[h_name] = calibrated_model
            self.model_metrics[h_name] = {
                "baseline_brier": round(float(baseline), 4),
                "brier_score": round(float(brier), 4),
                "accuracy": round(float(acc * 100), 2),
                "log_loss": round(float(loss), 4),
                "test_samples": len(y_test),
                "train_samples": len(y_train),
                "is_validated": is_valid
            }
            self.is_validated[h_name] = is_valid
            results[h_name] = self.model_metrics[h_name]

        self.last_training_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self._is_trained = bool(self.models)
        return {
            "status": "SUCCESS" if self._is_trained else "INSUFFICIENT_DATA",
            "model_version": self.model_version,
            "training_date": self.last_training_date,
            "metrics": results
        }

    @synchronized
    def generate_predictions(self, df_5m: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """Generates statistical predictions for all 4 horizons.
        Never fabricates arbitrary 80-95% confidence numbers.
        """
        now_ts = int(time.time())
        now_utc = datetime.now(timezone.utc).isoformat()
        
        if not self._is_trained and time.time() - self.last_attempt > 300:
            # Attempt to auto-train if sufficient candles exist
            if df_5m is not None and len(df_5m) >= 150:
                self.train_models(df_5m)
                
        if not self._is_trained or df_5m is None or len(df_5m) < 30:
            return {
                "status": "UNAVAILABLE",
                "message": "PREDICTION UNAVAILABLE — MODEL NOT VALIDATED",
                "model_version": self.model_version,
                "horizons": {},
                "timestamp": now_ts,
                "datetime_utc": now_utc
            }

        d, feature_cols = self.build_features(df_5m)
        if d.empty or not np.isfinite(d[feature_cols].iloc[-1]).all() or time.time() - float(d['time'].iloc[-1]) > 900:
            return {"status": "UNAVAILABLE", "horizons": {}, "message": "Fresh completed candles unavailable", "model_version": self.model_version}
        features = d[feature_cols].tail(1)
        rv_6 = float(features['rv_6'].iloc[0])

        horizon_forecasts = {}
        for h_name, h_bars in self.horizons.items():
            model = self.models.get(h_name)
            metrics = self.model_metrics.get(h_name, {})
            is_valid = self.is_validated.get(h_name, False)
            
            if model is None or not is_valid:
                horizon_forecasts[h_name] = {
                    "status": "PREDICTION UNAVAILABLE — MODEL NOT VALIDATED",
                    "horizon": h_name,
                    "horizon_minutes": h_bars * 5,
                    "is_validated": False,
                    "metrics": metrics,
                    "observed_price": current_price
                }
                continue

            # Predict probability
            prob_arr = model.predict_proba(features)[0]
            bull_prob = float(prob_arr[1])
            bear_prob = float(prob_arr[0])
            
            # Expected move (sigma * sqrt(h))
            # 5m bar volatility: rv_6
            h_scale = math.sqrt(h_bars)
            expected_vol_pct = (rv_6 * h_scale) if rv_6 > 0 else 0.002
            expected_move_usd = current_price * expected_vol_pct
            
            range_low = current_price - (expected_move_usd * 1.5)
            range_high = current_price + (expected_move_usd * 1.5)

            calib_label = (
                f"CALIBRATED (Brier: {metrics.get('brier_score', 'N/A')}, Acc: {metrics.get('accuracy', 'N/A')}%)"
                if is_valid else "UNCALIBRATED / HIGH BIAS"
            )

            horizon_forecasts[h_name] = {
                "horizon": h_name,
                "horizon_minutes": h_bars * 5,
                "observed_price": round(current_price, 1),
                "bullish_probability": round(bull_prob * 100, 1),
                "bearish_probability": round(bear_prob * 100, 1),
                "expected_move_usd": round(expected_move_usd, 1),
                "expected_volatility_pct": round(expected_vol_pct * 100, 3),
                "range_forecast": {
                    "lower": round(range_low, 1),
                    "upper": round(range_high, 1)
                },
                "directional_bias": "BULLISH" if bull_prob > 0.52 else ("BEARISH" if bear_prob > 0.52 else "NEUTRAL"),
                "model_version": self.model_version,
                "training_date": self.last_training_date,
                "calibration_status": calib_label,
                "is_validated": is_valid,
                "metrics": metrics
            }

        return {
            "status": "VALIDATED" if any(self.is_validated.values()) else "UNCALIBRATED",
            "model_version": self.model_version,
            "training_date": self.last_training_date,
            "horizons": horizon_forecasts,
            "timestamp": now_ts,
            "datetime_utc": now_utc
        }

prediction_engine = StatisticalAIPredictionEngine()
