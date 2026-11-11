import unittest
import math
import time
import pandas as pd
import numpy as np

from app.config import settings
from app.strategies.alpha5_sbr5 import Alpha5SBR5, funding_in_window
from app.strategies.alpha4_dislocation import Alpha4RDislocationProtection
from app.strategies.alpha1_orderflow import Alpha1ROrderFlow
from app.strategies.alpha2_volatility import Alpha2RVolatilityBreakout
from app.strategies.alpha3_basis import Alpha3RBasisAnalysis
from app.services.backtest_service import BacktestConfig, compute_sbr5_signals, simulate_trade, run_sbr5_backtest

def make_test_candles(rows=150):
    t = pd.date_range('2026-10-10T01:00:00Z', periods=rows, freq='5min')
    unix_times = [int(x.timestamp()) for x in t]
    df = pd.DataFrame({
        'time': unix_times,
        'dt': t,
        'open': [10000.0] * rows,
        'high': [10010.0] * rows,
        'low': [9990.0] * rows,
        'close': [10000.0] * rows,
        'volume': [100.0] * rows
    })
    # Create an SBR-5 sweep and reclaim bar at index 50
    # Sweeps below previous low of 9990.0 down to 9960.0
    # Reclaims above 9990.0 + 0.10*ATR to close at 10005.0 (> open 10000.0)
    # Volume 300.0 (3.0x prior volume 100.0)
    df.loc[50, ['open', 'high', 'low', 'close', 'volume']] = [10000.0, 10025.0, 9960.0, 10005.0, 300.0]
    df.loc[51, ['open', 'high', 'low', 'close', 'volume']] = [10006.0, 10046.0, 10000.0, 10035.0, 100.0]
    return df

class TestBTCQuantumBackend(unittest.TestCase):
    def setUp(self):
        self.sbr5 = Alpha5SBR5()
        self.dislocation = Alpha4RDislocationProtection()
        self.orderflow = Alpha1ROrderFlow()
        self.volatility = Alpha2RVolatilityBreakout()
        self.basis = Alpha3RBasisAnalysis()

    def test_sbr5_buy_signal_conditions(self):
        df = make_test_candles()
        # Bar 50 is evaluated after close
        sub_df = df.iloc[:51]
        market_state = {
            "connection_status": "LIVE",
            "exchange_status": "operational",
            "last_price": 10005.0,
            "best_bid": 10004.5,
            "best_ask": 10005.0,
            "spread": 0.5,
            "spread_bps": 0.5
        }
        res = self.sbr5.evaluate(sub_df, market_state)
        self.assertEqual(res["action"], "BUY")
        self.assertEqual(res["direction"], 1)
        self.assertGreater(res["take_profit"], res["entry_price"])
        self.assertLess(res["stop_loss"], res["entry_price"])
        self.assertGreater(res["estimated_fees_bps"], 11.0)  # Taker 2-leg + GST
        self.assertGreater(res["risk_reward"], 1.0)

    def test_sbr5_sell_signal_conditions(self):
        df = make_test_candles()
        # Create bearish sweep above 10010.0 up to 10035.0, closing back at 9995.0 (< open 10000.0)
        df.loc[50, ['open', 'high', 'low', 'close', 'volume']] = [10000.0, 10035.0, 9990.0, 9995.0, 300.0]
        sub_df = df.iloc[:51]
        market_state = {
            "connection_status": "LIVE",
            "exchange_status": "operational",
            "last_price": 9995.0,
            "best_bid": 9994.5,
            "best_ask": 9995.0,
            "spread": 0.5,
            "spread_bps": 0.5
        }
        res = self.sbr5.evaluate(sub_df, market_state)
        self.assertEqual(res["action"], "SELL")
        self.assertEqual(res["direction"], -1)
        self.assertLess(res["take_profit"], res["entry_price"])
        self.assertGreater(res["stop_loss"], res["entry_price"])

    def test_funding_gate(self):
        # 00:00 UTC is funding snapshot. Entry at 23:50 UTC must be blocked!
        t_blocked = int(pd.Timestamp('2026-10-10T23:50:00Z').timestamp())
        self.assertTrue(funding_in_window(t_blocked, holding_bars=5, buffer_sec=120))
        
        # 12:00 UTC is safely between funding snapshots (08:00 and 16:00 UTC)
        t_safe = int(pd.Timestamp('2026-10-10T12:00:00Z').timestamp())
        self.assertFalse(funding_in_window(t_safe, holding_bars=5, buffer_sec=120))

    def test_ambiguous_bar_hits_stop_first(self):
        df = make_test_candles()
        # Bar 51 hits both stop (9900) and target (10200)
        df.loc[51, ['open', 'high', 'low', 'close']] = [10006.0, 10200.0, 9900.0, 10000.0]
        c = BacktestConfig()
        d_sig = compute_sbr5_signals(df, c)
        trade = simulate_trade(d_sig, 50, 1, c, 10000.0)
        self.assertIsNotNone(trade)
        self.assertIn("stop", trade["reason"])
        self.assertLess(trade["pnl_usd"], 0)

    def test_dislocation_filter_blocks_trading_on_extreme_jump(self):
        df = make_test_candles()
        # Bar 50 jumps by 10%
        df.loc[50, ['open', 'high', 'low', 'close']] = [10000.0, 11000.0, 9990.0, 11000.0]
        market_state = {
            "connection_status": "LIVE",
            "exchange_status": "operational",
            "last_price": 11000.0,
            "mark_price": 11000.0,
            "spread_bps": 0.5
        }
        is_safe, msg, det = self.dislocation.evaluate(df.iloc[:51], market_state)
        self.assertFalse(is_safe)
        self.assertIn("HALTED", msg)

    def test_orderflow_metrics_and_classification(self):
        state = {
            "order_flow_imbalance": 0.65,
            "trade_flow_imbalance": 0.45,
            "micro_price_dev": 1.5,
            "aggressive_buy_vol": 50000.0,
            "aggressive_sell_vol": 10000.0,
            "spread_bps": 0.8
        }
        res = self.orderflow.evaluate(state)
        self.assertEqual(res["pressure_regime"], "BUY PRESSURE")
        self.assertEqual(res["status"], "RESEARCH ONLY")

    def test_backtest_execution_on_synthetic_data(self):
        df = make_test_candles()
        res = run_sbr5_backtest(df, BacktestConfig(), initial_equity=10000.0)
        self.assertGreaterEqual(res["trades_count"], 1)
        self.assertIn("cost_sensitivity", res)
        self.assertEqual(len(res["cost_sensitivity"]), 5)

if __name__ == '__main__':
    unittest.main()
