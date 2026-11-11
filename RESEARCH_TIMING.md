# Trade timing research and implementation

Reviewed 9 November 2026.

John Bollinger's official rules explain that band tags alone do not establish buy or sell signals; price can walk a band in trending markets. The implementation therefore retains the two completed-candle re-entry confirmation rather than issuing entries on a band touch.

Source: https://www.bollingerbands.com/bollinger-band-rules

Bailey, Borwein, López de Prado and Zhu describe the risk of selecting strategies based on repeated backtest searches. Nearby parameter tests are sensitivity diagnostics, not independent evidence of a profitable strategy. The application retains the specified band multiplier and displays 1.7/1.9 alternatives and doubled-cost results without choosing a winner.

Source: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

## Applied changes

- The 8H report checks market freshness, operational exchange status, bid/ask ordering, spread, risk halt and cooldown before displaying a buy candidate.
- Invalid hourly OHLC rows are excluded. Incomplete 8H groups never become signals. Simulation is withheld when missing bars prevent reliable exit reconstruction.
- The dashboard presents 5m SBR-5 and 8H BB separately, with entry/stop/target, next candle-close timers, and reasons to wait. Timer completion is not a trade signal.
- A stale 8H response or stale fast decision cannot keep a ready suggestion visible. The UI distinguishes short entries from exits of a long-only strategy.

## Evidence limits

No newly established predictive advantage is claimed. The available 1,000-hour history is approximately 41 days, which is small for a slow 8H strategy. Sensitivity results reuse this sample and are not out-of-sample tests. The simulation includes modeled Delta fees, GST and slippage; funding remains excluded. These are Delta BTCUSD observations, not replication of CoinDCX BTCUSDT results. A longer, separately reserved test period, funding history and forward paper results remain necessary before promotion to automatic execution.
