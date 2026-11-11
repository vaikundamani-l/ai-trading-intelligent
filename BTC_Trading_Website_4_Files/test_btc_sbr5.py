"""Deterministic correctness tests. Synthetic prices are not profitability evidence."""
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from btc_sbr5_backtest import (Config, get_signals, process_trade, run_backtest,
                                funding_in_window, load_data)


def toy_data(rows=150):
    t=pd.date_range('2026-10-10T01:00:00Z',periods=rows,freq='5min')
    out=pd.DataFrame({'time':t, 'dt':t, 'open':[10000.0]*rows,
            'high':[10010.0]*rows, 'low':[9990.0]*rows,
            'close':[10000.0]*rows, 'volume':[100.0]*rows})
    out.loc[50,['open','high','low','close','volume']]=[10000.0,10025.0,9960.0,10005.0,300.0]
    out.loc[51,['open','high','low','close','volume']]=[10006.0,10046.0,10000.0,10035.0,100.0]
    return out


class TestResearchBacktester(unittest.TestCase):
    def test_signal_uses_previous_low(self):
        d=get_signals(toy_data(),Config())
        self.assertTrue(bool(d.loc[50,'long_signal']))
        self.assertFalse(bool(d.loc[49,'long_signal']))

    def test_next_bar_entry_and_fees(self):
        c=replace(Config(), minimum_stop_fraction=0.0015)
        trade=process_trade(get_signals(toy_data(),c),50,1,c,10000.0)
        self.assertIsNotNone(trade)
        self.assertEqual(trade['entry_utc'], toy_data().loc[51,'dt'].isoformat())
        self.assertGreater(trade['fees_bps'],11)
        self.assertLessEqual(trade['notional_usd_equivalent'],20000)

    def test_same_bar_stop_target_prefers_loss(self):
        d=toy_data()
        d.loc[51,['open','high','low','close']]=[10006.0,10200.0,9900.0,10000.0]
        c=Config()
        trade=process_trade(get_signals(d,c),50,1,c,10000.0)
        self.assertIn('stop',trade['reason'])
        self.assertLess(trade['pnl_equity_units'],0)

    def test_funding_gate(self):
        # 00:00 UTC = 05:30 IST; a new entry at 23:50 must be gated
        t=int(pd.Timestamp('2026-10-10T23:50:00Z').timestamp())
        self.assertTrue(funding_in_window(t,5,120))
        t2=int(pd.Timestamp('2026-10-10T12:00:00Z').timestamp())
        self.assertFalse(funding_in_window(t2,5,120))

    def test_corrupt_gaps_rejected(self):
        import os
        d=toy_data()
        d=d.drop(index=23).reset_index(drop=True)
        path='/mnt/data/_tmp_sbr5_gap.csv' if os.path.exists('/mnt/data') else '/tmp/_tmp_sbr5_gap.csv'
        d.drop(columns=['dt']).to_csv(path,index=False)
        with self.assertRaises(ValueError):
            load_data(path)

    def test_evaluation_basics(self):
        d=toy_data()
        trade_list,report=run_backtest(d)
        self.assertGreaterEqual(report['trades'],1)
        self.assertEqual(report['trades'],len(trade_list))


if __name__=='__main__':
    unittest.main()
