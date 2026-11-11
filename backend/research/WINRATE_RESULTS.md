# Search for an 80% winning-trade strategy

Tested 90 days of Delta India BTCUSD: 8,640 complete 15-minute candles. Twenty-four predefined long-only candidates combined four timeframes (15m, 45m, 4h, 8h), two entry families (Bollinger re-entry and 20-bar close breakout), and three target/stop pairs in ATR units (2/2, 0.75/2.5, 0.5/3). The first 60% of time was used for selection; the remaining 40% was reserved for the one training-selected candidate. Selection required at least 30 training trades and ranked mean net basis points rather than win rate.

The training-selected candidate was 45m Bollinger re-entry with target 2 ATR and stop 2 ATR. Training: 42 trades, 52.38% wins, profit factor 1.07. Held out: 38 trades, 15 wins (39.47%), profit factor 0.586, mean modeled net return -20.33 bps per trade. Doubling costs reduced held-out wins to 36.84% and profit factor to 0.407.

The highest training win rate among candidates with at least 30 trades was 69.89% (45m breakout, target 0.75 ATR, stop 2.5 ATR). Its training profit factor was only 0.562 and mean modeled net return was -12.17 bps per trade.

**No candidate was promoted to execution. No validated 80% strategy was established.** All candidate results and assumptions are disclosed in `winrate_search.json`; source candles are in `winrate_candles.json`. Run `PYTHONPATH=backend /home/shadow-khan/myenv/bin/python backend/research/search_winrate.py` to repeat on the latest window.

The modeled round-trip cost is 13.8 bps; funding is excluded. OHLC simulation cannot reconstruct order-book execution. Same-bar stop/target ambiguity is resolved at the stop. Entries occur at the following candle open. Positions are closed at the end of each evaluation period, and candles straddling the boundary are excluded. The rerun after verifying boundary handling uses the same observations and is a software consistency check, not independent validation.

Research sources: John Bollinger's official rules (https://www.bollingerbands.com/bollinger-band-rules) and Bailey et al., The Probability of Backtest Overfitting (https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). These motivate confirmation and selection discipline; they do not endorse these exact candidates or establish their profitability.
