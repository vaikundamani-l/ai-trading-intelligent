"""Regression cases for chart/live SBR parity and countertrend filtering."""
from unittest.mock import patch

import pandas as pd
import pytest

from app.api.endpoints import get_candles
from app.config import settings
from app.services.backtest_service import BacktestConfig, compute_sbr5_signals
from app.strategies.alpha5_sbr5 import Alpha5SBR5
from test_backend import make_test_candles


@pytest.fixture(autouse=True)
def normal_mode_for_existing_regressions(monkeypatch):
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', False)


def trending_sweep(direction):
    times = pd.date_range('2026-10-10T01:00:00Z', periods=71, freq='5min')
    closes = [10500 - i * 5 for i in range(71)]
    df = pd.DataFrame({'time': times.astype('int64') // 10**9, 'dt': times,
                       'open': closes, 'close': closes,
                       'high': [c + 10 for c in closes],
                       'low': [c - 10 for c in closes], 'volume': 100.0})
    low = df.iloc[:70].tail(24)['low'].min()
    df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [low + 4, low + 10, low - 20, low + 5, 300]
    if direction == -1:
        df[['open', 'close']] = 20000 - df[['open', 'close']]
        high, low = df['high'].copy(), df['low'].copy()
        df['high'], df['low'] = 20000 - low, 20000 - high
    return df


@pytest.mark.parametrize('direction', [1, -1])
def test_strong_opposing_trend_blocks_live_and_replay(direction):
    df = trending_sweep(direction)
    strategy = Alpha5SBR5()
    price = float(df.iloc[-1]['close'])
    market = {'best_bid': price, 'best_ask': price}
    with patch.object(settings, 'SBR5_TREND_FILTER', False):
        assert strategy.evaluate(df, market)['is_setup']
    live = strategy.evaluate(df, market)
    assert not live['is_setup']
    assert 'opposing' in live['reasons'][0]
    col = 'long_signal' if direction == 1 else 'short_signal'
    assert compute_sbr5_signals(df, BacktestConfig(big_move_only=False, trend_filter=False)).iloc[-1][col]
    assert not compute_sbr5_signals(df, BacktestConfig(big_move_only=False, )).iloc[-1][col]
    # Appending future bars cannot change the decision for an earlier candle.
    extended = pd.concat([df, df.iloc[-10:].assign(close=20000)], ignore_index=True)
    assert not compute_sbr5_signals(extended, BacktestConfig(big_move_only=False, )).iloc[70][col]


def chart(df, resolution='5m', now=None):
    now = now if now is not None else float(df.iloc[-1]['time']) + 301
    with patch('app.api.endpoints.market_data_service.fetch_candles_rest', return_value=df), \
         patch('app.api.endpoints.get_recent_signals', return_value=[]), \
         patch('app.api.endpoints.time.time', return_value=now):
        return get_candles(resolution=resolution, limit=len(df))


@pytest.mark.parametrize('resolution', ['1m', '3m', '15m', '1h'])
def test_incompatible_candle_spacing_cannot_be_reinterpreted(resolution):
    assert chart(make_test_candles(), resolution)['passed_signals'] == []


def test_open_candle_cannot_emit_marker():
    df = make_test_candles().iloc[:51]
    result = chart(df, now=float(df.iloc[-1]['time']) + 150)
    assert result['passed_signals'] == []


def test_chart_levels_match_live_and_net_result_includes_costs():
    df = make_test_candles()
    result = chart(df)
    marked = result['candles'][50]
    next_open = float(df.iloc[51]['open'])
    t = int(df.iloc[50]['time'])
    live = Alpha5SBR5().evaluate(df.iloc[:51],
        {'best_bid': next_open, 'best_ask': next_open, 'entry_time': t + 300}, as_of=t + 300)
    for chart_key, live_key in [('signal_price', 'entry_price'), ('signal_stop', 'stop_loss'), ('signal_target', 'take_profit')]:
        assert marked[chart_key] == live[live_key]
    assert marked['signal_stop'] < marked['signal_price'] * (1 - settings.SBR5_MIN_STOP_FRACTION)
    assert marked['signal_pnl_r'] < 1.8


def test_chart_applies_funding_and_excessive_stop_gates():
    df = make_test_candles()
    # Move signal's next open to 07:45 UTC: funding falls inside holding window.
    desired = pd.Timestamp('2026-10-10T07:45:00Z').timestamp()
    df['time'] += int(desired - df.iloc[51]['time'])
    assert chart(df)['passed_signals'] == []
    df = make_test_candles()
    df.loc[50, 'low'] = 9000
    assert chart(df)['passed_signals'] == []


def test_gap_stop_and_incomplete_timeout_are_conservative():
    df = make_test_candles()
    # Preserve entry at next open, then gap through the resulting stop later.
    df.loc[51, ['open', 'high', 'low', 'close']] = [10006, 10010, 10000, 10005]
    df.loc[52, ['open', 'high', 'low', 'close']] = [9800, 9810, 9790, 9800]
    marked = chart(df)['candles'][50]
    assert marked['signal_outcome'] == 'STOP_HIT'
    assert marked['signal_exit_price'] < 9800
    assert marked['signal_pnl_r'] < -1
    df = make_test_candles().iloc[:56].copy()
    df.loc[51:55, ['high', 'low', 'close']] = [10010, 10000, 10005]
    now = float(df.iloc[-1]['time']) + 150
    assert chart(df, now=now)['candles'][50]['signal_outcome'] == 'ACTIVE'
    assert chart(df, now=now + 150)['candles'][50]['signal_outcome'] == 'TIME_EXIT'


def momentum_history(direction=1, pullback=False):
    df = make_test_candles(rows=90).iloc[:71].copy()
    df[['open', 'close']] = 10000.0
    df['high'], df['low'], df['volume'] = 10010.0, 9990.0, 100.0
    if pullback:
        prices = pd.Series([10000 + i * 3 for i in range(71)])
        df['open'], df['close'] = prices, prices
        df['high'], df['low'] = prices + 4, prices - 4
        df.loc[66, 'high'] += 80  # Not a range breakout: earlier resistance remains.
        df.loc[69, 'low'] -= 20  # Prior candle pulls back through EMA9.
        df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10204, 10224, 10202, 10222, 150]
    else:
        df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10000, 10055, 9999, 10050, 300]
    if direction == -1:
        df[['open', 'close']] = 20000 - df[['open', 'close']]
        high, low = df['high'].copy(), df['low'].copy()
        df['high'], df['low'] = 20000 - low, 20000 - high
    return df


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('pullback', [False, True])
def test_momentum_breakout_and_pullback_live_replay_chart_parity(direction, pullback):
    df = momentum_history(direction, pullback)
    t, px = int(df.iloc[-1]['time']), float(df.iloc[-1]['close'])
    strategy = Alpha5SBR5()
    live = strategy.evaluate(df, {'best_bid': px, 'best_ask': px}, as_of=t + 300)
    assert live['is_setup'], live
    assert live['direction'] == direction
    assert ('PULLBACK' if pullback else 'BREAKOUT') in live['strategy']
    col = 'long_signal' if direction == 1 else 'short_signal'
    assert compute_sbr5_signals(df, BacktestConfig(big_move_only=False, )).iloc[-1][col]
    assert not compute_sbr5_signals(df, BacktestConfig(big_move_only=False, momentum_enabled=False)).iloc[-1][col]
    marked = chart(df)['candles'][-1]
    assert marked['signal'] == live['action']
    assert marked['signal_stop'] == live['stop_loss']
    assert marked['signal_target'] == live['take_profit']
    # Changing/appending a future bar cannot insert an earlier signal.
    future = df.iloc[[-1]].copy()
    future['time'] += 300
    future['close'] *= 1.1
    extended = pd.concat([df, future], ignore_index=True)
    assert compute_sbr5_signals(extended, BacktestConfig(big_move_only=False, )).iloc[70][col]
    assert not strategy.evaluate(df, {}, as_of=t + 150)['is_setup']


@pytest.mark.parametrize('direction', [1, -1])
def test_momentum_rejects_weak_volume_and_rejection_wick(direction):
    df = momentum_history(direction)
    df.loc[70, 'volume'] = 50
    assert not Alpha5SBR5().evaluate(df, {})['is_setup']
    df = momentum_history(direction)
    df.loc[70, 'high' if direction == 1 else 'low'] = 10200 if direction == 1 else 9800
    assert not Alpha5SBR5().evaluate(df, {})['is_setup']


def test_new_impulse_blocks_fading_before_slow_ema_catches_up():
    from app.strategies.sbr_filters import opposing_trend_masks
    df = trending_sweep(1)
    df.loc[67:69, 'close'] = [10260, 10340, 10420]
    atr = pd.Series(20.0, index=df.index)
    _, block_short = opposing_trend_masks(df, atr)
    assert block_short.iloc[-1]


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('pullback', [False, True])
def test_big_move_mode_accepts_strong_moves_live_chart_replay(monkeypatch, direction, pullback):
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', True)
    df = momentum_history(1, pullback)
    if pullback:
        df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10204, 10264, 10202, 10260, 250]
    if direction == -1:
        df[['open', 'close']] = 20000 - df[['open', 'close']]
        high, low = df['high'].copy(), df['low'].copy()
        df['high'], df['low'] = 20000 - low, 20000 - high
    px = float(df.iloc[-1]['close'])
    result = Alpha5SBR5().evaluate(df, {'best_bid': px, 'best_ask': px})
    assert result['is_setup'], result
    assert result['direction'] == direction
    assert 'BIG MOVE ONLY' in result['strategy']
    replay = compute_sbr5_signals(df, BacktestConfig())
    assert replay.iloc[-1]['long_signal' if direction == 1 else 'short_signal']
    assert chart(df)['candles'][-1]['signal'] == result['action']


@pytest.mark.parametrize('direction', [1, -1])
def test_big_move_mode_ignores_small_valid_momentum(monkeypatch, direction):
    df = momentum_history(direction, pullback=True)
    assert Alpha5SBR5().evaluate(df, {})['is_setup']  # Normal mode.
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', True)
    assert not Alpha5SBR5().evaluate(df, {})['is_setup']
    assert not chart(df)['candles'][-1]['signal']
    replay = compute_sbr5_signals(df, BacktestConfig())
    assert not replay.iloc[-1]['long_signal'] and not replay.iloc[-1]['short_signal']


def test_big_move_mode_excludes_pure_sweep_reversals(monkeypatch):
    df = make_test_candles().iloc[:51]
    assert Alpha5SBR5().evaluate(df, {})['is_setup']
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', True)
    assert not Alpha5SBR5().evaluate(df, {})['is_setup']
    assert chart(df)['passed_signals'] == []


def test_big_move_mode_rejects_low_volume_and_choppy_path(monkeypatch):
    from app.strategies.big_move import big_move_masks
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', True)
    df = momentum_history()
    df.loc[70, 'volume'] = 150  # Passes normal 1.25x, fails big-move 1.75x.
    assert not Alpha5SBR5().evaluate(df, {})['is_setup']
    df = momentum_history()
    df.loc[68:70, 'close'] = [10060, 9990, 10050]
    df.loc[70, 'open'] = 9990
    allowed_long, _ = big_move_masks(df, pd.Series(20.0, index=df.index), pd.Series(100.0, index=df.index))
    assert not allowed_long.iloc[-1]  # Large net move but inefficient zigzag path.


def test_small_projected_target_rejected_live_chart_and_simulation(monkeypatch):
    from app.services.backtest_service import simulate_trade
    monkeypatch.setattr(settings, 'SCALP5_BIG_MOVE_ONLY', True)
    df = momentum_history()
    df['high'], df['low'] = df['close'] + 2, df['close'] - 2
    df.loc[68, ['open', 'high', 'low', 'close']] = [10012, 10014, 10010, 10012]
    df.loc[69, ['open', 'high', 'low', 'close']] = [10024, 10026, 10022, 10024]
    df.loc[70, ['open', 'high', 'low', 'close']] = [10024, 10042, 10023, 10040]
    cfg = BacktestConfig()
    replay = compute_sbr5_signals(df, cfg)
    assert replay.iloc[-1]['long_signal']  # Real momentum, insufficient projected target.
    result = Alpha5SBR5().evaluate(df, {'best_ask': 10040, 'best_bid': 10040})
    assert not result['is_setup']
    assert 'Small target' in result['reasons'][0]
    assert not chart(df)['candles'][-1]['signal']
    next_bar = df.iloc[[-1]].copy()
    next_bar['time'] += 300
    next_bar['dt'] += pd.Timedelta(minutes=5)
    next_bar['open'] = 10040
    extended = pd.concat([df, next_bar], ignore_index=True)
    assert simulate_trade(compute_sbr5_signals(extended, cfg), 70, 1, cfg, 10000) is None


def test_big_move_target_cost_thresholds_and_default():
    from app.config import Settings
    from app.strategies.big_move import substantial_target
    assert Settings().SCALP5_BIG_MOVE_ONLY
    assert BacktestConfig().big_move_only
    assert substantial_target(0.005, 0.00138)
    assert not substantial_target(0.0049, 0.001)
    assert not substantial_target(0.005, 0.0016)
    assert not substantial_target(0.006, 0.0021)
