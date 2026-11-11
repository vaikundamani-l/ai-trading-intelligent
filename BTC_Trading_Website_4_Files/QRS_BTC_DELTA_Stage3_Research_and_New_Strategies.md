# QRS-BTC-DELTA — Stage 3: Independent Synthesis, Corrected Mathematics, and New Testable Strategies

**Version:** S3-v1.0 | **Research cutoff:** 28 October 2026 | **Target:** Delta Exchange **India** `BTCUSD` perpetual | **Status:** RESEARCH PROTOTYPE — **NO CONFIRMED PROFIT**

> **Executive decision:** Do **not** deploy the original 2–30-second passive market-making scalper using the provided specification. Its fill selection, fee burden, and single-venue information deficit are unresolved. Prioritize a lower-frequency, executable, fee-aware system. This report supplies corrected equations and complete *proposed* modules, including a new SBR-5 strategy with a runnable OHLC research backtester. **None of the strategies has been demonstrated profitable on actual historical or paper fills in this work.**

## 0. Scope, evidence labels and provenance

- **SOURCE:** The supplied `QRS-BTC-DELTA_Stage1-2_Combined.md` contained Stage 1 through the beginning of Alpha-2 and the complete audit of that received portion. Missing equations and Alpha-3/4 were **not** supplied. This document is an **independent reconstruction**, not a restoration of lost text.
- **VERIFIED:** Directly supported by published exchange rules, paper conclusions, or mathematical identities.
- **MODEL:** An operational approximation whose parameters require calibration (e.g., execution simulator, arrival model).
- **HYPOTHESIS:** Proposed predictive rule with net-of-cost expected return not yet established.
- **DESIGN DEFAULT:** A declared starting parameter, **not** an optimized or empirically validated constant.

**Evidence of profitability available:** No actual user P&L, live fills, raw historical tick/L2 data, data file, or out-of-sample backtest was supplied. The environment could not access the historical-candles API to download BTC prices. Accordingly: historical profit = **unknown**; future profit = **uncertain**; strategy profitability = **not confirmed**. Six local *synthetic-data unit tests* validate limited software logic, **not financial performance**.

### Research inputs (independent verification)

1. Delta India contract page: `BTCUSD` perpetual, USD price quote, INR effective margin/settlement, lot 0.001 BTC, tick $0.50, maker 0.02%, taker 0.05%, eight-hour funding interval, mark method “Fair Price”. **Do not interchange Global and India contract terms.** https://www.delta.exchange/contracts
2. Delta India fees page: 18% GST applies to trading fees; fee calculation based on notional. https://www.delta.exchange/fees
3. Delta India Scalper Offer help: subject to enrollment/qualification, BTCUSD closing fee is waived if a position is closed in 30 minutes. A separate Diwali promotion effective 25 Sep 2026 offers conditional opening-fee *vouchers*, not a cash refund, subject to restrictions and a $100 monthly cap. May be modified or withdrawn. https://www.delta.exchange/support/solutions?articleId=80001172745
4. Funding schedule: examples for BTCUSD at **05:30, 13:30, 21:30 IST**; snapshot-based, and timing and intervals must be checked against the actual product. https://www.delta.exchange/support/solutions?articleId=80001183756
5. Delta India API: historical `GET /v2/history/candles` max 2,000 candles per response; `ob_l1`, `ob_l2`, `ob_updates`, `trades`, `mark_price`, `funding_rate` and authenticated execution endpoints. https://docs.delta.exchange/
6. **Urgent 2026 operations change:** Legacy `l1_orderbook`, `l2_orderbook`, and `l2_update` channels and old WS authentication are being removed **31 October 2026**; migrate to new endpoint and `ob_l1`, `ob_l2`, `ob_updates` before then. Also a USD index name change applies. https://community.delta.exchange/t/websocket-deprecations-31-october-2026/2525
7. Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*: OFI relates to **contemporaneous price impact** in equity books; it does **not** establish an executable predictive BTC alpha at Delta. https://doi.org/10.1093/jjfinec/nbt003
8. Wen et al. (2022), *Intraday return predictability in the cryptocurrency markets*: intraday momentum/reversal can vary with jumps, liquidity, regime; not validation of the precise proposed rules. https://www.sciencedirect.com/science/article/pii/S1062940822000833
9. Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*: adjustment for model selection and non-normality is needed. https://doi.org/10.3905/jpm.2014.40.5.094
10. Bailey et al. (2017), *The Probability of Backtest Overfitting*: test the search process, not only the winning configuration. https://escholarship.org/uc/item/4w1110bb

---

## 1. Feasibility first: an actual financial constraint

**Contract assumption:** Delta **India** BTCUSD. Returns below are expressed as percent or basis points **of entry notional**, not percent of margin. INR settlement conversion, account balances, portfolio margin, taxes beyond trading-fee GST and contract-specific exceptions require reconciliation to the actual statement.

### Fee table, verified rate inputs and derived values

One basis point (bp) = 0.01%. With maker 2 bp per leg, taker 5 bp per leg, and 18% GST on those fees:

| Entry / exit execution | Standard two-leg fee, bps of notional approximately | Conditional active BTCUSD Scalper Offer fee (opening leg only), bps |
|---|---:|---:|
| Maker / Maker | **4.72** | **2.36** |
| Maker / Taker | **8.26** | **2.36** |
| Taker / Taker | **11.80** | **5.90** |

The last column assumes the trader enrolled **before entry**, the position was fully or partially closed within the eligible period and the offer is still active; **never** assume it in the mandatory conservative baseline. Promotional fee vouchers are not withdrawable cash profit and must be accounted separately. Closing notional changes with price; bps here use an approximately unchanged notional for clarity.

### Correct net-trade accounting

For entry/exit execution prices `P_e` and `P_x`, direction `d=+1` long or `-1` short, and entry notional `N_e`:

```text
Gross-return-on-entry-notional = d * (P_x / P_e - 1)
Entry-fee-fraction             = fee_entry * (1 + GST)
Exit-fee-fraction              = fee_exit  * (1 + GST) * (P_x / P_e)
Net-return-on-entry-notional   = gross-return - entry-fee - exit-fee
                                - funding-paid-fraction - other-verified-costs
Net P&L in entry-notional units = N_e * net-return
```

This is the linear exposure approximation relevant to BTCUSD as described in current India specifications; verify effective contract multiplier/settlement mechanics against the actual fills before expressing INR profit. **Do not multiply the notional return by leverage again.** The *equity* return depends on notional/equity. Entry/exit slippage is included by simulating *worse executable prices*, **not again** as a cost line if already reflected in `P_e`, `P_x`.

**Spread/book-walk correction:** If the L2 execution price is `VWAP_buy`, aggressive-buy price cost relative to mid is `10,000*(VWAP_buy / P_mid - 1)` bp. This already includes half the spread; do not add half-spread twice. Do not graft a daily-volume square-root impact law onto small 5-second orders without calibration.

### Example: why the win rate must pay fees

Suppose a hypothetical completed trade has **40 bp stop**, **72 bp gross target** (1.8 R), and ~**13.8 bp combined taker fees and two 1 bp execution slippages**. Ignoring time stops and non-symmetric gaps, breakeven win rate is:

`p_be ~= (40 + 13.8) / (72 + 40) = 48.04%`.

That is only an **illustration**, not a measured BTC success rate. A stop that gaps can lose more, the time stop yields non-binary outcomes, and realized exits may differ from both levels. One cannot infer edge from the ratio alone.

**Gate G0 (reject early):** Compare historically *executable* favorable excursion at each holding horizon against the cost distribution. For a short-lived strategy, if realistic favorable excursion cannot clear fees + book-crossing + adverse fill selection with margin, reject it **before** optimizing ML models.

---

## 2. Corrections to the original mathematics and five Critical issues

### C1 — Trend on log prices

OLS `ln(P_t)` regressed on time can produce inflated t-statistics in a stochastic-trend price process. **Replace** with lagged returns, a robust trend persistence estimate, or a HAC drift estimate on returns, fitted in a trailing past-only window. A model trained on a price-level regression is not a trend detector merely because `R²` is high. For directional trading, require held-out predictive ability *after costs*.

### C2 — Basis and cointegration

For perp/spot where arbitrage tends to enforce near-unity exposure, initially define `B_t = ln(P_perp,t) - ln(P_spot,t)` with `beta=1`. If estimating an intercept/slope from data, an Engle–Granger residual-based unit-root test needs the appropriate Engle–Granger critical values rather than ordinary ADF critical values. Train parameters on past only. An observed stationary basis does not by itself mean a *perp-only* mean-reversion trade can earn money; a true basis strategy normally requires **two executable hedged legs**, both with fees and borrow/funding.

For AR(1) `B_t=c+phi B_(t-1)+eps`, OU half-life is `ln(2)*Δt/[-ln(phi)]` **only when `0<phi<1`**, using matching units. Reject unstable or rapidly changing estimated half-lives.

### C3 — HMM regime detectability

The prior feature vector (`ln volatility`, `abs(TFI)`, `ln spread`, jump ratio) contains **no signed directional persistence**. It cannot reliably identify a latent **trend** versus **mean reversion** label. Add past return autocorrelation/variance ratio, trend efficiency `|sum(r)|/(sum |r| + eps)`, and signed drift or cross-venue confirmations. Use a past-only refit. Since each feature has different support, choose appropriate emission family/transforms, rather than Gaussian everywhere. For Stage 3 implementation, **do not require an HMM**: explicit, inspectable regime gates are the baseline; test whether HMM adds incremental edge by ablation.

### C4 — Passive fills and venue leadership

Original Alpha-1 posts at the bid/ask and assumes an execution when it is actually filled. A favorable price move can cause the order to **remain unfilled**, while adverse moves hit the order. Measure **filled versus unfilled** conditional returns. L2 snapshots are not a FIFO queue simulator; order priority, marketable-order volume, cancellation acknowledgements, latency and partial fills all matter. Cross-venue data (read-only external BTC quotes/trades where lawfully available) can identify Delta prices lagging a more liquid venue, but synchronization and the cost of reacting are critical. A paper trade without an execution confirmation is not a fill.

### C5 — Multiple testing, corrected nuance

Maintain a ledger of **all** tried variants and search decisions. DSR's independent-trial maximum assumption requires an appropriate *effective* trial count; overlapping or serially dependent returns require robust standard errors. **Important correction to the previous audit:** Benjamini–Yekutieli FDR procedures are designed for arbitrary dependency *given valid p-values*; it is inaccurate to say BY itself assumes independent trials. However FDR control is **not** the probability that the single selected strategy is real. Use a pre-registered primary strategy and calendar-forward holdout, bootstrap confidence bounds, a multiple-model test such as Hansen SPA, and out-of-sample repeatability.

### Major/minor issue closure matrix

| Audit item | Stage 3 disposition |
|---|---|
| M1: Hawkes ≠ queue depletion | Define directly measured queue depletion; do not use Hawkes branching `eta` as proxy. Remove redundant lambda/TFI double-count. |
| M2: compression-trigger coupling | Require absolute breakout distance in ATR, spread multiples, and ticks, not Z-score alone. |
| M3: per-leg fee model | Separate maker/taker entry and exit; treat fees and return on *notional* basis, compare to hypothetical no-promo baseline. |
| M4: liquidation | Do **not** invent inverse/linear liquidation formulas; query actual product margin and position risk from API. Stress marked-price dislocation. |
| M5: tick volatility noise | Use mid-based, fixed-time regular-sample return windows; no unqualified “tick ATR”. |
| M6: epistemic labels | Adopt VERIFIED / MODEL / HYPOTHESIS / DESIGN DEFAULT instead of tagging assumptions `[DEF]`. |
| M7: parameter explosion | Fix structure; only a tiny predeclared grid, holdout not used for redesign. |
| M8: ruin risk approximation | Use block-bootstrap and stress scenario drawdowns; do not equate fixed barrier hitting with max drawdown. |
| M9: change-point model | BOCPD remains research-only until predictive likelihood, hazard units and detection delay are specified. |
| M10: spread double count | Correct book walk in bps; no uncalibrated square-root law in entry costs. |
| M11: Kelly wrong coefficients | Correct raw-moment expansion; **do not deploy Kelly** until sufficient net sample, tail model and uncertainty. |
| m1–m13 | Fix variance label/drift, weighted-mid naming, Gaussian jump filter, EMA decay units, VWAP weighting, contract notional, OFI scope, notation, funding snapshot, bootstrap blocks, net reward/risk, missing variable definitions, denominator/OU guards. |

**Correct moment-expanded Kelly first-order condition (model):** For simple unlevered trade outcome `R`, the 4th-order Taylor expansion of expected `ln(1+fR)` yields

`E[R] - f*E[R²] + f²*E[R³] - f³*E[R⁴] ~= 0`,

subject to `1+fR_i>0` for every considered outcome and sufficient accuracy of the truncated series. In central moments, terms involving `mean` must be retained unless a small-mean approximation is explicitly made. For practical risk controls, prefer fixed fractional **stop-risk budgeting** and finite loss limits over estimating unstable Kelly fractions.

**Corrections of original probability and RR equations:** With approximately constant *full round-trip cost* `C` applied to winners and losers, `E_net=p*W-(1-p)*L-C`; `p_be=(L+C)/(W+L)` and `RR_net=(W-C)/(L+C)`; where win- and loss-conditional realized costs differ, `p_be=(L+C_loss)/(W+L + C_loss-C_win)`.

---

## 3. Proposed complete strategy family (reconstructed, NOT supplied original)

These are orthogonal *economic hypotheses*, not proof of orthogonal trade outcomes. Begin with the low-complexity baseline below and add components **only if an ablation demonstrates benefit**.

### Alpha-1R — Reference-filtered microstructure impulse (research-only)

**Claim [HYPOTHESIS]:** Short-lived directional order-flow plus an *external* reference price impulse may predict Delta's next executable move **only in select liquid, high-move regimes**.

**Inputs:** Synchronized Delta `ob_updates` L2, `trades`, mark, external BTC perp L1/trade feed, timestamps at receive and exchange side. A stale external feed or wrong symbol blocks trade.

**Features (past-only):**

- `OFI_norm(t,h) = sum(e_n from t-h to t) / max(eps, time-averaged top-depth)`, clipped and standardized using historical trailing window.
- `TFI(t,h) = (aggressor_buy_notional-aggressor_sell_notional) / (total_aggressive_notional+eps)`.
- `RefImpulse(t,h) = log(P_ref,t/P_ref,t-h) - beta*log(P_delta,t/P_delta,t-h)`; beta fixed on trailing sample.
- `Depletion_bid/ask = (top_size_before - top_size_after - confirmed_executed_qty_adjustment)` per short horizon; distinguish true cancels versus trades; do **not** interpret snapshot imbalance as proof of actual buy aggression.
- Delta weighted mid `P_wmid=(q_bid*ask + q_ask*bid)/(q_bid+q_ask)`; its deviation from mid is mathematically related to top-level OBI, so **do not score both as independent predictors**.

**Long candidate:** Positive standardized Delta OFI, positive aggressor TFI, positive reference residual, low relative spread, no stale sequence/checksum, no price dislocation, no imminent funding, and *empirical conditional forward executable return exceeds worst-case cost*. Short is symmetric. No standing quote merely because price is predicted to rise.

**Execution:** Use a calibrated aggressive **limit IOC** with fixed maximum book-walk, or post-only entry *only* if a queue replay demonstrates positive filled-order net expectancy. Validated TTL, cancel-ack, partial fills required. A rejected IOC means **no fill**, not a win or a guaranteed missed profit. **Exit:** hard protective reduce-only stop plus immediate state-based invalidation; 30–120 sec time limit only if validated. **Failure:** fees dominate, external feed latency, price jumps, adverse selection, spoofed depth.

**Go/no-go:** Compare *actual fill-conditioned* net return distributions against an equal-frequency random-entry control and against no external filter. If G0 not passed, module is **OFF**.

### Alpha-2R — Compression-to-expansion breakout (research-only)

**Claim [HYPOTHESIS]:** Compression followed by a *large absolute* breakout and aggressive flow can continue for several 5m bars.

**Compression, computed before signal:** `VCR = RV(short=6 completed 5m bars) / median(RV(short=6) over prior 48 bars)`, with denominator >0; choose `VCR<0.65` solely as a design default.

**Long:** Preceding 6 bars satisfy compression; *completed* current 5m bar closes above highest prior 12-bar high by `max(0.30*ATR14_prior, 3*spread, 2*ticks)`; positive volume impulse >1.25× prior 24-bar mean; optional external price direction agrees; no funding window or jump/mark dislocation. Enter at **next bar's executable ask**. Short symmetric. Stop beyond breakout-candle opposite extreme subject to max risk, target at least 1.8R with timeout <=25min. Do not trade if breakeven reward is too small relative to realistic costs. **Failure:** tiny standardized Z-score breakout after compressed bands, news spikes/gaps, fade into prior range. **Test:** remove compression, volume and external confirmation one by one; breakouts often lose after friction.

### Alpha-3R — Perpetual/spot basis mean-reversion (hedged-only)

**Claim [HYPOTHESIS]:** Large perp-minus-spot basis deviations may revert faster than cumulative funding, basis risk, hedge execution, and fees.

`B_t = ln(P_perp_t) - ln(P_spot_t)` with beta=1 initially. Use historical reference spot index only as *observation*; the **tradable spot hedge has its own bid/ask and fees**. Estimate AR(1)/OU only on trailing time windows, enforce `0<phi<1`, and check predictive half-life stability. Signal absolute basis in *cost-adjusted* sigma units; trade **short perp + long executable spot** when premium rich, reverse when discount cheap **only if both legs legally/account-accessible**. Target total-basis convergence measured using simultaneous executable quotes and net financing. Track imbalance exposure, borrow, funding snapshots, FX, and hedge fill risk. **If spot leg unavailable, strategy OFF** (basis may instead serve as a no-trade risk filter). Do **not** call this arbitrage or risk-free profit.

### Alpha-4R — Jump/dislocation avoidance + delayed response

**Primary role: NO-TRADE and risk governor.** A large mark-mid or Delta-reference dislocation is not automatically a contrarian edge.

**Dislocation measure:** `D_t = abs(log(P_mid_delta / P_ref_adjusted))` adjusted for expected persistent intervenue basis. **Trigger:** `D_t > rolling_99th_percentile + shock_buffer`, confirmed source availability, or `abs(5m return) > 2.5*ATR14_prior / close` (both design defaults). No new trades; if already open, honor loss limit and reliable reducing orders. Keep a cooling window (e.g., 2 completed 5m candles after normalization) and test *resumption* under reference agreement. Alert on mark-mid, book checksum, API degraded status. A jump-reversal trading branch is a **separate HYPOTHESIS**; do not simultaneously optimize it and Alpha-5.

---

## 4. NEW ORIGINAL IMPLEMENTABLE BASELINE: Alpha-5 SBR-5 (Sweep → Reclaim → Fee Gate)

**Why this one?** It replaces an extremely latency-sensitive 2–30sec quote scalper with a completed-bar 5m *liquidity sweep/reclaim* setup in which the potential move is intended to be several multiples of the execution cost. It is simple enough for reproducible testing and easy to discard if it fails. It does **not** assert that “stop hunting” or institutional manipulation occurred; OHLC cannot establish trader motives.

### 4.1 Intuition (hypothesis, not an established profitable fact)

When the current 5m low temporarily breaks the lowest low of the **previous 24 closed 5m bars**, but the current bar closes back inside that old range on elevated volume, short-breakout buyers/sellers may be trapped and a reversal may follow. Its mirror applies to highs. This explanation is a *candidate mechanism* and can be false in momentum-heavy markets.

**Inputs:** Delta India BTCUSD **5-minute** completed OHLCV (time is UTC candle START). A production enhancement would require Delta bid/ask, mark, and optional independent reference trade data. The code only models the OHLC baseline; **it does not implement Alpha-1–4, external confirmation, real fills, queue priority, or live orders**.

### 4.2 Complete deterministic entry predicates

Let bar index `t` denote a *fully completed* 5m bar, with all normalizers calculated through `t-1`:

- `L24 = min(low[t-24 : t-1])`, `H24=max(high[t-24 : t-1])`.
- `ATR14_prior = mean(last 14 true ranges through t-1)`; simple moving ATR for test reproducibility (distinct from Wilder ATR in source).
- `V24_prior = mean(last 24 volumes through t-1)`.
- **Volume condition:** `volume[t] >= 1.25*V24_prior`.
- **Long signal:** `low[t] < L24 - max($0.50, 0.12*ATR14_prior)` AND `L24 + 0.10*ATR14_prior < close[t] < L24 + 1.20*ATR14_prior` AND `close[t]>open[t]`.
- **Short signal:** `high[t] > H24 + max($0.50, 0.12*ATR14_prior)` AND `H24 - 1.20*ATR14_prior < close[t] < H24 - 0.10*ATR14_prior` AND `close[t]<open[t]`.
- **Entry:** the next bar `t+1` **OPEN**, in the direction of signal, penalized by assumed *1 bp per-leg* aggressive slippage. In live trading, OHLC OPEN is an imperfect execution proxy; no guarantee of that fill.
- **Funding safety:** no entry if a (verified) BTCUSD funding snapshot lies within **2 min before entry through 2 min after maximum planned 25-minute hold**. Default published scheduled times = 05:30/13:30/21:30 IST. True schedule must be checked from current venue data.

**Stop and target in price:** For long, stop = `floor_to_tick(min(signal_low - 0.10*ATR14_prior, entry*(1-0.0015)))`; short stop = `ceil_to_tick(max(signal_high + 0.10*ATR14_prior, entry*(1+0.0015)))`. Reject if entry-to-stop distance >0.80% entry price. `R=abs(entry-stop)`; target = entry + `direction*1.80*R`, rounded conservatively away from entry. First of **stop / target / 5-bar time limit** ends the position. If both stop and TP are touched in a single OHLC bar, assume **stop occurs first**. For a stop gap, pay at the worse of bar open and stop, plus slippage. Time stop exits at close of the last bar plus slippage. **Do not optimize a TP ratio after seeing holdout outcomes.**

### 4.3 Sizing / kill switches (design safety envelope)

- **Assumed maximum risk:** 0.25% of current simulated equity per *fully stopped* trade including conservative taker/taker fees and slippage allowance (gaps can exceed it). Dollar-equivalent notional `min(equity*0.0025/(stop_distance_pct+fee_buffer+slip_buffer), equity*2)`, rounded **down** to an integer number of 0.001 BTC lots, or skipped if too small.
- **Max total modeled notional:** 2× equity; this is not a recommendation to use 2× leverage and **does not guarantee no liquidation**. Live risk must be validated against exchange liquidation and available margin.
- Stop taking new trades after a **1% daily equity loss** measured from modeled daily starting balance, **5% peak-to-trough closed-trade drawdown** (hard halt), or **four consecutive losing trades** (12-bar cooldown). Production must additionally enforce intrabar/equity drawdown and broker-side kill switches.
- No simultaneous positions; no increasing losing trades; no trading if data gaps.
- **Baseline ignores all promotions**, assumes both entry and exit are takers: `0.05%` each leg × `1.18` GST and assumed `1 bp` price slippage each side. The latter is merely a starting scenario, not observed Delta fill quality. Stress-test at 0,1,3,5+ bp per leg and with actual quote/trade reconstruction.

### 4.4 Performance metrics that MUST be reported

Completed trade log with signal timestamp, actual/assumed entry/exit, fees, volume, stop/target, signed gross/NET bps, equity-based profit, exit reason. Out-of-sample monthly net expectancy; net profit factor (PF); win rate; trade count; longest losing run; drawdown including open P&L in better simulator; fill probability; time-of-day distribution; volatility regime; slippage distribution; negative market days. **Note:** A positive win rate does not prove profitability. A 100% win rate over three trades is not robust evidence.

**Present state:** Executable *research code* is supplied and unit tested. **No verified performance result is supplied**. The system may lose money even when implemented without bugs.

### 4.5 SBR-X: optional independent confirmation (not coded, pre-register as separate experiment)

Improve SBR-5 only if it helps future independent data:

1. **Cross-venue disagreement:** After a Delta downside sweep and reclaim, a read-only reference BTC perp mid does not make a corresponding new *return-normalized* low at synchronized timestamps. Never compare raw USDT and USD price levels without a rolling basis correction.
2. **Aggressor absorption:** A strong reversal candle is accompanied by Delta **buy-side aggressive notional after the price low**, not just a bullish candle (requires time-aligned trade prints).
3. **Cost floor / skip:** Compare predicted *realizable* post-signal excursion with fees and depth, estimated only using past training data. If expected **lower confidence bound** on net return is <=0, refuse trade.
4. **Ablation:** Evaluate each extra gate one at a time. If it removes the best trades or data is stale, remove it; complexity is not edge.

**Unproven:** These four features can improve robustness, lower activity, or destroy the signal entirely. They are not present in supplied backtest code and cannot be described as tested.

---

## 5. Execution architecture and latest critical Delta operational facts

### Live systems must use the new WebSocket protocol

- **As of 28 Oct 2026:** old `l1_orderbook`, `l2_orderbook`, `l2_update` legacy channels scheduled for removal **31 Oct 2026**; replace with `ob_l1`, `ob_l2`, `ob_updates` on **`wss://public-socket.india.delta.exchange`**; migrate authentication to the documented current method. Do not adapt old messages by simply changing channel strings.
- `ob_l1` typically publishes every ~100 ms, `ob_l2` top 15 levels at ~500 ms, `ob_updates` supplies initial snapshot plus ~100 ms incremental updates. These are **documented nominal publish intervals, not a roundtrip execution-latency SLA**.
- On `ob_updates`, require monotonic adjacent `seq` and CRC32 `cs` book reconstruction (first 10 levels); on gap/mismatch unsubscribe/resubscribe and **block trading** until reconciled. Store both exchange event and local receive timestamps.
- Feed `trades` includes buyer role; verify interpretation before classifying aggressor side. Do not infer aggressor from raw signed sizes without checking schema.
- `mark_price` for liquidation risk is not the last traded price. Reject trading on stale mark, extreme mark/mid dislocation, or disconnect from private order/fill updates.
- Use a server-side **reduce-only** protective order where available; reconcile open positions and open orders on reconnect; do not blindly retry ambiguous order submission without idempotency/client IDs.
- Build a safe state machine `BOOTSTRAP -> SYNC -> FLAT -> ENTER_PENDING -> OPEN -> EXIT_PENDING -> FLAT`, with transitions to `HALTED` on data/API/risk incidents. Test the **kill switch and reconciliation** separately from alpha.
- API order limits, rate caps, post-only rejection behavior and contract details can change; read live product specifications from `/v2/products` before placing an order.
- Historical API `GET /v2/history/candles` returns **up to 2,000 candles per request**, so download date chunks and enforce no duplicate/missing bars. **OHLCV alone cannot validate queue-based Alpha-1 or mark-triggered stops.**

### Practical tricks that are real engineering, not profit guarantees

**No-trade is a valid decision.** (a) If pre-cost expected move <= cost, stay out; (b) if the **quote is older** than exchange-specific calibrated freshness cap, stay out; (c) never treat an order response as a fill: wait for execution confirmation; (d) close or block before a funding snapshot when strategy holds minutes; (e) estimate maker fill bias using both filled and unfilled signals; (f) separate mark and last for liquidation; (g) use actual spread in costs rather than chart candles; (h) test “promotions expired” as baseline; (i) never add random indicators without incremental value; (j) calendar holdout once, no cherry-picking; (k) distinguish a backtest with robust drawdown control from a strategy with a proven edge.

---

## 6. Evaluation protocol: what would justify a limited pilot?

Research stages must occur in this order; a beautiful equity curve from incomplete candles is **not** pass evidence.

| Gate | Test | Pre-registered example acceptance criterion (research design, NOT an observed result) |
|---|---|---|
| G0 | Economic viability | Trade horizon move potential demonstrably clears actual spread/fees under both standard and promo-expired schedules; reject if structurally impossible. |
| G1 | Data integrity | At least 180 days of clean 5m bars for SBR-5; 90–180 days full timestamped L2 + trades for Alpha-1. Reject time gaps, out-of-order/corrupt book; mark/funding coverage verified. |
| G2 | Research replay | Entry only from **next bar** or later; every exit pays slippage/fees; worst-case same-bar collision; compare to no-trade and randomized-entry baselines. |
| G3 | Holdout | Predeclare a small trial ledger, train on earlier calendar block, evaluate final untouched *later* block; no feature selection on final holdout; rolling/walk-forward confirm. |
| G4 | Statistical evidence | For primary candidate, 95% block-bootstrap **lower confidence bound of OOS average NET expectancy >0**; correct for tried variants; at least 200 OOS executed trades across multiple regimes if signal frequency allows. A small sample -> inconclusive, not “failed proof.” |
| G5 | Execution sensitivity | Remains positive under 2–5 bps extra *per-leg* costs, latency/outage scenarios, spread/mark stress, and **no conditional promotion**. |
| G6 | Live paper trial | At least 30–60 calendar days fixed-parameter paper execution, records of real signal-to-order timing, fill differences, fees and notional; rerun confidence interval on paper returns. |
| G7 | Minimal-size pilot | Only after explicit risk review. Begin minimum size with exchange-hosted protective exits, reconciliation, real-time daily/peak stops; objective is execution validation, not wealth generation. |

**Data partition example:** 2026-01-01 to 2026-06-30 research; 2026-07-01 to 2026-08-31 untouched validation; 2026-09-01 to 2026-10-27 final holdout. **Do not reuse these exact dates if they have already influenced strategy selection**; in that case, lock code now and collect a new forward period. Use chronological, purged 5m windows, no randomized shuffling of adjacent observations. Record all 2–6 initial parameter candidates in an immutable trial ledger and every later revision.

**Bootstrap detail:** Resample calendar-day blocks of realized *strategy* net returns to preserve event clusters; also examine event-level block lengths, position overlap and time-of-day seasonality. Compute a confidence interval on mean daily net portfolio returns and a separate trade-level interval; do not pretend trades are IID. Compare risk-budgeted returns, not only raw price bps.

**Claims threshold:** `net return > 0` on a single past sample is not “confirmed profitability.” Even passing all gates implies a historically supported, uncertain strategy; future P&L can turn negative. A significant strategy must also be economically meaningful after realistic operational effort and risk.

---

## 7. Delivered research code / data instructions

**Artifact:** `btc_sbr5_backtest.py` in this package (Python 3.10+, `pandas`, `numpy`, `requests`). It deliberately has **no private API key, order placement, leverage or auto-trading function**.

```bash
python3 -m pip install pandas numpy requests

# Fetch ~6 months of 5m data: public API, no API key; requires Internet.
python3 btc_sbr5_backtest.py fetch --start 2026-01-01 --end 2026-07-01 --out btc_5m.csv

# Research baseline, standard taker/taker fees with GST, 1bp slippage each side.
python3 btc_sbr5_backtest.py test --csv btc_5m.csv --out trades_base.csv --slip-bps 1

# Example cost stress tests (do not optimize on held-out data):
python3 btc_sbr5_backtest.py test --csv btc_5m.csv --out trades_3bp.csv --slip-bps 3
python3 btc_sbr5_backtest.py test --csv btc_5m.csv --out trades_5bp.csv --slip-bps 5

# Check six software tests on synthetic candles (these are NOT profit tests):
python3 -m unittest -v test_btc_sbr5.py
```

**CSV:** `time,open,high,low,close,volume`; `time` = Unix seconds marking the **start** of each UTC 5m candle, or parseable UTC ISO timestamp. The program refuses missing candles; solve gaps using a valid historical source rather than fabricating prices. Check exchange candle timestamp semantics and available history retention before using it.

**What the code gets right:** Previous-bar rolling features, next-bar entry, no overlap, conservative same-bar stops, funding block, GST fee per leg, price slippage, basic risk shutdown, test assertions, CSV reporting. **What it does not solve:** L2 order-book execution, bid/ask path, volatility of slippage, partial fills, actual order latency, mark-triggered liquidation/stop behavior, dynamic funding intervals, true INR P&L conversion, exchange insurance or risk-tier behavior, exact executed stop/TP ordering intrabar. OHLC backtest is only **G2 preliminary**.

**Known conservative/optimistic ambiguities:** Entering exactly at next bar open is an idealized assumption that can be optimistic. A “1bp slippage each side” stress assumption can be optimistic in jumps and pessimistic in quiet markets; measure actual execution. Using signal-bar wick as stop can select stops >risk cap and skip trades. Using a time exit on final available bar gives a completed modeled position rather than forcibly dropping it. Closed-trade drawdown misses intratrade peak-to-trough. These must be reconciled before live testing.

---

## 8. Deliverable verdict and next research experiment

**Prioritization:**

1. **SBR-5 on 5m bars** — lowest implementation burden, transparent and reproducible; first candidate for falsification, **not a guaranteed “best” strategy**.
2. **Alpha-2R** — secondary independent test if cost-based breakout feasibility holds; avoid selecting whichever looks best on one shared holdout.
3. **Alpha-1R** — highest data and latency requirement and likely to face substantial short-horizon friction; off until the queue and cross-venue test is feasible.
4. **Alpha-3R** — off without both executable legs and independently auditable financing.
5. **Alpha-4R** — deploy initially only as a protective no-trade/cooldown filter; whether it improves Alpha-5 is a hypothesis.

**State as of this document:**

| Deliverable | Actual status |
|---|---|
| Original file audited/read | Yes, for supplied content |
| Critical mathematical corrections | Design corrected |
| Alpha-1/2 missing equations filled | Proposed replacements, not originals |
| Alpha-3/4 strategy specifications | New proposed reconstructions |
| New strategy Alpha-5 | Fully specified, deterministic OHLC research version |
| Python research backtest | Built; six synthetic correctness checks passed |
| Historical BTC results | **NOT RUN** — API historical data inaccessible here |
| Cross-venue L2 proof | **NOT RUN** — data unavailable |
| Real paper/portfolio P&L | **NOT AVAILABLE** |
| **Confirmed profit** | **NO** — cannot honestly be asserted |

**The key original insight:** Avoid competing on milliseconds and indicators when the exchange fee floor makes the trade economically thin. Seek rare, auditable structural setups with larger potential excursions, quantify the opportunity cost of *not trading*, and refuse any strategy whose filled-order net edge does not survive realistic execution and untouched future data. This is a research direction, not a profit claim.

*Not personalized investment, tax or legal advice. Leveraged BTC futures can lose the entire posted margin rapidly; execution and liquidation risks can exceed stop-based simulations.*
