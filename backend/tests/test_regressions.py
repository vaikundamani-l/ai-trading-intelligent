import time
import pandas as pd
from app.services.delta_market_data import DeltaMarketDataService
from app.strategies.alpha5_sbr5 import Alpha5SBR5

def test_heartbeat_does_not_refresh_price():
    service = DeltaMarketDataService()
    service.last_price = 80000
    service.last_update_ts = time.time() - 100
    service._handle_ws_message({'type': 'heartbeat'})
    assert service.get_market_state()['connection_status'] == 'DISCONNECTED'

def test_stream_updates_volume():
    service = DeltaMarketDataService()
    service.candles_5m = pd.DataFrame([dict(time=1800000000, open=80000., high=80010., low=79990., close=80000., volume=1.)])
    service._handle_ws_message(dict(type='candlestick_5m', res='5m', cst=1800000000000000, o=80000, h=80020, l=79990, c=80010, v=500))
    assert service.candles_5m.iloc[-1]['volume'] == 500

def test_future_candles_cannot_signal():
    future = int(time.time()) + 300
    candles = pd.DataFrame([dict(time=future+i*300, open=100., high=101., low=99., close=100., volume=100.) for i in range(30)])
    assert not Alpha5SBR5().evaluate(candles, {})['is_setup']

def test_prediction_features_exclude_unfinished_candles():
    from app.ml.prediction_engine import StatisticalAIPredictionEngine
    now = int(time.time())
    candles = pd.DataFrame([dict(time=now-300*(40-i), close=100.+i, high=102.+i, low=98.+i, volume=100.+i) for i in range(41)])
    features, cols = StatisticalAIPredictionEngine.build_features(candles)
    assert features.iloc[-1]['time'] + 300 <= time.time()
    assert features[cols].iloc[-1].notna().all()

def test_paper_execution_rejects_disconnected_market(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'DB_PATH', str(tmp_path/'paper.db'))
    from app.database import init_db
    init_db()
    from app.services.paper_trading import PaperTradingEngine
    engine = PaperTradingEngine()
    assert engine.execute_signal(dict(direction=1, stop_loss=79000, take_profit=82000), dict(connection_status='DISCONNECTED', best_ask=80000, best_bid=79999)) is None

def test_risk_halt_cannot_be_cleared_with_pause_button(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.config import settings
    monkeypatch.setattr(settings, 'DB_PATH', str(tmp_path/'risk.db'))
    from app.database import init_db, update_risk_state
    init_db()
    update_risk_state(9000, 4, 0, 1, 'Daily loss limit reached')
    from app.api.endpoints import toggle_engine
    with pytest.raises(HTTPException) as exc:
        toggle_engine()
    assert exc.value.status_code == 409

def test_paper_timeout_and_single_position(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app.config import settings
    monkeypatch.setattr(settings, 'DB_PATH', str(tmp_path/'orders.db'))
    from app.database import init_db, get_connection
    from app.strategies import alpha5_sbr5
    monkeypatch.setattr(alpha5_sbr5, 'funding_in_window', lambda *a: False)
    init_db()
    from app.services.paper_trading import PaperTradingEngine
    engine = PaperTradingEngine()
    market = dict(connection_status='LIVE', is_data_safe=True, best_ask=80001, best_bid=80000, last_price=80000)
    order = dict(direction=1, stop_loss=79700, take_profit=80600)
    assert engine.execute_signal(order, market) is not None
    assert engine.execute_signal(order, market) is None
    conn = get_connection()
    with conn:
        conn.execute('UPDATE paper_trades SET entry_time = ?', ((datetime.now(timezone.utc)-timedelta(minutes=26)).isoformat(),))
    conn.close()
    engine.update_open_positions(market)
    summary = engine.get_portfolio_summary()
    assert summary['open_position'] is None
    assert summary['closed_trades'][0]['exit_reason'] == 'time_limit_25m'
    assert summary['current_equity'] < 10000

def test_strong_suggestion_requires_every_gate():
    from app.suggestion_quality import assess_setup
    now = int(time.time())
    candles = pd.DataFrame([dict(time=now-(60-i)*300, close=100+i) for i in range(60)])
    decision = dict(status='ACTIVE_SETUP', direction=1, risk_reward=1.5)
    market = dict(is_data_safe=True, spread_bps=0.5)
    assert assess_setup(decision,market,candles)['eligible_for_auto_paper']
    market['spread_bps'] = 3
    assert not assess_setup(decision,market,candles)['eligible_for_auto_paper']
    market['spread_bps'] = 0.5
    decision['direction'] = -1
    assert not assess_setup(decision,market,candles)['eligible_for_auto_paper']

def test_missing_evidence_never_grades_strong():
    from app.suggestion_quality import assess_setup
    assert assess_setup({}, {}, pd.DataFrame())['grade'] == 'NO TRADE'
    assert not assess_setup(dict(status='ACTIVE_SETUP',direction=1,risk_reward=float('nan')), dict(is_data_safe=True,spread_bps=None), pd.DataFrame())['eligible_for_auto_paper']
