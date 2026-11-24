"""Meaningful rejection, causality and historical-execution regressions."""
from unittest.mock import patch
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.config import settings
from app.decision_engine import SignalDecisionEngine
from app.services.backtest_service import BacktestConfig, compute_sbr5_signals, simulate_trade
from app.strategies.alpha5_sbr5 import Alpha5SBR5
from app.strategies.engine_safety import completed_history, resolve_bar_exit
from app.strategies.momentum_context import context_masks
from test_selected_timeframe import history, chart


@pytest.mark.parametrize('column,value', [('low', -1), ('high', 9990), ('close', float('nan')),
    ('open', 0), ('volume', -10), ('volume', float('inf')), ('time', float('nan'))])
def test_invalid_completed_candles_cannot_generate_signals(column, value):
    df, entry, _ = history('5m')
    df.loc[70, column] = value
    result = Alpha5SBR5().evaluate(df, {}, as_of=entry)
    assert not result['is_setup']
    assert 'Invalid' in result['reasons'][0] or 'invalid' in result['reasons'][0] or 'non-finite' in result['reasons'][0]


@pytest.mark.parametrize('quote', [dict(best_bid=10050), dict(best_bid=-1, best_ask=10050),
    dict(best_bid=10051, best_ask=10050), dict(best_bid=10050, best_ask=float('nan'))])
def test_unsafe_quotes_rejected(quote):
    df, entry, _ = history('5m')
    assert not Alpha5SBR5().evaluate(df, quote, as_of=entry)['is_setup']


def test_entry_drift_gate_is_enforced_in_live_and_history():
    df, entry, seconds = history('4h')
    result = Alpha5SBR5().evaluate(df, dict(best_bid=10100, best_ask=10100), resolution='4h', as_of=entry)
    assert not result['is_setup'] and 'Entry drift' in result['reasons'][0]
    future = pd.DataFrame([dict(time=entry, open=10100, high=10101, low=10099, close=10100, volume=100)])
    extended = pd.concat([df.drop(columns='dt'), future], ignore_index=True)
    marked = chart(extended, '4h', entry + seconds)
    assert not marked['candles'][70]['signal']
    assert marked['signal_diagnostics']['filtered_reasons']['Entry moved too far'] == 1


def test_unfinished_bad_prices_do_not_contaminate_completed_signal():
    df, entry, _ = history('5m')
    future = df.iloc[[-1]].copy()
    future['time'] = entry
    future['close'] = np.nan
    extended = pd.concat([df, future], ignore_index=True)
    assert Alpha5SBR5().evaluate(extended, {}, as_of=entry + 1)['is_setup']


def test_context_masks_are_causal_and_do_not_fabricate_strength():
    df, _, _ = history('5m')
    df['close'] = np.linspace(10000, 10300, len(df))
    atr = pd.Series(20.0, index=df.index)
    long, short = context_masks(df, atr, 'trend_context')
    assert long.iloc[-1] and not short.iloc[-1]
    later = pd.concat([df, df.iloc[-5:].assign(close=1)], ignore_index=True)
    future_atr = pd.Series(20.0, index=later.index)
    assert context_masks(later, future_atr, 'trend_context')[0].iloc[70] == long.iloc[-1]
    df['close'] = 10000
    long, short = context_masks(df, atr, 'trend_context')
    assert not long.any() and not short.any()


def test_gap_and_ambiguous_ohlc_use_adverse_stop():
    assert resolve_bar_exit(dict(open=95, high=125, low=90, close=110), 1, 100, 120) == (95, 'STOP_HIT')
    assert resolve_bar_exit(dict(open=105, high=125, low=90, close=110), 1, 100, 120) == (100, 'STOP_HIT')
    assert resolve_bar_exit(dict(open=125, high=130, low=90, close=110), -1, 120, 100) == (125, 'STOP_HIT')


def test_backtest_respects_hourly_stop_policy_and_ignores_missing_entry():
    df, entry, seconds = history('4h')
    df[['open', 'close']] = 10000.0
    df['high'], df['low'] = 10060.0, 9940.0
    df.loc[70, ['open', 'high', 'low', 'close', 'volume']] = [10000, 10160, 9995, 10150, 300]
    future = pd.DataFrame([dict(time=entry + i * seconds, open=10150, high=10160, low=10140,
                                close=10150, volume=100) for i in range(5)])
    df = pd.concat([df.drop(columns='dt'), future], ignore_index=True)
    df['dt'] = pd.to_datetime(df.time, unit='s', utc=True)
    cfg = BacktestConfig(resolution='4h')
    signals = compute_sbr5_signals(df, cfg)
    trade = simulate_trade(signals, 70, 1, cfg, 10000)
    assert trade is not None
    live = Alpha5SBR5().evaluate(df.iloc[:71], {}, resolution='4h', as_of=entry)
    assert trade['stop'] == live['stop_loss'] and trade['target'] == live['take_profit']
    broken = signals.drop(index=71).reset_index(drop=True)
    assert simulate_trade(broken, 70, 1, cfg, 10000) is None


def test_engine_rejects_reported_or_actual_wide_spread_and_bad_data():
    df, entry, _ = history('5m')
    engine = SignalDecisionEngine(persist=False)
    market = dict(connection_status='LIVE', exchange_status='operational', best_bid=10050, best_ask=10050, spread_bps=4)
    with patch('time.time', return_value=entry + 1):
        assert engine.evaluate(df, market)['action'] == 'HALTED / DATA UNSAFE'
        market.update(best_ask=10060, spread_bps=0)
        assert engine.evaluate(df, market)['action'] == 'HALTED / DATA UNSAFE'
        market.update(best_ask=10050)
        df.loc[70, 'close'] = np.nan
        assert engine.evaluate(df, market)['action'] == 'HALTED / DATA UNSAFE'


def test_research_alpha_cannot_bypass_big_move_policy():
    assert settings.SCALP5_BIG_MOVE_ONLY
    assert not settings.ENABLE_RESEARCH_ALPHA2_SIGNALS
    assert not settings.ENABLE_RESEARCH_TRAILING_STOPS


def research_module():
    path = Path(__file__).parents[1] / 'research/strengthen_engine.py'
    spec = importlib.util.spec_from_file_location('strengthen_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_research_aggregation_never_upsamples_or_fills_gaps():
    research = research_module()
    source = pd.DataFrame([dict(time=i * 900, open=100, high=101, low=99, close=100, volume=100) for i in range(16)])
    assert len(research.aggregate(source, 3600, 900)) == 4
    assert len(research.aggregate(source.drop(index=2), 3600, 900)) == 3
    with pytest.raises(ValueError):
        research.aggregate(source, 300, 900)


def test_research_windows_never_execute_next_segment_prices():
    research = research_module()
    df, entry, _ = history('15m')
    # Signal is outside this segment; even an attractive following open must not enter.
    plan = Alpha5SBR5().evaluate(df, {}, resolution='15m', as_of=entry)
    future = pd.DataFrame([dict(time=entry, open=10050, high=20000, low=10050, close=19000, volume=100)])
    extended = pd.concat([df.drop(columns='dt'), future], ignore_index=True)
    result = research.evaluate_segment(extended, {70: plan}, '15m', entry, entry + 900)
    assert result['trades'] == 0


@pytest.mark.parametrize('kind', ['duplicate', 'unsorted'])
def test_duplicate_or_unsorted_candles_fail_closed(kind):
    df, entry, _ = history('5m')
    df = pd.concat([df, df.iloc[[-1]]], ignore_index=True) if kind == 'duplicate' else df.iloc[::-1]
    result = Alpha5SBR5().evaluate(df, {}, as_of=entry)
    assert not result['is_setup']
    assert 'duplicated or unsorted' in result['reasons'][0]


def test_paper_ohlc_cannot_apply_a_favorable_ratchet_before_adverse_touch(tmp_path, monkeypatch):
    from app.database import init_db
    from app.services.paper_trading import PaperTradingEngine
    from app.strategies import alpha5_sbr5
    monkeypatch.setattr(settings, 'DB_PATH', str(tmp_path / 'paper-risk.db'))
    monkeypatch.setattr(alpha5_sbr5, 'funding_in_window', lambda *args: False)
    init_db()
    engine = PaperTradingEngine()
    market = dict(connection_status='LIVE', is_data_safe=True, best_bid=80000, best_ask=80001, last_price=80000)
    assert engine.execute_signal(dict(direction=1, stop_loss=79700, take_profit=80600), market)
    engine.update_open_positions(market, dict(open=80000, high=80700, low=79600, close=80300))
    portfolio = engine.get_portfolio_summary()
    assert portfolio['open_position'] is None
    assert portfolio['current_equity'] < 10000


def test_engine_remains_fail_closed_when_feed_returns_none():
    result = SignalDecisionEngine(persist=False).evaluate(pd.DataFrame(), None)
    assert result['action'] == 'HALTED / DATA UNSAFE'
    assert not result['quality']['eligible_for_auto_paper']
