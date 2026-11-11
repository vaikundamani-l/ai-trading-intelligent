# Validation — 29 October 2026

The platform remains a paper trading and research application. No live order execution is implemented.

## Measured prediction results

A chronological evaluation on 1,000 public Delta India BTCUSD five-minute candles yielded directional accuracy of 51.54%, 54.79%, 46.74%, and 47.06% for 5m, 15m, 30m, and 1h respectively. No horizon met the required Brier improvement over the historical class-frequency baseline. Forecasts are therefore withheld. Full metrics are in `backend/model_validation.json`.

This is one short historical window, not evidence of sustained predictive skill. Overlapping long-horizon outcomes are correlated. The validation threshold is an engineering gate, not a statistical significance claim.

The model combines standardized logistic regression and a regularized gradient boosting classifier, with chronological sigmoid calibration. Horizon-sized gaps separate training and evaluation, unknown future labels are excluded, and training and inference share the same feature builder. No model settings were tuned to this held-out result.

## Checks

20 automated Python tests pass, including freshness, streaming volume, completed candles, disconnected execution, and protection against clearing risk halts. Frontend lint and TypeScript checking pass. Live public ticker and historical candle requests succeeded. Container build verification is recorded separately in the completion message.

## Research references

- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://scikit-learn.org/stable/modules/calibration.html
- https://scikit-learn.org/stable/modules/model_evaluation.html

## Operational limitations

Historical OHLC data cannot reproduce executable order-book fills or queue priority. Paper fills and backtests remain approximations. A broader history and prospectively recorded predictions across different market regimes are required before claiming improved accuracy. Research strategies do not automatically become validated execution strategies.

## Activated deployment and expanded evaluation

Both production services were activated through Docker on 29 October 2026. The original SQLite portfolio was copied into the persistent container volume. Browser inspection confirmed live prices, strategy rationale, order-book data, the paper portfolio, and withheld forecasts.

Thirty days of public exchange history yielded 8,640 candles. Three chronological evaluation windows (5,184, 6,912, and 8,640 candles) were assessed without tuning model settings to the results. No horizon passed validation. On the full window, directional accuracy was 50.54%, 53.75%, 53.58%, and 51.07% for 5m, 15m, 30m, and 1h. Detailed results: `backend/research/history_validation.json`. Reproduce with `PYTHONPATH=backend OMP_NUM_THREADS=1 /home/shadow-khan/myenv/bin/python backend/research/evaluate_history.py`.

The running paper engine can now accumulate prospective trade results. Sustained forward performance has not yet been measured; an elapsed-time observation period is still required.

## Engine and paper interface upgrade — 30 October 2026

Added explicit five-check setup grading: completed SBR-5 setup, fresh safe data, spread <=2 bps, net target reward/risk >=1.2, and completed-bar EMA alignment. Automatic paper entries require every check. These additional filters are heuristic screening rules, not validated profitability or confidence percentages.

Prediction refresh runs separately every ten seconds so it cannot directly delay the position-monitoring loop. Slow WebSocket sends have a timeout. Paper controls now offer bounded stop distance and target multiples, live unrealized P&L before fees, and disabled entry buttons when market or account checks fail. ATR display now uses the server-calculated indicator.

Verification: 22 local tests, 16 backend container tests, frontend lint, TypeScript and Docker production builds passed. Browser inspection confirmed live market data, the five-check suggestion panel, customizable paper controls, and correctly disabled entries during an existing daily loss halt.
