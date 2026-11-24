"""Selected-timeframe completion, live/chart parity and data isolation."""
from unittest.mock import patch

import pandas as pd
import pytest

from app.api import endpoints
from app.strategies.alpha5_sbr5 import Alpha5SBR5, funding_in_window
from app.timeframes import TIMEFRAME_SECONDS
from test_scalping_signals import momentum_history


def history(resolution):
    duration = TIMEFRAME_SECONDS[resolution]
    entry = int(pd.Timestamp('2026-10-10T09:00:00Z').timestamp())
    df = momentum_history()
    df['time'] = [entry - (len(df) - i) * duration for i in range(len(df))]
    df['dt'] = pd.to_datetime(df['time'], unit='s', utc=True)
    return df, entry, duration


def chart(df, resolution, now):
    with patch.object(endpoints.market_data_service, 'fetch_candles_rest', return_value=df), \
         patch.object(endpoints, 'get_recent_signals', return_value=[]), \
         patch('time.time', return_value=now):
        return endpoints.get_candles(resolution=resolution, limit=len(df))


@pytest.mark.parametrize('resolution', TIMEFRAME_SECONDS)
def test_each_timeframe_closes_and_replays_its_own_candles(resolution):
    df, entry, duration = history(resolution)
    strategy = Alpha5SBR5()
    assert not strategy.evaluate(df, {}, as_of=entry - 1, resolution=resolution)['is_setup']
    live = strategy.evaluate(df, {}, as_of=entry, resolution=resolution)
    assert live['is_setup'], live
    assert live['resolution'] == resolution
    assert live['bar_seconds'] == duration
    assert live['max_hold_seconds'] == 5 * duration
    assert live['valid_until_ts'] == entry + min(120, duration)
    marker = chart(df, resolution, entry)['candles'][-1]
    assert marker['signal'] == live['action']
    assert marker['signal_stop'] == live['stop_loss']
    assert marker['signal_target'] == live['take_profit']
    assert not chart(df, resolution, entry - 1)['candles'][-1]['signal']


@pytest.mark.parametrize('resolution', TIMEFRAME_SECONDS)
def test_current_signal_uses_selected_history_and_keeps_ledgers_separate(resolution):
    df, entry, duration = history(resolution)
    state = dict(connection_status='LIVE', exchange_status='operational', is_data_safe=True,
                 last_price=10050, mark_price=10050, best_bid=10050, best_ask=10050, spread_bps=0.5)
    engine = endpoints.decision_engine if resolution == '5m' else endpoints.timeframe_engines[resolution]
    engine.dislocation.cooldown_until_ts = 0
    with patch.object(endpoints.market_data_service, 'fetch_candles_rest', return_value=df) as fetch, \
         patch.object(endpoints.market_data_service, 'candles_5m', df), \
         patch.object(endpoints.market_data_service, 'get_market_state', return_value=state), \
         patch.object(engine, '_get_risk_state', return_value={}), \
         patch.object(engine, '_persist_signal') as persist, \
         patch('time.time', return_value=entry + 1):
        result = endpoints.get_current_signal(resolution=resolution)
        assert result['action'] == 'BUY', result
        assert result['resolution'] == resolution
        assert result['max_hold_seconds'] == 5 * duration
        if resolution != '5m':
            fetch.assert_called_once_with(resolution=resolution, count=250)
            persist.assert_not_called()
        else:
            fetch.assert_not_called()
        with patch('time.time', return_value=entry + min(120, duration) + 1):
            expired = endpoints.get_current_signal(resolution=resolution)
            assert expired['action'] == 'WAIT / NO TRADE'
            assert expired['status'] in ('EXPIRED_SETUP', 'STALE_CANDLES')


@pytest.mark.parametrize('resolution', TIMEFRAME_SECONDS)
def test_timeout_waits_for_five_selected_candles_to_close(resolution):
    df, entry, duration = history(resolution)
    future = pd.DataFrame([dict(time=entry + i * duration, open=10050, high=10052,
                                low=10048, close=10050, volume=100) for i in range(5)])
    future['dt'] = pd.to_datetime(future['time'], unit='s', utc=True)
    extended = pd.concat([df, future], ignore_index=True)
    assert chart(extended, resolution, entry + 5 * duration - 1)['candles'][70]['signal_outcome'] == 'ACTIVE'
    assert chart(extended, resolution, entry + 5 * duration)['candles'][70]['signal_outcome'] == 'TIME_EXIT'


def test_funding_uses_selected_duration_and_long_holds_disclose_exposure():
    entry = int(pd.Timestamp('2026-10-10T15:30:00Z').timestamp())
    assert not funding_in_window(entry, 5, 120, bar_seconds=60)
    assert funding_in_window(entry, 5, 120, bar_seconds=900)
    df, _, duration = history('1d')
    # Real daily boundaries coincide with funding. A multi-day observation
    # must disclose funding rather than be permanently impossible.
    df['time'] -= 9 * 3600
    signal = Alpha5SBR5().evaluate(df, {}, as_of=int(df.iloc[-1]['time']) + duration, resolution='1d')
    assert signal['is_setup']
    assert signal['funding_exposure']
    assert any('funding charges' in risk for risk in signal['invalidation_risks'])


def test_selected_signal_rejects_stale_history_and_wrong_interval():
    df, entry, duration = history('15m')
    with patch.object(endpoints.market_data_service, 'fetch_candles_rest', return_value=df), \
         patch('time.time', return_value=entry + 3 * duration):
        assert endpoints.get_current_signal(resolution='15m')['status'] == 'STALE_CANDLES'
    assert not Alpha5SBR5().evaluate(df, {}, as_of=entry, resolution='1m')['is_setup']


@pytest.mark.parametrize('resolution', ['1h', '4h', '1d'])
@pytest.mark.parametrize('direction', [1, -1])
def test_hourly_daily_stop_limit_adapts_to_realistic_atr_without_changing_scalping(resolution, direction):
    df, entry, _ = history(resolution)
    df[['open', 'close']] = 10000.0
    df['high'], df['low'] = 10060.0, 9940.0  # Prior ATR = 1.2%, not the old 0.2% fixture.
    df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10000, 10160, 9995, 10150, 300]
    if direction == -1:
        df[['open', 'close']] = 20000 - df[['open', 'close']]
        high, low = df['high'].copy(), df['low'].copy()
        df['high'], df['low'] = 20000 - low, 20000 - high
    strategy = Alpha5SBR5()
    signal = strategy.evaluate(df, {}, resolution=resolution, as_of=entry)
    assert signal['is_setup'], signal
    assert signal['direction'] == direction
    assert abs(signal['entry_price'] - signal['stop_loss']) / signal['entry_price'] > 0.008
    assert 0.008 < signal['max_stop_fraction'] <= 0.08
    result = chart(df, resolution, entry)
    assert result['candles'][-1]['signal'] == signal['action']
    assert result['signal_diagnostics']['qualified_count'] == 1
    assert result['signal_diagnostics']['filtered_count'] == 0
    # The original fixed scalp ceiling really would have rejected this case.
    with patch.object(endpoints.settings, 'HIGHER_TF_STOP_ATR_MULTIPLIER', 0):
        rejected = strategy.evaluate(df, {}, resolution=resolution, as_of=entry)
        assert not rejected['is_setup'] and 'Stop distance' in rejected['reasons'][0]
    df['time'] = [entry - (len(df) - i) * 300 for i in range(len(df))]
    rejected = strategy.evaluate(df, {}, resolution='5m', as_of=entry)
    assert not rejected['is_setup'] and 'Stop distance' in rejected['reasons'][0]


def test_chart_explains_zero_signals_and_still_rejects_excessive_stop():
    df, entry, _ = history('4h')
    df[['open', 'close']] = 10000.0
    df['high'], df['low'] = 10060.0, 9940.0
    df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10000, 10160, 9700, 10150, 300]
    result = chart(df, '4h', entry)
    assert not result['candles'][-1]['signal']
    diagnostics = result['signal_diagnostics']
    assert diagnostics['candidate_count'] == 1
    assert diagnostics['qualified_count'] == 0
    assert diagnostics['filtered_reasons']['Stop distance too wide'] == 1
    df['volume'] = 100
    assert chart(df, '4h', entry)['signal_diagnostics']['candidate_count'] == 0
