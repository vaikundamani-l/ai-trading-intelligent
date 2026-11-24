# Engine research protocol — fixed before this run

The saved `winrate_candles.json` has been used in earlier project research. Chronological evaluation on it is **reused-sample diagnostics**, not an untouched holdout or independent proof. Network/DNS restrictions prevented a fresh exchange download in this session. Record the actual cadence and file SHA-256; never treat these 15m candles as 5m data or fabricate smaller bars.

Compare exactly three profiles, without a parameter sweep:

1. `baseline`: current big-move breakout/pullback conditions.
2. `trend_context`: baseline plus aligned EMA9/21, directional three-bar EMA21 slope and 12-bar path efficiency >= 0.25.
3. `trend_and_extension`: profile 2 plus entry candle close no more than two prior ATR from EMA21.

The alternatives are hypotheses motivated by trend persistence, not rules established by published BTC scalping research. The AQR time-series momentum study concerns much longer horizons and other instruments; it does not validate this intraday implementation.

Use only complete native or aggregated 15m, 30m, 1h, 4h, 1d candles. Reject missing constituents. Split time 60% development / 20% validation / 20% evaluation. Compute indicators causally using prior context. No signal or execution crosses from an earlier segment into a later segment. Close outstanding positions at the segment boundary using only that segment's data.

Select at most one profile per timeframe using development mean net bps, requiring >=30 development trades. Validation requires >=20 trades, positive mean and profit factor >=1.1; the evaluation period never changes selection. Disclose all 15 timeframe/profile trials. Require >=20 evaluation trades and positive lower block-bootstrap mean interval before even considering later forward observation. No automatic promotion from this reused data, regardless of apparent results.

Execution uses the current strategy evaluator with next-candle-open quotes and explicit entry time. Use one position per timeframe, no overlapping trades, 0.25% equity risk, <=2x notional, daily loss / losing streak / realized drawdown governors, conservative stop-first OHLC ambiguity and opening-gap stops. Fees are 5 bps per leg plus 18% GST, slippage 1 bp per leg. No scalper discount is assumed. Reports disclose realized-equity drawdown separately from intrabar drawdown, which this OHLC study does not establish.

Stress the same qualified opportunity schedule with (a) 3 bps slippage per leg, (b) doubled taker fees plus 3 bps slippage per leg, and (c) adverse funding debits of 1 and 5 bps per funding snapshot. Funding scenarios are assumptions, not actual funding history. A full exit candle is included when bounding funding exposure because intrabar exit time is unknown. A missing trade outcome is not a win. Fees on the exit use exit notional. Recompute scenario sizing and risk governors; stress does not search for replacement parameters.

Report trade counts, win rate, mean net bps, profit factor, equity return, realized maximum drawdown, maximum loss streak, direction breakdown, 5-trade circular-block bootstrap interval (seed 20261117, 500 samples). No annualized Sharpe claim for this small, sparse sample. No guaranteed win rate or prediction of every large move.

Sources reviewed 17 November 2026:
- https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf — repeated selection can overfit; a single split does not establish robust evidence.
- https://davidhbailey.com/dhbpapers/deflated-sharpe.pdf — selection and non-normality matter when interpreting performance estimates; DSR is not computed here.
- https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum — motivation for testing trend context, not evidence for these intraday thresholds.
- https://docs.delta.exchange/ — public candles, supported durations, 2000-row response maximum and funding-history symbol.
- https://www.delta.exchange/support/solutions?articleId=80001177869 — published futures maker/taker fees; account tiers can vary.
- https://prod-mobile-india.delta.exchange/fees — GST and fee-offer qualifications; no discount assumed.
- https://guides.delta.exchange/delta-exchange-india-user-guide/derivatives-guide/docs — funding mechanics; some contract intervals can change.
