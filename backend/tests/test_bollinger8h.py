import pandas as pd
from app.strategies.bollinger8h import completed_8h, analyze, replay

def history():
    return pd.DataFrame([dict(time=i*3600, open=100.0, high=101.0, low=99.0, close=100.0) for i in range(240)])

def test_complete_groups_and_unfinished_exclusion():
    assert len(completed_8h(history(), 240*3600-1)) == 29
    d = history().drop(index=8)
    assert len(completed_8h(d, 240*3600)) == 29

def test_45m_bars_use_three_complete_15m_candles():
    d = history()
    d['time'] = d['time'] / 4
    bars = completed_8h(d, 240*900, duration=2700, base=900)
    assert len(bars) == 80
    assert bars.time.diff().dropna().eq(2700).all()
    missing = completed_8h(d.drop(index=5), 240*900, duration=2700, base=900)
    assert len(missing) == 79

def test_custom_timeframe_history_and_validation(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.api import endpoints
    with pytest.raises(HTTPException):
        endpoints.bollinger8h_report(minutes=17)
    for minutes in (15,45,240,480,75):
        base = 3600 if minutes%60==0 else 900
        d = history()
        d['time'] = d['time'] / (3600/base)
        result = analyze(d, {}, 240*base, duration=minutes*60, base=base)
        assert result['timeframe_minutes'] == minutes
        assert result['max_hold_hours'] == minutes/5

def test_no_setup_on_flat_market():
    assert analyze(history(), {'connection_status':'LIVE','best_ask':100}, 240*3600)['action'] == 'WAIT'
    assert replay(history(), 240*3600)['total_trades'] == 0

def test_invalid_price_rows_cannot_form_complete_bar():
    d = history()
    d.loc[239, 'high'] = float('inf')
    assert len(completed_8h(d, 240*3600)) == 29

def test_risk_halt_blocks_bollinger_candidate(monkeypatch):
    from app.api import endpoints
    monkeypatch.setattr(endpoints.market_data_service, 'fetch_candles_rest', lambda *a, **k: history())
    monkeypatch.setattr(endpoints.market_data_service, 'get_market_state', lambda: dict(is_data_safe=True, exchange_status='operational', best_bid=100, best_ask=101, spread_bps=1))
    monkeypatch.setattr(endpoints, 'get_risk_state', lambda: dict(is_halted=True))
    result = endpoints.bollinger8h_report()
    assert result['signal']['action'] == 'WAIT'
    assert not result['signal']['checks']['risk_governor_clear']
    assert len(result['stress_tests']) == 3

def test_signal_is_long_only_and_expires():
    d = history()
    # Entire penultimate bar closes below band; last bar reenters green.
    d.loc[224:231, ['open','high','low','close']] = [100,101,79,80]
    d.loc[232:239, ['open','high','low','close']] = [80,101,79,100]
    now=240*3600
    signal=analyze(d, {'connection_status':'LIVE','best_ask':100}, now)
    assert signal['action'] == 'BUY CANDIDATE'
    assert signal['stop_loss'] < 100 < signal['take_profit']
    assert analyze(d, {'connection_status':'LIVE','best_ask':100}, now+901)['action'] == 'WAIT'
    assert analyze(d, {'connection_status':'DISCONNECTED','best_ask':100}, now)['action'] == 'WAIT'
