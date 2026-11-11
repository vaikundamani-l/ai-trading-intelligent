import importlib.util
from pathlib import Path
import pandas as pd

spec=importlib.util.spec_from_file_location('winrate',Path(__file__).parents[1]/'research/search_winrate.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_high_win_rate_can_lose_money():
    result=module.summary([{'net_bps':10}]*8+[{'net_bps':-100}]*2)
    assert result['win_rate_pct']==80
    assert result['mean_net_bps']<0
    assert result['profit_factor']<1

def test_same_bar_stop_is_conservative_and_split_excludes_future():
    rows=[dict(time=i*900,open=100.,high=101.,low=99.,close=100.,atr=1.,setup=True) for i in range(23)]
    rows[21].update(high=103.,low=97.)
    bars=pd.DataFrame(rows)
    bars.attrs['duration']=900
    trades=module.simulate(bars,'BB_REENTRY',2,2,0,22*900)
    assert len(trades)==1
    assert abs(trades[0]['net_bps']-(-213.8))<1e-8
    assert module.simulate(bars,'BB_REENTRY',2,2,0,21*900+450)==[]
