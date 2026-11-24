"""Offline, reproducible engine comparison. No orders, network or ledger changes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import settings
from app.services.backtest_service import BacktestConfig, compute_sbr5_signals
from app.strategies.alpha5_sbr5 import Alpha5SBR5
from app.strategies.engine_safety import completed_history, resolve_bar_exit
from app.strategies.momentum_context import PROFILES
from app.timeframes import TIMEFRAME_SECONDS

ROOT = Path(__file__).resolve().parent


def aggregate(source, seconds, base):
    if seconds < base or seconds % base:
        raise ValueError('Cannot reconstruct a finer timeframe from coarse candles')
    grouped = source.assign(bucket=(source.time // seconds).astype('int64') * seconds).groupby('bucket')
    rows = []
    for timestamp, group in grouped:
        expected = np.arange(timestamp, timestamp + seconds, base)
        if not np.array_equal(group.time.to_numpy(), expected):
            continue
        rows.append(dict(time=int(timestamp), open=float(group.iloc[0].open),
                         high=float(group.high.max()), low=float(group.low.min()),
                         close=float(group.iloc[-1].close), volume=float(group.volume.sum())))
    return pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])


def prepare_plans(d, resolution, profile):
    seconds = TIMEFRAME_SECONDS[resolution]
    cfg = BacktestConfig(resolution=resolution, context_profile=profile)
    signals = compute_sbr5_signals(d, cfg)
    strategy, plans, rejected = Alpha5SBR5(), {}, Counter()
    for i in range(26, len(d) - 1):
        if not (signals.iloc[i].long_signal or signals.iloc[i].short_signal):
            continue
        signal, entry = d.iloc[i], d.iloc[i + 1]
        if entry.time != signal.time + seconds:
            rejected['missing_entry_bar'] += 1
            continue
        price = float(entry.open)
        plan = strategy.evaluate(d.iloc[:i + 1],
            dict(best_bid=price, best_ask=price, entry_time=int(entry.time)),
            as_of=int(entry.time), resolution=resolution, context_profile=profile)
        if plan.get('is_setup'):
            plans[i] = plan
        else:
            reason = plan.get('reasons', ['unknown'])[0]
            key = ('funding' if 'Funding snapshot' in reason else 'entry_drift' if 'Entry drift' in reason
                   else 'stop_distance' if 'Stop distance' in reason else 'target_costs' if 'target' in reason.lower()
                   else 'other')
            rejected[key] += 1
    return plans, dict(rejected)


def bootstrap_mean(values):
    if not values:
        return None
    x = np.asarray(values)
    rng = np.random.default_rng(20261117)
    count, block = len(x), min(5, len(x))
    starts = rng.integers(0, count, size=(500, (count + block - 1) // block))
    indices = ((starts[..., None] + np.arange(block)) % count).reshape(500, -1)[:, :count]
    return [round(float(v), 3) for v in np.quantile(x[indices].mean(axis=1), [0.025, 0.975])]


def summarize(trades, equity_curve):
    values = [t['net_bps'] for t in trades]
    positive = sum(max(t['pnl'], 0) for t in trades)
    negative = -sum(min(t['pnl'], 0) for t in trades)
    peak, drawdown, streak, max_streak = equity_curve[0], 0.0, 0, 0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    for trade in trades:
        streak = streak + 1 if trade['pnl'] <= 0 else 0
        max_streak = max(max_streak, streak)
    return dict(trades=len(trades), wins=sum(v > 0 for v in values),
                win_rate_pct=round(100 * sum(v > 0 for v in values) / len(values), 2) if values else None,
                mean_net_bps=round(float(np.mean(values)), 3) if values else None,
                mean_net_bps_block_interval_95=bootstrap_mean(values),
                profit_factor=round(positive / negative, 3) if negative else None,
                equity_return_pct=round(100 * (equity_curve[-1] / equity_curve[0] - 1), 3),
                realized_max_drawdown_pct=round(100 * drawdown, 3), max_loss_streak=max_streak,
                long_trades=sum(t['direction'] == 1 for t in trades),
                short_trades=sum(t['direction'] == -1 for t in trades),
                funding_snapshot_exposures=sum(t['funding_snapshots'] for t in trades))


def evaluate_segment(d, plans, resolution, begin, end, *, slip_bps=1, fee_bps=5, funding_bps=0):
    seconds, cfg = TIMEFRAME_SECONDS[resolution], BacktestConfig()
    allowed = d[(d.time >= begin) & (d.time + seconds <= end)]
    if allowed.empty:
        return summarize([], [10000.0])
    final_index = int(allowed.index[-1])
    equity, peak, day_start, day, losing, cooldown = 10000.0, 10000.0, 10000.0, None, 0, -1
    records, curve, busy_until = [], [equity], -1
    for index, plan in sorted(plans.items()):
        i = index + 1
        if index < busy_until or i > final_index or d.iloc[index].time < begin:
            continue
        bar = d.iloc[i]
        if bar.time < begin or bar.time + seconds > end:
            continue
        today = int(bar.time) // 86400
        if today != day:
            day, day_start = today, equity
        if i < cooldown or equity <= day_start * (1 - cfg.daily_loss_limit_fraction):
            continue
        if equity <= peak * (1 - cfg.peak_drawdown_kill_fraction):
            break
        direction = plan['direction']
        slip = slip_bps / 10000
        entry = float(bar.open) * (1 + direction * slip)
        stop, target = plan['stop_loss'], plan['take_profit']
        risk = direction * (entry - stop) / entry
        if risk <= 0:
            continue
        risk_cost = 2 * fee_bps / 10000 * settings.GST_MULTIPLIER + 2 * slip
        notional = min(equity * cfg.max_risk_fraction / (risk + risk_cost),
                       equity * cfg.max_notional_equity_multiple)
        lot = entry * settings.CONTRACT_SIZE
        notional = np.floor(notional / lot) * lot
        if notional <= 0:
            continue
        result, exit_index, missing = None, None, False
        last_index = min(i + plan['max_hold_bars'] - 1, final_index)
        for j in range(i, last_index + 1):
            if d.iloc[j].time != bar.time + (j - i) * seconds:
                missing = True
                break
            result = resolve_bar_exit(d.iloc[j], direction, stop, target, timeout=j == last_index)
            if result is not None:
                exit_index = j
                break
        if missing or result is None:
            # Missing execution data invalidates reconstruction; do not skip
            # the unknown risk and resume a supposedly complete portfolio.
            break
        base_exit, reason = result
        exit_price = base_exit * (1 - direction * slip)
        fees = fee_bps / 10000 * settings.GST_MULTIPLIER * (1 + exit_price / entry)
        left, right = int(bar.time), int(d.iloc[exit_index].time + seconds)
        interval = settings.FUNDING_INTERVAL_SEC
        snapshots = max(0, right // interval - ((left - 1) // interval))
        net = direction * (exit_price - entry) / entry - fees - snapshots * funding_bps / 10000
        pnl = float(notional * net)
        equity += pnl
        peak = max(peak, equity)
        curve.append(equity)
        records.append(dict(net_bps=float(net * 10000), pnl=pnl, direction=direction,
                            funding_snapshots=snapshots, reason=reason))
        busy_until = exit_index
        losing = losing + 1 if pnl <= 0 else 0
        if losing >= cfg.max_consecutive_losses:
            cooldown, losing = exit_index + 1 + cfg.cooldown_bars, 0
    return summarize(records, curve)


def run(input_path, output_path):
    if not settings.SCALP5_BIG_MOVE_ONLY:
        raise ValueError('Protocol requires big-move-only mode; no silent change of study baseline')
    payload = input_path.read_bytes()
    source = pd.DataFrame(json.loads(payload)).sort_values('time').reset_index(drop=True)
    diffs = source.time.diff().dropna()
    base = int(diffs.mode().iloc[0])
    source = completed_history(source, base, float('inf'))
    start, end = int(source.time.min()), int(source.time.max()) + base
    split1, split2 = start + int((end - start) * 0.6), start + int((end - start) * 0.8)
    segments = dict(development=(start, split1), validation=(split1, split2), evaluation=(split2, end))
    comparisons = []
    for resolution, seconds in TIMEFRAME_SECONDS.items():
        if seconds < base:
            continue
        bars = aggregate(source, seconds, base)
        row = dict(resolution=resolution, bars=len(bars), profiles=[])
        for profile in PROFILES:
            plans, rejected = prepare_plans(bars, resolution, profile)
            metrics = {name: evaluate_segment(bars, plans, resolution, *bounds)
                       for name, bounds in segments.items()}
            stress = {name: evaluate_segment(bars, plans, resolution, *segments['evaluation'], **kwargs)
                      for name, kwargs in (
                          ('slippage_3bps', dict(slip_bps=3)),
                          ('double_fees_slippage_3bps', dict(slip_bps=3, fee_bps=10)),
                          ('adverse_funding_1bp', dict(funding_bps=1)),
                          ('adverse_funding_5bps', dict(funding_bps=5)))}
            row['profiles'].append(dict(profile=profile, qualified_opportunities=len(plans),
                                        rejected_candidates=rejected, segments=metrics, evaluation_stress=stress))
        eligible = [p for p in row['profiles'] if p['segments']['development']['trades'] >= 30]
        selected = max(eligible, key=lambda p: p['segments']['development']['mean_net_bps']) if eligible else None
        row['development_selected_profile'] = selected['profile'] if selected else None
        row['validation_passed'] = bool(selected and selected['segments']['validation']['trades'] >= 20
            and (selected['segments']['validation']['mean_net_bps'] or 0) > 0
            and (selected['segments']['validation']['profit_factor'] or 0) >= 1.1)
        comparisons.append(row)
        print(f"{resolution}: {len(bars)} complete bars; baseline opportunities={row['profiles'][0]['qualified_opportunities']}; development selection={row['development_selected_profile']}", flush=True)
    result = dict(protocol='ENGINE_RESEARCH_PROTOCOL.md', dataset=dict(path=str(input_path), sha256=hashlib.sha256(payload).hexdigest(),
                  rows=len(source), base_seconds=base, missing_intervals=int((diffs != base).sum()),
                  start_utc=pd.Timestamp(start, unit='s', tz='UTC').isoformat(), end_utc=pd.Timestamp(end, unit='s', tz='UTC').isoformat(),
                  previously_used_in_research=True, independent_holdout=False),
                  execution_assumptions=dict(base_fee_per_leg_bps=5, gst_multiplier=settings.GST_MULTIPLIER,
                      base_slip_per_leg_bps=1, funding_interval_seconds=settings.FUNDING_INTERVAL_SEC,
                      max_risk_fraction=settings.MAX_RISK_FRACTION, max_entry_deviation_fraction=settings.MAX_ENTRY_DEVIATION_FRACTION,
                      higher_tf_stop_atr_multiplier=settings.HIGHER_TF_STOP_ATR_MULTIPLIER,
                      higher_tf_max_stop_fraction=settings.HIGHER_TF_MAX_STOP_FRACTION,
                      context_profiles_are_hypotheses=True),
                  splits={k: [pd.Timestamp(t, unit='s', tz='UTC').isoformat() for t in v] for k, v in segments.items()},
                  compared_profiles=list(PROFILES), trial_count=len(comparisons) * len(PROFILES), comparisons=comparisons,
                  promotion='NO PREDICTIVE FILTER PROMOTED: reused data and insufficient independent evidence',
                  limitations=['No 1m/3m/5m evidence can be derived from 15m candles.',
                    'Funding scenarios are adverse assumptions, not historical funding measurements.',
                    'OHLC cannot establish execution queue, spread history, intrabar order or mark-to-market drawdown.',
                    'Bootstrap intervals on sparse dependent trades do not resolve strategy-selection bias.',
                    'No full portfolio claim across correlated timeframes; portfolios are evaluated separately.'])
    output_path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'winrate_candles.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'engine_strengthening_results.json')
    args = parser.parse_args()
    run(args.input, args.output)
