# QRS-BTC-DELTA — Stage 1 + Stage 2 Combined Result (v2)

**Real-Time BTC Scalping Engine (Delta Exchange Architecture)**

| Stage | Content | Status |
|---|---|---|
| Stage 1 | Quantitative Research Specification (QRS-BTC-DELTA-S1-v1.0) | **Merged from two pastes in Part A.** Sections 0–1.5C are complete with equations. From the liquidation formula in 1.5D onward the text is incomplete: no equations for Section 2, and nothing after Alpha-2's entry rules |
| Stage 2 | Claude Audit & Critique | **Part B, complete for everything received.** Every equation in Sections 1.1–1.5C was checked line by line (log in B.3.4) |
| Stage 3 | GPT Synthesis & Verification | Pending; see B.7 for handoff notes |

**How to read this file.**
- Part A is the Stage 1 text. LaTeX uses `$...$` / `$$...$$`, so it renders in viewers with math support and otherwise shows as source. Markers like *[equation missing in both pastes]* are my additions.
- Part B is the Stage 2 audit. Section numbers such as "1.2E" or "2.1" in Part B refer to Part A. Part B's own sections are numbered B.1–B.7.

**Result in one paragraph.** The Stage 1 specification is unusually disciplined about separating definitions, empirical facts and hypotheses, and most of its formulas are correct. It is **still not ready for Stage 3 synthesis**. The audit found 5 Critical, 11 Major and 13 Minor issues (table in B.2). The Critical items: an inflated trend t-statistic (C1), an invalid cointegration test setup (C2), an HMM that cannot identify its own "trend" state (C3), a single-venue passive-fill scalper whose adverse selection is structural (C4), and multiple-testing controls that mis-count correlated trials (C5). Checking the equations also found wrong coefficients in the moment-adjusted Kelly condition (M11) and a slippage formula that double-counts the half-spread (M10).

**What changed since v1 of this file:** Part A now includes the equations for Sections 0–1.5C. In Part B, M1, M8, M9 and M10 were refined against the actual formulas; M11 and m11–m13 are new; B.3.4 (formula verification log) is new.

**Contents**
- Part A — Stage 1 specification (merged from both pastes)
- Part B — Stage 2 audit & critique: B.1 Scope and verdict · B.2 Findings at a glance · B.3 Detailed findings (incl. B.3.4 formula log) · B.4 Cross-cutting issues · B.5 Delta-specific claims to verify · B.6 Validation gates · B.7 Handoff notes

---

# Part A — Stage 1 Specification (merged from both pastes)

**Source map.**
- **Sections 0 through 1.5D (start):** from the *second* paste, with equations intact (LaTeX in `$...$` and `$$...$$`). That paste ends inside the liquidation formula in 1.5D.
- **Rest of 1.5D and all of Section 2:** from the *first* paste, where display equations were blank. These spots carry the marker *[equation missing in both pastes]*; the marker is my addition.
- The first paste ends mid-word in Alpha-2 ("Exit Predic"), so nothing after that point has been received.

## STAGE 1 QUANTITATIVE RESEARCH SPECIFICATION: REAL-TIME BTC SCALPING ENGINE (DELTA EXCHANGE ARCHITECTURE)

**Document ID:** `QRS-BTC-DELTA-S1-v1.0`
**Pipeline Stage:** Stage 1 (Foundational Specification & Mathematical Architecture) → Stage 2 (Claude Audit & Critique) → Stage 3 (GPT Synthesis & Verification)
**Target Instrument Class:** Bitcoin Perpetual Futures (`BTCUSD` / `BTCUSDT` Linear & Inverse Perpetuals, Delta Exchange)

---

### 0. Epistemic Taxonomy & Methodological Guardrails

To prevent conflation of mathematical identities with unproven trading alpha, every claim, model, and rule in this specification is classified under one of three epistemic tags:

* **[DEF — Established Definition]:** Exact mathematical, statistical, or accounting identities true by construction or axiomatic derivation.
* **[EMP — Empirical Stylized Fact / Mechanical Constraint]:** Documented market microstructure properties of limit order books (LOBs) and cryptocurrency perpetual derivatives (e.g., heavy-tailed return distributions, volatility clustering, maker/taker fee asymmetry, funding settlement mechanics). No numerical performance or profitability claims are fabricated.
* **[HYP — Proposed Hypothesis]:** Falsifiable predictive relationships or parameterization structures proposed for empirical testing on historical and paper-trading Delta Exchange data. Every `[HYP]` statement carries a strict null hypothesis ($H_0$: net expected return after all costs is less than or equal to zero) that must be rejected out-of-sample before deployment.

---

### 1. Mathematical Foundations & Formula Catalogue

#### 1.1 Time-Series Analysis, Clocks, and Volatility Estimators (Areas 1 & 4)

**[EMP]** High-frequency cryptocurrency order-book arrivals follow an irregular point process in physical time. Sampling strictly on fixed wall-clock intervals ($t_k = t_0 + k\Delta t$) induces heteroskedasticity and serial correlation artifacts during low-activity regimes and aliases information bursts during liquidation cascades.

##### A. Sampling Clocks & Log Returns [DEF]
Let $\tau_i$ denote the arrival timestamp of event $i$. The system maintains three synchronized clocks:
1. **Wall Clock ($\Delta t$):** Fixed millisecond/second intervals (used for funding accrual, heartbeat monitoring, and regular OHLCV aggregation).
2. **Volume Clock ($\Delta V$):** A new bar $k$ is emitted whenever cumulative traded notional since bar $k-1$ reaches threshold $V_{\text{thresh}}$:
   $$\sum_{j \in \text{Bar}_k} p_j q_j \ge V_{\text{thresh}}$$
3. **Tick/Imbalance Clock ($\Delta \Theta$):** A bar is emitted when cumulative signed tick volume crosses a dynamic expectation threshold.

For any reference price series $P_t$ (mid-price $P_{\text{mid},t}$ or micro-price $P_{\text{micro},t}$), the single-period log return over horizon $h$ is:
$$r_{t,h} = \ln\left(\frac{P_t}{P_{t-h}}\right)$$

##### B. Realized Volatility & Jump Separation [DEF]
Over a rolling window of $N$ high-frequency return increments $r_{t-i}$ ($i = 0, \dots, N-1$):

* **Realized Variance ($RV_t$) and Realized Volatility ($\sigma_{\text{RV},t}$):**
  $$RV_t(N) = \sum_{i=0}^{N-1} r_{t-i}^2, \quad \sigma_{\text{RV},t} = \sqrt{RV_t(N)}$$
* **Barndorff-Nielsen & Shephard Bipower Variation ($BV_t$):** Separates continuous diffusive variance from discontinuous jump variance:
  $$BV_t(N) = \frac{\pi}{2} \left(\frac{N}{N-1}\right) \sum_{i=0}^{N-2} |r_{t-i}| \cdot |r_{t-i-1}|$$
* **Jump Component ($J_t$):**
  $$J_t(N) = \max\left(0, RV_t(N) - BV_t(N)\right)$$
  **[HYP]** When the jump ratio $J_t(N) / RV_t(N)$ exceeds a calibrated critical threshold $\psi_{\text{jump}}$, continuous mean-reversion assumptions fail and passive limit orders face extreme adverse selection.

* **Range-Based Estimators (Over $M$ Volume or Time Bars with Open $O_i$, High $H_i$, Low $L_i$, Close $C_i$) [DEF]:**
  * **Parkinson Estimator:**
    $$\sigma_{\text{Park},t}^2 = \frac{1}{4 M \ln 2} \sum_{i=0}^{M-1} \left(\ln\frac{H_{t-i}}{L_{t-i}}\right)^2$$
  * **Garman-Klass-Yang-Zhang (GKYZ) Estimator (Accounts for Overnight/Inter-Bar Jumps and Drift):**
    $$\sigma_{\text{GKYZ},t}^2 = \frac{1}{M}\sum_{i=0}^{M-1}\left[\left(\ln\frac{O_{t-i}}{C_{t-i-1}}\right)^2 + \frac{1}{2}\left(\ln\frac{H_{t-i}}{L_{t-i}}\right)^2 - (2\ln 2 - 1)\left(\ln\frac{C_{t-i}}{O_{t-i}}\right)^2\right]$$

---

#### 1.2 Indicator Mathematics in Discrete and Irregular-Time Form (Area 4)

##### A. Irregular-Time Exponential Moving Average (EMA) [DEF]
For irregular tick arrivals at timestamps $t_i$ with $\Delta t_i = t_i - t_{i-1}$ and characteristic decay half-life $\tau_{1/2}$ (so mean lifetime $\tau = \tau_{1/2} / \ln 2$):
$$\alpha_i = 1 - \exp\left(-\frac{\Delta t_i}{\tau}\right), \quad \text{EMA}_i(X) = \alpha_i X_i + (1 - \alpha_i)\text{EMA}_{i-1}(X)$$
For uniform bar sampling ($\Delta t_i = \text{const}$), this reduces to standard discrete EMA with $\alpha = \frac{2}{N+1}$.

##### B. Wilder's RSI & Volatility-Normalized RSI [DEF]
Let $\Delta P_t = P_t - P_{t-1}$, $U_t = \max(\Delta P_t, 0)$, and $D_t = \max(-\Delta P_t, 0)$. Using Wilder smoothing factor $\alpha_W = 1/N$:
$$\bar{U}_t = \alpha_W U_t + (1 - \alpha_W)\bar{U}_{t-1}, \quad \bar{D}_t = \alpha_W D_t + (1 - \alpha_W)\bar{D}_{t-1}$$
$$\text{RSI}_t = 100 - \frac{100}{1 + (\bar{U}_t / \bar{D}_t)}$$

##### C. Average True Range (ATR) & Proportional ATR [DEF]
$$\text{TR}_t = \max\left(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|\right)$$
$$\text{ATR}_t(N) = \alpha_W \text{TR}_t + (1 - \alpha_W)\text{ATR}_{t-1}(N), \quad \text{ATR}_{\%,t} = \frac{\text{ATR}_t(N)}{C_t}$$

##### D. Exponentially Decayed VWAP & Volume-Weighted Bollinger Z-Score [DEF]
To avoid anchoring discontinuities at arbitrary UTC midnight boundaries in 24/7 crypto markets, define continuous decay-weighted VWAP with decay factor $\gamma \in (0,1)$:
$$V_t^{(\gamma)} = \gamma V_{t-1}^{(\gamma)} + v_t, \quad W_t^{(\gamma)} = \gamma W_{t-1}^{(\gamma)} + p_t v_t, \quad \text{VWAP}_t^{(\gamma)} = \frac{W_t^{(\gamma)}}{V_t^{(\gamma)}}$$
The decay-weighted volume variance $S_t^{2(\gamma)}$ and Volume-Weighted Bollinger Z-score $Z_{\text{VWAP},t}$ are:
$$S_t^{2(\gamma)} = \frac{\gamma V_{t-1}^{(\gamma)} S_{t-1}^{2(\gamma)} + v_t (p_t - \text{VWAP}_{t-1}^{(\gamma)})(p_t - \text{VWAP}_t^{(\gamma)})}{V_t^{(\gamma)}}$$
$$Z_{\text{VWAP},t} = \frac{P_t - \text{VWAP}_t^{(\gamma)}}{\sqrt{S_t^{2(\gamma)}}}$$
Standard Bollinger Bands at multiplier $k_{\text{BB}}$ are $\text{BB}_{\text{upper/lower},t} = \text{VWAP}_t^{(\gamma)} \pm k_{\text{BB}}\sqrt{S_t^{2(\gamma)}}$.

##### E. Rolling OLS/WLS Regression Slope & t-Statistic [DEF]
Over window $N$, fitting $\ln P_{t-N+1+j} = \beta_0 + \beta_1 j + \epsilon_j$ for $j \in \{0, \dots, N-1\}$ yields slope $\hat{\beta}_{1,t}$ and its standard error $\text{SE}(\hat{\beta}_{1,t})$:
$$\hat{\beta}_{1,t} = \frac{\sum_{j=0}^{N-1}(j - \bar{j})(y_j - \bar{y})}{\sum_{j=0}^{N-1}(j - \bar{j})^2}, \quad t_{\text{reg},t} = \frac{\hat{\beta}_{1,t}}{\text{SE}(\hat{\beta}_{1,t})}$$
where $y_j = \ln P_{t-N+1+j}$. Using $t_{\text{reg},t}$ normalizes raw slope by residual dispersion, distinguishing high-R-squared linear trends from noisy price spikes.

---

#### 1.3 Market Microstructure & Order Book Mathematics (Area 3)

Let the Level-2 (L2) Limit Order Book at time $t$ consist of $L$ price levels on the bid side $(p_{t,i}^b, q_{t,i}^b)_{i=1}^L$ and ask side $(p_{t,i}^a, q_{t,i}^a)_{i=1}^L$, where $p_{t,1}^b$ is the Best Bid and $p_{t,1}^a$ is the Best Ask.

##### A. Spread Metrics & Micro-Price [DEF]
* **Quoted Spread ($S_{q,t}$) & Relative Spread ($s_{q,t}$):**
  $$S_{q,t} = p_{t,1}^a - p_{t,1}^b, \quad P_{\text{mid},t} = \frac{p_{t,1}^a + p_{t,1}^b}{2}, \quad s_{q,t} = \frac{S_{q,t}}{P_{\text{mid},t}}$$
* **Effective Spread ($S_{\text{eff},t}$) for a Trade at Price $p_t^{\text{tr}}$ with Direction $d_t \in \{+1, -1\}$:**
  $$S_{\text{eff},t} = 2 d_t \left(p_t^{\text{tr}} - P_{\text{mid},t}\right)$$
* **Realized Spread ($S_{\text{real},t,\Delta}$) over Horizon $\Delta$ (Measures Market-Maker Gross Capture Net of Adverse Selection):**
  $$S_{\text{real},t,\Delta} = 2 d_t \left(p_t^{\text{tr}} - P_{\text{mid},t+\Delta}\right)$$
* **Volume-Weighted Micro-Price ($P_{\text{micro},t}$):**
  $$I_{1,t} = \frac{q_{t,1}^b}{q_{t,1}^b + q_{t,1}^a}, \quad P_{\text{micro},t} = I_{1,t} p_{t,1}^a + (1 - I_{1,t}) p_{t,1}^b$$

##### B. Multi-Level Order-Book Imbalance ($OBI_{L,t}$) [DEF]
Weighting deeper levels with exponential decay $\lambda_d \gt 0$:
$$Q_t^b(L) = \sum_{i=1}^L \exp(-\lambda_d (i-1)) q_{t,i}^b, \quad Q_t^a(L) = \sum_{i=1}^L \exp(-\lambda_d (i-1)) q_{t,i}^a$$
$$OBI_{L,t} = \frac{Q_t^b(L) - Q_t^a(L)}{Q_t^b(L) + Q_t^a(L)} \in [-1, +1]$$

##### C. Order Flow Imbalance ($OFI_t$) & Trade-Flow Imbalance ($TFI_t$) [DEF]
Cont, Kukanov, and Stoikov (2014) Order Flow Imbalance over interval $[t-1, t]$ captures net liquidity addition/cancellation at the best quotes:
$$e_n = \mathbb{I}_{\{p_{n,1}^b \ge p_{n-1,1}^b\}} q_{n,1}^b - \mathbb{I}_{\{p_{n,1}^b \le p_{n-1,1}^b\}} q_{n-1,1}^b - \mathbb{I}_{\{p_{n,1}^a \le p_{n-1,1}^a\}} q_{n,1}^a + \mathbb{I}_{\{p_{n,1}^a \ge p_{n-1,1}^a\}} q_{n-1,1}^a$$
$$OFI_t(\tau) = \sum_{n \in [t-\tau, t]} e_n$$

**Trade-Flow Imbalance ($TFI_t$)** aggregates aggressive taker executions over decay horizon $\tau_{\text{flow}}$:
$$V_t^{\text{buy}} = \sum_{k} v_k \mathbb{I}_{\{d_k = +1\}} \exp\left(-\frac{t - t_k}{\tau_{\text{flow}}}\right), \quad V_t^{\text{sell}} = \sum_{k} v_k \mathbb{I}_{\{d_k = -1\}} \exp\left(-\frac{t - t_k}{\tau_{\text{flow}}}\right)$$
$$TFI_t = \frac{V_t^{\text{buy}} - V_t^{\text{sell}}}{V_t^{\text{buy}} + V_t^{\text{sell}} + \epsilon}$$

##### D. Hawkes Process Self-Exciting Trade Arrival Intensity [DEF / HYP]
**[DEF]** Let $\lambda_t^+$ and $\lambda_t^-$ denote the conditional arrival intensities of aggressive buy and sell market orders:
$$\lambda_t^{\pm} = \mu_0^{\pm} + \sum_{t_k^{\pm} \lt t} \alpha_H \exp\left(-\beta_H (t - t_k^{\pm})\right)$$
where $\mu_0^{\pm}$ is baseline arrival intensity, $\alpha_H$ is excitation jump size, and $\beta_H$ is exponential decay rate (stationarity requires branching ratio $\eta = \alpha_H / \beta_H \lt 1$).

##### E. Market Impact, Slippage, and Latency Decay [DEF / EMP]
* **Kyle's Lambda ($\lambda_K$):** Estimated via rolling regression $\Delta P_{\text{mid},t} = \lambda_{K,t} \cdot OFI_t + \varepsilon_t$. Measures price sensitivity per unit of net order flow (illiquidity).
* **Execution Slippage & Square-Root Impact Model [EMP]:** For an aggressive order of notional size $Q$, expected immediate book walk plus temporary impact is modeled as:
  $$\mathbb{E}[\text{Slippage}_{\text{bps}}(Q)] = \frac{s_{q,t}}{2} + \kappa \sigma_{\text{RV},t} \sqrt{\frac{Q}{V_{\text{ADV},t}}} + \text{BookWalk}(Q, \text{LOB}_t)$$
  where $\text{BookWalk}(Q, \text{LOB}_t)$ is the exact volume-weighted average execution price across currently visible L2 levels minus $P_{\text{mid},t}$.
* **Latency Decay of Short-Horizon Alpha [HYP]:** Given round-trip network + exchange processing latency $\Delta t_{\text{lat}}$, predicted horizon return $\hat{r}_{t,h}$ decays according to:
  $$\hat{r}_{\text{exec},t,h}(\Delta t_{\text{lat}}) = \hat{r}_{t,h} \exp\left(-\gamma_{\text{lat}} \Delta t_{\text{lat}}\right)$$

---

#### 1.4 State-Space Models, Cointegration, Regime Filtering & Statistical Inference (Areas 2, 5, 6)

##### A. Linear Gaussian State-Space (Kalman Filter) for Latent Price & Velocity [DEF]
Let the latent state vector at discrete step $t$ be $\mathbf{x}_t = [x_{1,t}, x_{2,t}]^\top$, representing true uncorrupted log-price ($x_{1,t}$) and local drift velocity ($x_{2,t}$):
$$\mathbf{x}_t = \mathbf{F}_t \mathbf{x}_{t-1} + \mathbf{w}_t, \quad \mathbf{w}_t \sim \mathcal{N}(\mathbf{0}, \mathbf{Q}_t)$$
$$z_t = \mathbf{H} \mathbf{x}_t + v_t, \quad v_t \sim \mathcal{N}(0, R_t)$$
where $z_t = \ln P_{\text{micro},t}$ is the noisy microstructure observation, and for time step $\Delta t_t$:
$$\mathbf{F}_t = \begin{bmatrix} 1 & \Delta t_t \\ 0 & 1 \end{bmatrix}, \quad \mathbf{H} = \begin{bmatrix} 1 & 0 \end{bmatrix}, \quad \mathbf{Q}_t = q_c \begin{bmatrix} \frac{\Delta t_t^3}{3} & \frac{\Delta t_t^2}{2} \\ \frac{\Delta t_t^2}{2} & \Delta t_t \end{bmatrix}$$
Observation noise variance $R_t$ is dynamically scaled by the squared relative bid-ask spread: $R_t = r_0 + r_1 s_{q,t}^2$.
* **Prediction Step:**
  $$\hat{\mathbf{x}}_{t|t-1} = \mathbf{F}_t \hat{\mathbf{x}}_{t-1|t-1}, \quad \mathbf{P}_{t|t-1} = \mathbf{F}_t \mathbf{P}_{t-1|t-1} \mathbf{F}_t^\top + \mathbf{Q}_t$$
* **Innovation & Update Step:**
  $$y_t = z_t - \mathbf{H}\hat{\mathbf{x}}_{t|t-1}, \quad S_t = \mathbf{H}\mathbf{P}_{t|t-1}\mathbf{H}^\top + R_t, \quad \mathbf{K}_t = \mathbf{P}_{t|t-1}\mathbf{H}^\top S_t^{-1}$$
  $$\hat{\mathbf{x}}_{t|t} = \hat{\mathbf{x}}_{t|t-1} + \mathbf{K}_t y_t, \quad \mathbf{P}_{t|t} = (\mathbf{I} - \mathbf{K}_t \mathbf{H})\mathbf{P}_{t|t-1}$$
The standardized Kalman innovation is $\tilde{y}_t = y_t / \sqrt{S_t}$.

##### B. Cointegration & Ornstein-Uhlenbeck (OU) Basis Dynamics [DEF]
Between Delta Exchange Perpetual log-price $p_t^{\text{perp}}$ and Reference Spot Index log-price $p_t^{\text{spot}}$ (or across two correlated perpetual contracts), define the dynamic basis spread $B_t = p_t^{\text{perp}} - \hat{\beta}_t p_t^{\text{spot}} - \hat{\alpha}_t$. When $B_t$ is stationary ($I(0)$, verified via Augmented Dickey-Fuller test statistic $\tau_{\text{ADF}} \lt \tau_{\text{crit}}$), model $B_t$ as an Ornstein-Uhlenbeck process:
$$dB_t = \theta_{\text{OU}}(\mu_{\text{OU}} - B_t)dt + \sigma_{\text{OU}} dW_t$$
Discrete exact AR(1) representation $B_t = c + \phi B_{t-1} + \varepsilon_t$ yields mean-reversion speed and half-life:
$$\theta_{\text{OU}} = -\frac{\ln \phi}{\Delta t}, \quad t_{1/2}^{\text{OU}} = \frac{\ln 2}{\theta_{\text{OU}}}, \quad \sigma_{\text{eq}} = \frac{\sigma_\varepsilon}{\sqrt{1 - \phi^2}}$$

##### C. Regime Detection: Hidden Markov Model (HMM) & Bayesian Online Change-Point Detection (BOCPD) [DEF]
1. **3-State Gaussian HMM:** Latent regime $S_t \in \{1 \text{ (Quiet/Mean-Reverting)}, 2 \text{ (Directional Trend)}, 3 \text{ (Volatile/Dislocated)}\}$ governs feature vector $\mathbf{o}_t = [\ln \sigma_{\text{RV},t}, |TFI_t|, \ln s_{q,t}, J_t/RV_t]^\top$ with transition matrix $\mathbf{A}_{ij} = \mathbb{P}(S_t = j \mid S_{t-1} = i)$. Forward filtering updates state probabilities $\xi_{t}(j) = \mathbb{P}(S_t = j \mid \mathbf{o}_{1:t})$ in real time without look-ahead:
   $$\xi_t(j) = \frac{b_j(\mathbf{o}_t) \sum_{i=1}^3 \xi_{t-1}(i) \mathbf{A}_{ij}}{\sum_{k=1}^3 b_k(\mathbf{o}_t) \sum_{i=1}^3 \xi_{t-1}(i) \mathbf{A}_{ik}}$$
2. **Bayesian Online Change-Point Detection (BOCPD — Adams & MacKay 2007):** Tracks the run length $r_t$ (time since the last structural change-point in return variance/mean) recursively via hazard rate $H(\tau) = 1/\lambda_{\text{cp}}$:
   $$\mathbb{P}(r_t = r_{t-1}+1, \mathbf{x}_{1:t}) = \mathbb{P}(r_{t-1}, \mathbf{x}_{1:t-1}) \cdot \mathbb{P}(x_t \mid r_{t-1}, \mathbf{x}_t^{(r)}) (1 - H(r_{t-1}))$$
   $$\mathbb{P}(r_t = 0, \mathbf{x}_{1:t}) = \sum_{r_{t-1}} \mathbb{P}(r_{t-1}, \mathbf{x}_{1:t-1}) \cdot \mathbb{P}(x_t \mid \emptyset) H(r_{t-1})$$
   When $\mathbb{P}(r_t \le k_{\text{short}} \mid \mathbf{x}_{1:t}) \gt \theta_{\text{bocpd}}$, a structural regime break is flagged.

##### D. Statistical Hypothesis Testing, Bootstrap, and Multiple-Testing Corrections [DEF]
* **Politis-Romano Stationary Bootstrap:** Resamples time series in blocks of random geometric length $L_b \sim \text{Geom}(p_b)$ to preserve autocorrelation and volatility clustering when constructing $1-\alpha$ confidence intervals for Sharpe ratio, net expectancy, and maximum drawdown.
* **Benjamini-Hochberg-Yekutieli (BHY) False Discovery Rate (FDR):** For $M$ tested strategy/parameter variants with sorted p-values $p_{(1)} \le p_{(2)} \le \dots \le p_{(M)}$ under arbitrary dependence, reject hypotheses up to $k^*$:
  $$k^* = \max\left\{k : p_{(k)} \le \frac{k}{M \cdot c(M)} q_{\text{FDR}}\right\}, \quad c(M) = \sum_{i=1}^M \frac{1}{i}$$
* **Deflated Sharpe Ratio (DSR — Bailey & López de Prado 2014):** Corrects the observed Sharpe Ratio $\widehat{SR}$ for non-normality (skewness $\hat{\gamma}_3$, kurtosis $\hat{\gamma}_4$), sample length $T$, and the expected maximum Sharpe Ratio $SR_0$ across $M$ independent trials:
  $$SR_0 = \sqrt{\mathbb{V}[\{\widehat{SR}_m\}_{m=1}^M]} \left((1 - \gamma_{\text{EM}})\Phi^{-1}\left(1 - \frac{1}{M}\right) + \gamma_{\text{EM}}\Phi^{-1}\left(1 - \frac{1}{M e}\right)\right)$$
  $$\text{DSR} = \Phi\left(\frac{(\widehat{SR} - SR_0)\sqrt{T - 1}}{\sqrt{1 - \hat{\gamma}_3 \widehat{SR} + \frac{\hat{\gamma}_4 - 1}{4}\widehat{SR}^2}}\right)$$
  where $\gamma_{\text{EM}} \approx 0.5772$ is the Euler-Mascheroni constant and $\Phi(\cdot)$ is the standard normal CDF.

---

#### 1.5 Trade Expectancy, Position Sizing, Tail Risk & Delta Exchange Perpetual Mechanics (Area 7)

##### A. Net Trade Expectancy With Maker/Taker, Slippage, and Funding [DEF]
Let $p_w$ be the probability of a winning trade, $R_w$ the gross average fractional gain on winners, $R_l$ the gross average fractional loss on losers ($R_l \gt 0$), $\omega_M \in [0,1]$ the proportion of volume executed as Maker (fee rate $f_M$), $(1-\omega_M)$ executed as Taker (fee rate $f_T$), $s_{\text{slip}}$ the round-trip fractional slippage, and $c_{\text{fund}}$ the net fractional funding paid/received over the holding period:
$$C_{\text{RT}} = 2\left(\omega_M f_M + (1 - \omega_M) f_T\right) + s_{\text{slip}} + c_{\text{fund}}$$
$$E_{\text{net}} = p_w R_w - (1 - p_w) R_l - C_{\text{RT}}$$
**Reward-to-Risk Ratio (Net):**
$$\text{RR}_{\text{net}} = \frac{R_w - C_{\text{RT}}/2}{R_l + C_{\text{RT}}/2}$$
**Minimum Breakeven Win Rate ($p_{\text{BE}}$):**
$$p_{\text{BE}} = \frac{R_l + C_{\text{RT}}}{R_w + R_l}$$

##### B. Higher-Moment Fractional Kelly Position Sizing [DEF]
Standard Gaussian Kelly $f^* = \mu / \sigma^2$ overestimates optimal leverage under heavy left-tail risk. Expanding expected logarithmic utility up to the fourth central moment for trade return $R$ with mean $\mu_R = E_{\text{net}}$, variance $\sigma_R^2$, skewness $\gamma_1$, and excess kurtosis $\gamma_2$ yields the moment-adjusted Kelly fraction $f_{\text{HM}}^*$ solved numerically from:
$$\mu_R - f \sigma_R^2 + \frac{f^2}{2} \gamma_1 \sigma_R^3 - \frac{f^3}{6} (\gamma_2 + 3) \sigma_R^4 = 0$$
The deployed position fraction applies a conservative shrinkage factor $\kappa_{\text{Kelly}} \in [0.10, 0.30]$ and caps leverage against exchange liquidation distance:
$$f_{\text{deploy}} = \min\left(\kappa_{\text{Kelly}} f_{\text{HM}}^*, \, L_{\text{max}}, \, \frac{\text{Risk}_{\text{max,trade}}}{\text{StopDistance}_{\%} + C_{\text{RT}}}\right)$$

##### C. Tail Risk: Cornish-Fisher VaR, Expected Shortfall ($\text{CVaR}_\alpha$), and Risk of Ruin [DEF]
* **Historical / Parametric Expected Shortfall at Confidence Level $1-\alpha$:**
  $$\text{CVaR}_\alpha(R) = -\mathbb{E}\left[R \mid R \le -\text{VaR}_\alpha(R)\right]$$
* **Risk of Ruin ($P_{\text{ruin}}$) for Drawdown Barrier $B_{\text{dd}}$ (Fraction of Capital):**
  Approximating cumulative equity log-increments with drift $\mu_e \gt 0$ and variance $\sigma_e^2$:
  $$P_{\text{ruin}}(B_{\text{dd}}) \approx \exp\left(-\frac{2 \mu_e |\ln(1 - B_{\text{dd}})|}{\sigma_e^2}\right)$$

##### D. Delta Exchange Perpetual Contract & Liquidation Constraints [EMP / DEF]
1. **Mark Price vs. Last Traded Price (LTP):** Delta Exchange triggers liquidations based on **Mark Price** ($P_{\text{mark},t}$), which is derived from a composite spot index plus an exponentially smoothed funding basis, whereas limit/market orders execute against the Delta Exchange order book ($P_{\text{mid},t}$).
2. **Liquidation Boundary Constraint:** For a position of direction $d \in \{+1, -1\}$ at entry price $P_{\text{entry}}$ with effective leverage $L_{\text{eff}}$ and Maintenance Margin Ratio $\text{MMR}$:
   Equation as received (truncated; shown as plain text so it does not break math rendering):

   ```
   $$P_{\text{liq}}^{\text{approx}} \approx P_{\text{entry}} \left(1 - d \left(\
   ```

> **[Second paste ends here, inside the liquidation formula. In the first paste, both liquidation equations were blank.]**

*[equation(s) missing in both pastes: remainder of the liquidation boundary formula, and the second liquidation equation]*

   **Hard Safety Constraint:** Every trade's hard stop-loss distance $\Delta P_{\text{stop}}$ plus maximum observed Mark-to-Mid basis dislocation $\Delta P_{\text{basis,max}}$ must satisfy:

   *[equation missing in both pastes]*
3. **Funding Fee Gate:** At funding timestamp $t_{\text{fund}}$, a position of notional $N_{\text{pos}}$ and direction $d$ pays $F_{\text{cost}} = d \cdot N_{\text{pos}} \cdot r_{\text{fund}}$. If $d \cdot r_{\text{fund}} \gt 0$ and time-to-funding $t_{\text{fund}} - t \le \Delta t_{\text{fund\_gate}}$, expected alpha must exceed $E_{\text{net}} + |r_{\text{fund}}|$ or the position is flattened/blocked.

---

### 2. Comprehensive Strategy Specifications (Areas 2 & 8)

*(From the first paste: equations missing.)*

To ensure structural diversification across market regimes, the engine specifies four orthogonal strategy modules. No strategy is assumed profitable prior to completing the Validation Matrix (Section 7).

#### 2.1 Strategy Alpha-1: Microstructure Order-Book & Trade-Flow Imbalance Scalper

* **Archetype:** Ultra-short-horizon order-flow momentum & micro-price dislocation capture.
* **Target Regime:** HMM State 1 (Normal/Liquid) or State 2 (Moderate Trend), with tight relative spread.

**1. Mathematical Equations & Structural Assumptions**

* [DEF] Normalized Micro-Price Deviation:

  *[equation missing in both pastes]*
* [DEF] Composite Microstructure Pressure Score ($MPS_t$):

  *[two equations missing in both pastes]*

  where $w_1 + w_2 + w_3 + w_4 = 1$ and $Z(OFI_t(\tau_1))$ is the rolling Z-score of Order Flow Imbalance clipped to $[-3, +3]$.
* [HYP] Hypothesis H1: When $MPS_t$ exceeds an extreme threshold $\theta_{\text{entry}}$ while top-of-book queue depletion accelerates (Hawkes branching ratio $\eta_t \gt \eta_{\text{min}}$) and spread is compressed ($s_{q,t} \le s_{\text{max}}$), the mid-price $P_{\text{mid},t+h}$ exhibits positive drift over $h \in [2\text{s}, 30\text{s}]$ sufficient to overcome maker-entry / taker-exit costs.

**2. Required Inputs & Data Frequency**

* Delta Exchange WebSocket L2 Order Book updates (top 10 levels, event-driven, sub-100ms resolution).
* Real-time Trade print stream (trades channel: price, size, buyer/seller maker flag, timestamp).
* Mark Price & Spot Index stream (1s resolution).

**3. Exact Entry & Exit Conditions**

* Entry Predicate:

  *[equation missing in both pastes]*
* Execution Mechanism: Post-Only Maker Limit Order placed at Best Bid ($p_{t,1}^b$) for Long or Best Ask ($p_{t,1}^a$) for Short, with a maximum resting TTL of $\tau_{\text{fill}} \in [500\text{ms}, 3000\text{ms}]$. If unfilled after $\tau_{\text{fill}}$, cancel immediately.
* Exit Predicates (First Triggered):
  * Signal Reversal Exit: $d \cdot MPS_t \le \theta_{\text{exit}}$ (attempt passive Maker exit at touch for $\tau_{\text{exit\_passive}}$, then cross spread via IOC/Market).
  * Take-Profit: $d \cdot (P_t - P_{\text{entry}}) \ge k_{\text{TP}} \cdot \text{ATR}_{t}^{\text{tick}}$.
  * Hard Stop-Loss: $d \cdot (P_t - P_{\text{entry}}) \le -k_{\text{SL}} \cdot \text{ATR}_{t}^{\text{tick}}$ (immediate Market/IOC order).
  * Time Stop: Holding duration $t - t_{\text{entry}} \ge \tau_{\text{max\_hold}}$ without reaching $0.25 \times \text{TP}$.

**4. Long, Short, and No-Trade Rules**

* Long Rule ($d = +1$): $MPS_t \ge +\theta_{\text{entry}}$ and $\lambda_t^+ \gt \lambda_t^-$.
* Short Rule ($d = -1$): $MPS_t \le -\theta_{\text{entry}}$ and $\lambda_t^- \gt \lambda_t^+$.
* No-Trade Rules:
  * Relative spread $s_{q,t} \gt s_{\text{max}}$ (book is too wide).
  * Top-5 book depth on either side is below $Q_{\text{min}}$ (thin book / spoofing vulnerability).
  * BOCPD change-point probability $\mathbb{P}(r_t \le 5) \gt 0.50$.

**5. Parameter Definitions & Test Ranges**

| Parameter | Symbol | Description | Test Range | Step / Scale |
|---|---|---|---|---|
| Weight Vector | $\mathbf{w}$ | Weights for $(\delta_{\text{micro}}, OBI_5, Z(OFI), TFI)$ | Simplex grid $[0.1, 0.5]$ | Dirichlet / Constrained Grid |
| Entry Threshold | $\theta_{\text{entry}}$ | Minimum $\vert{}MPS_t\vert{}$ to trigger entry | $[0.55, 0.85]$ | 0.05 |
| Exit Threshold | $\theta_{\text{exit}}$ | Signal decay/reversal threshold | $[-0.20, +0.15]$ | 0.05 |
| Flow Decay Horizon | $\tau_1, \tau_2$ | Exponential decay window for OFI / TFI | $[1.0\text{s}, 15.0\text{s}]$ | Logarithmic |
| Max Holding Time | $\tau_{\text{max\_hold}}$ | Time-stop ceiling | $[15\text{s}, 120\text{s}]$ | $15\text{s}$ |
| TP / SL Multipliers | $k_{\text{TP}}, k_{\text{SL}}$ | Volatility-scaled target and stop | $k_{\text{TP}} \in [1.5, 4.0]$, $k_{\text{SL}} \in [1.0, 2.5]$ | 0.25 |

**6. Expected Costs & Execution Assumptions**

* Assumes Post-Only Maker entry ($\omega_{M,\text{entry}} = 1.0$) and a conservative 30% Maker / 70% Taker exit blend ($\omega_{M,\text{exit}} = 0.30$).
* Queue position is modeled conservatively at the back of the existing price level queue at timestamp $t + \Delta t_{\text{lat}}$.

**7. Known Failure Modes**

* Adverse Selection ("Toxic Fill"): Passive buy order at $p_{t,1}^b$ fills only when a large informed seller sweeps the entire bid level, causing immediate negative mark-to-market excursion.
* L2 Spoofing: Large resting orders placed at levels 2–5 distort $OBI_{5,t}$ and are canceled within milliseconds before execution reaches them.

**8. Required Historical Data**

* Minimum 90–180 continuous days of tick-by-tick L2 incremental order book updates + full snapshots + trade prints from Delta Exchange `BTCUSD` / `BTCUSDT`.

**9. Viability Tests Before Deployment**

* Adverse selection conditioned return test: Compare $\mathbb{E}[r_{t,h} \mid \text{Signal}, \text{Passive Fill}]$ against $\mathbb{E}[r_{t,h} \mid \text{Signal}, \text{Unfilled}]$. If filled trades systematically underperform unfiltered signal returns by more than net edge, reject [HYP H1].
* Latency sensitivity sweep: Inject $\Delta t_{\text{lat}} \in \{25\text{ms}, 50\text{ms}, 100\text{ms}, 250\text{ms}\}$ in event replay.

#### 2.2 Strategy Alpha-2: Volatility Compression Breakout & Hawkes Intensity Engine

* **Archetype:** Volatility expansion / momentum breakout on volume-clock bars.
* **Target Regime:** Transition from HMM State 1 (Low Volatility Compression) to State 2 (Directional Expansion).

**1. Mathematical Equations & Structural Assumptions**

* [DEF] Volatility Compression Ratio ($VCR_t$):

  *[equation missing in both pastes]*
* [DEF] Directional Hawkes Intensity Imbalance ($HII_t$):

  *[equation missing in both pastes]*
* [HYP] Hypothesis H2: When $VCR_t \lt \theta_{\text{comp}}$ (prolonged volatility compression), a price breakout beyond the Volume-Weighted Bollinger Band ($\vert{}Z_{\text{VWAP},t}\vert{} \ge k_{\text{BB}}$) accompanied by a self-exciting surge in directional trade arrival intensity ($\vert{}HII_t\vert{} \ge \theta_{\text{hawkes}}$ and total intensity $\lambda_t^+ + \lambda_t^- \ge \Lambda_{\text{min}}$) leads to positive momentum continuation over 1 to 15 minutes.

**2. Required Inputs & Data Frequency**

* Volume-clock bars ($V_{\text{thresh}}$ calibrated to average 15–60 seconds per bar), L1/L2 top-5 book, and tick trade stream for Hawkes recursive intensity tracking.

**3. Exact Entry & Exit Conditions**

* Compression Pre-Condition: Over the preceding $K$ bars, $\min_{j \in [0,K]} VCR_{t-j} \le \theta_{\text{comp}}$.
* Long Entry Predicate:

  *[equation missing in both pastes]*
* Short Entry Predicate:

  *[equation missing in both pastes]*
* Execution Mechanism: Aggressive Limit / IOC order capped at $p_{t,1}^a + \Delta p_{\text{slip\_cap}}$ (Long) or $p_{t,1}^b - \Delta p_{\text{slip\_cap}}$ (Short).
* Exit Predic

> **[Stage 1 text ends here: the first paste is truncated mid-word. Everything after this point (Alpha-2 exits, costs and tests; Alpha-3; Alpha-4; the Validation Matrix in Section 7; any later sections) has not been received.]**

---

# Part B — Stage 2 Audit & Critique

*Audited document: QRS-BTC-DELTA-S1-v1.0 (Part A). Section numbers such as "1.2E" or "2.1" refer to Part A.*

## B.1 Scope, limitations and verdict

**What was received.** Two pastes, merged in Part A:
- **Second paste (equations intact):** Sections 0 through 1.5C and the start of 1.5D. It ends inside the liquidation formula.
- **First paste (equations blank):** the rest of 1.5D and Section 2 (Alpha-1 in full, Alpha-2 up to its exit conditions). It ends at "Exit Predic".

**Checked line by line.** Every equation in Sections 1.1–1.5C (log in B.3.4). Logic, assumptions and cross-references in Section 2 were audited from the text.

**Still not checked** because the equations or text were never received: the liquidation and hard-safety formulas (1.5D); Alpha-1's normalized micro-price deviation, MPS and entry predicate; Alpha-2's VCR, HII and entry predicates; Alpha-2 exits onward; Alpha-3; Alpha-4; the Validation Matrix (Section 7). Stage 2 is therefore complete for everything received, but Stage 1 is not complete, so this audit cannot be called final.

**Not verified.** I could not confirm Delta-specific mechanics (mark-price construction, liquidation engine, funding interval, fee schedule, WebSocket depth/rate limits, contract specifications) from primary Delta documentation. A third-party SDK description reports that Delta Exchange India is INR-settled, which suggests contract specifications differ between Delta's entities. Every Delta-specific [EMP] claim should be checked against current Delta docs (see B.5). No code or data was run; nothing here is a statement about profitability.

**Verdict.** The specification is unusually disciplined about separating definitions, empirical facts and hypotheses, and most formulas in Sections 1.1–1.5C are correct as written (B.3.4). It is **not yet ready for Stage 3 synthesis**: five findings are Critical (they would produce false positives, mis-specified tests or an untestable core hypothesis), and eleven Major items affect cost realism, sizing and overfitting control, including two formula errors (M10 slippage, M11 Kelly). None of the findings says the strategies cannot work; they say the current text cannot yet show whether they do.

**Revision note.** Compared with the first version of this report: M1, M8, M9 and M10 were refined against the actual formulas; M11 and m11–m13 are new; m1 and m8 were extended; B.3.4 is new.

---

## B.2 Findings at a glance

| ID | Section | Severity | Finding |
|---|---|---|---|
| C1 | 1.2E | Critical | Trend t-statistic on log price ignores autocorrelated residuals; inflates with window length |
| C2 | 1.4B | Critical | Engle-Granger residual ADF needs different critical values; stationarity partly true by construction |
| C3 | 1.4C | Critical | HMM features are all unsigned, so "Trend" vs "Mean-Reverting" is not identifiable; leakage risk |
| C4 | 2.1 | Critical | Alpha-1 uses only Delta's own book; passive-fill adverse selection is structural, and fill selection is untestable without a queue model |
| C5 | 1.4D | Critical | DSR/BHY assume independent trials; parameter grids are highly correlated; overlapping holds break iid Sharpe variance |
| M1 | 1.3D, 2.1 | Major | H1 tests "queue depletion" with a trade-arrival parameter; η_t is undefined in the model; λ⁺>λ⁻ duplicates TFI |
| M2 | 2.2 | Major | Compression and Z-score breakout are coupled; fires on tiny absolute moves |
| M3 | 1.5A, 2.1 | Major | Cost model: single maker share cannot represent mixed legs; return basis (notional vs margin) unstated |
| M4 | 1.5D | Major | Linear-only liquidation logic; inverse perps differ; "maximum observed basis" is not a bound |
| M5 | 1.1, 2.1 | Major | Microstructure noise biases RV, BV, jump ratio and "tick ATR" at high frequency |
| M6 | 0, 1.4–1.5 | Major | [DEF] tag applied to models and approximations (Kelly, ruin, VaR, filters) |
| M7 | 2.1 | Major | Alpha-1 alone has 12+ free parameters; feasibility pre-test missing |
| M8 | 1.5C | Major | Ruin formula is a fixed-barrier hitting probability under Gaussian assumptions; Cornish-Fisher VaR is named but never defined |
| M9 | 1.4C | Major | BOCPD underspecified (predictive model, units, prior predictive), differs from Adams-MacKay, and detection delay may equal the holding period |
| M10 | 1.3E | Major | Slippage formula double-counts the half-spread, mixes units, and uses a square-root law calibrated for large metaorders |
| M11 | 1.5B | Major | Moment-adjusted Kelly condition has wrong coefficients (½ and ⅙ should be 1), understating skew and kurtosis penalties |
| m1–m13 | various | Minor | GKYZ labeling, micro-price naming, Kalman assumptions, EMA/VWAP details, OFI/OBI scope, notation collisions, funding gate, bootstrap block choice, RR_net inconsistency, undefined items, guards |

---

## B.3 Detailed findings

Severity scale: **Critical** = invalidates a claim or test as written, or likely to generate false discoveries; **Major** = materially affects realism, risk or overfitting; **Minor** = correctness or clarity fix.

### B.3.1 Critical

#### C1 — Critical [Section 1.2E]: Rolling OLS slope t-statistic on log price

**Issue.** Regressing ln P on time over a window gives residuals that are strongly serially correlated, because log price behaves like an I(1) process. Classical OLS standard errors assume independent residuals.

**Why it matters.** The standard error is understated, so the t-statistic is inflated and tends to grow with window length N even for a driftless random walk (the classic spurious-trend result). The claim that t_reg distinguishes "high-R-squared linear trends from noisy price spikes" does not hold.

**Fix.** Use Newey-West (HAC) standard errors with a lag rule stated in the spec, or test drift on returns using a variance-ratio or autocorrelation-robust statistic. Re-tag the normalization claim as [HYP] until shown on data.

#### C2 — Critical [Section 1.4B]: Cointegration and ADF on the perpetual–spot basis

**Issue.** Applying a standard ADF critical value to residuals of an estimated regression is invalid: because β and α are estimated, Engle-Granger/MacKinnon critical values apply. Separately, perp–spot β should be near 1 by arbitrage, and the spot index is an input to the mark price, so mean reversion of the basis is partly built in.

**Why it matters.** The test will over-reject a unit root, producing apparent tradable stationarity. A rolling β̂_t that floats freely also adds estimation noise and look-ahead risk if fitted on the full sample.

**Fix.** Use Engle-Granger critical values (or Phillips-Ouliaris / Johansen). Fix β=1 as the null structure and treat deviations as the signal. State which module consumes B_t and what trade it implies; it is not used in the visible parts of Alpha-1/2. Add guards for the half-life (undefined if φ≤0 or φ≥1) and specify the sampling interval Δt that converts φ into κ.

#### C3 — Critical [Section 1.4C]: Three-state HMM regime filter

**Issue.** The observation vector (ln σ_RV, |TFI|, ln s_q, J/RV) contains no signed or persistence information. It can separate volatility and liquidity regimes, but cannot distinguish a "Directional Trend" state from a "Quiet/Mean-Reverting" one. State names are assigned by hand after fitting (label switching).

**Why it matters.** Strategies gated on "State 2 = trend" are gated on something the model cannot see. Bounded features (|TFI|, J/RV in [0,1]) are poorly described by Gaussian emissions. Overlapping rolling-window features violate the conditional-independence assumption and make posteriors overconfident. "Forward filtering without look-ahead" is only true if parameters (A, means, covariances) were estimated on data strictly before the filtered period.

**Fix.** Add a persistence feature (rolling variance ratio, signed return autocorrelation, or Hurst-type statistic). Transform bounded features (logit) before Gaussian emissions. Fix labeling by a deterministic rule (e.g. ordering on volatility). Re-estimate parameters on a trailing window and filter only forward; log the refit schedule.

#### C4 — Critical [Section 2.1 (Alpha-1), 1.3C]: Single-venue, passive-fill microstructure scalper

**Issue.** Alpha-1 builds its signal only from Delta's own L2 book and trades, and enters with post-only limit orders at the touch. The spec lists adverse selection as a failure mode but frames it as an exception.

**Why it matters.** When a venue is not where price discovery happens, a resting passive order is filled disproportionately when the price has already moved elsewhere (the filler is informed by a different book). Fills therefore cluster on the losing side, so adverse selection is the default outcome, not a tail case. Fill selection also cuts the other way: the strongest signals are the ones where price runs away from the order and no fill occurs. Because OFI explains contemporaneous mid-price change well but forward change far less, a backtest that assumes fills at the touch will overstate performance. The proposed viability test (filled vs unfilled returns) is the right idea but cannot be run without a queue-aware simulator.

**Fix.**
1. Add a reference-venue feature (lead-lag from the most liquid BTC perpetual books) as a conditioning variable and as a toxicity filter.
2. Specify a queue-position simulator with latency, cancel-ack delay, partial fills and pro-rata/FIFO behavior as documented by Delta.
3. Report results separately for filled and unfilled signals and for the opportunity cost of unfilled ones.
4. Treat multi-level OBI as spoof-prone: add order-lifetime or trade-confirmed depth filters.

#### C5 — Critical [Section 1.4D]: Deflated Sharpe Ratio and BHY false-discovery control

**Issue.** DSR's expected-maximum benchmark assumes M independent trials. Parameter variants in this spec (weights, thresholds, horizons, multipliers) are highly correlated, so nominal M overstates the effective number of independent trials, while discarded variants from earlier exploration are easy to forget. The PSR/DSR variance formula also assumes roughly iid returns, which overlapping holds and volatility clustering violate. BHY controls the false discovery rate, not the chance that the single deployed strategy is a false positive.

**Why it matters.** Both errors mislead in opposite directions: ignoring discarded trials flatters the result; counting correlated variants as independent makes the test too harsh. A formal pass would not be trustworthy either way.

**Fix.** Record every variant ever evaluated (a trial ledger). Estimate effective independent trials by clustering variant return series. Compute Sharpe at the trade or fixed-interval level with a serial-dependence correction. Add a data-snooping-robust test (Romano-Wolf step-down or Hansen SPA) for the deployed candidate. Use the raw kurtosis in PSR/DSR and excess kurtosis in the Kelly expansion, and unify the γ notation.

### B.3.2 Major

#### M1 — Major [Sections 1.3D, 2.1 (H1)]: Hypothesis H1 mixes variables; double counting

**Issue.** H1 says "queue depletion accelerates (Hawkes branching ratio η_t > η_min)". The branching ratio is a property of the trade-arrival process, not a measure of queue depletion. The long/short rules also require λ⁺>λ⁻, which is nearly the same information as TFI already inside MPS.

**Why it matters.** The hypothesis is not testable as written (variable does not match the claim). As written in 1.3D, the Hawkes model has self-excitation only (no buy↔sell cross terms) and constant α_H, β_H, so the scalar condition η=α_H/β_H<1 is the right one, but "η_t" in H1 is undefined: it would require re-estimating the parameters over time, and no procedure is given. With this kernel, λ⁺−λ⁻ equals the baseline difference plus an exponentially decayed count imbalance, which is nearly the same information as TFI (volume-weighted) already inside MPS, so the entry rule counts the same flow signal twice. Real-time Hawkes estimates are unstable unless multi-print sweeps are aggregated per taker order and timestamp ties are handled; if cross-excitation is added later, stationarity becomes a spectral-radius condition on the branching matrix.

**Fix.** Restate H1 with a direct depletion measure (top-of-book queue change rate) or rename the Hawkes condition as a flow-clustering filter. Drop the λ⁺/λ⁻ condition or show incremental value via ablation. Specify the Hawkes fitting cadence, window and aggregation rule.

#### M2 — Major [Section 2.2 (Alpha-2)]: Breakout condition is coupled to the compression condition

**Issue.** The pre-condition requires low volatility compression (small S²), and the trigger requires |Z_VWAP| ≥ k_BB, where Z is scaled by that same small standard deviation.

**Why it matters.** During compression the band is narrow, so the trigger fires on very small absolute price moves, often comparable to the spread and tick size. The two conditions select events by construction rather than by independent evidence.

**Fix.** Add an absolute minimum breakout distance in ticks or in units of a longer-horizon ATR, and a spread-multiple floor. Test the compression and breakout conditions by ablation.

#### M3 — Major [Sections 1.5A, 2.1(6)]: Cost model structure

**Issue.** E_net uses one maker proportion ω_M, but Alpha-1 enters 100% maker and exits ~30% maker / 70% taker. Fees are charged on notional while returns may be quoted on margin; the leverage basis is not stated. The 30/70 exit blend is labeled "conservative" without measurement.

**Why it matters.** A single blend misstates round-trip fees for asymmetric legs and mixes bases when leverage varies. For a 2–30 s horizon, round-trip fees and spread can exceed the typical absolute mid-price move, which would settle H1 before any model is fitted.

**Fix.** Define fees per leg (entry and exit separately), on notional, with the fee schedule taken from Delta's current documentation (including tiers, rebates and any taxes). Add a feasibility pre-test: compute break-even move in bps and compare to the empirical distribution of |Δmid| at each horizon; if the median is below break-even, stop. Measure realized maker share in paper trading and replace the 30% assumption.

#### M4 — Major [Section 1.5D]: Liquidation and basis constraints

**Issue.** The liquidation boundary is written for a linear contract. The spec names both BTCUSDT (linear) and BTCUSD (inverse) but gives one formula. The hard-safety constraint adds the "maximum observed mark-to-mid basis dislocation" to the stop distance.

**Why it matters.** Inverse contracts have BTC-margined, convex PnL and different liquidation prices; fees and margin currency also differ. A maximum observed in a finite sample is not a bound on future dislocation, especially in a cascade.

**Fix.** Provide separate PnL and liquidation formulas per contract type, with maintenance-margin tiers and any liquidation fee taken from current Delta documentation. Replace the observed maximum with a high quantile plus a stress add-on, and enforce at order time using live mark price.

#### M5 — Major [Sections 1.1, 2.1]: Microstructure noise in volatility and ATR estimators

**Issue.** Realized variance, bipower variation and the jump ratio J/RV are computed on high-frequency increments. Bid-ask bounce inflates both RV and BV and biases jump separation. Alpha-1's TP/SL use "tick ATR", which is not defined in the visible text.

**Why it matters.** Jump flags and stop distances may be driven by spread noise rather than information, producing stops inside the noise band or spurious no-trade states.

**Fix.** Compute RV/BV on mid or micro-price returns sampled at a fixed horizon (or with a noise-robust estimator such as pre-averaging or two-scale), and define tick ATR explicitly on mid-price with a stated sampling rule and a floor of a few spreads.

#### M6 — Major [Sections 0, 1.4–1.5]: Epistemic tagging creep

**Issue.** The taxonomy reserves [DEF] for identities true by construction. Several items tagged [DEF] are modeling assumptions or approximations: moment-expanded Kelly, risk of ruin, Cornish-Fisher VaR, Kalman state-space structure, HMM and BOCPD models, Kyle-lambda regression.

**Why it matters.** Readers (and Stage 3) may treat model assumptions as settled. That weakens the section's main safeguard against conflating mathematics with alpha.

**Fix.** Add a fourth tag, [MOD — modeling assumption], or move these to [HYP] with an explicit validation test. Keep [DEF] to the definitions (log return, RV, BV, spreads, EMA recursion, expectancy identity).

#### M7 — Major [Section 2.1(5)]: Parameter proliferation in Alpha-1

**Issue.** Free parameters include three independent weights, θ_entry, θ_exit, τ₁, τ₂, τ_max_hold, k_TP, k_SL, plus η_min, s_max, Q_min, τ_fill and the HMM/BOCPD settings.

**Why it matters.** With 12+ degrees of freedom on a few months of data, in-sample optimization will find configurations that fail out of sample, and the multiple-testing correction (C5) will be heavy.

**Fix.** Fix most parameters from microstructure reasoning, search only a small number, and use purged, embargoed walk-forward validation (combinatorial purged cross-validation if available). Report sensitivity surfaces rather than a single optimum.

#### M8 — Major [Section 1.5C]: Risk of ruin and Cornish-Fisher VaR

**Issue.** The risk-of-ruin expression exp(−2μ_e|ln(1−B)|/σ_e²) is the probability that Brownian motion with drift ever hits a fixed barrier below initial equity. It assumes Gaussian, independent increments, constant drift, and consistent time units for μ_e and σ_e². A drawdown breach is measured from a running peak, which is more likely. The heading of 1.5C promises Cornish-Fisher VaR, but only CVaR is defined; CF quantiles are only monotone over a limited range of skewness and kurtosis.

**Why it matters.** Fat tails, volatility clustering and serial dependence make the closed form optimistic, and CF can return non-monotone, nonsensical quantiles for strongly non-normal returns.

**Fix.** Estimate drawdown and ruin probabilities by block-bootstrap Monte Carlo on realized trade sequences, report CF only with a monotonicity check, and keep ES (historical) as the primary tail measure.

#### M9 — Major [Section 1.4C]: BOCPD specification and detection delay

**Issue.** BOCPD needs a predictive model (conjugate prior and likelihood) and a hazard whose units are defined (events, bars or seconds); neither is given. The spec's change-point term uses the prior predictive P(x_t|∅), whereas the original Adams-MacKay recursion uses the same run-conditional predictive in both terms (under which, with a constant hazard, P(r_t=0) equals the hazard regardless of data). Either variant can be valid, but ∅ and x_t^(r) must be defined and the chosen variant stated; the rule r ≤ k is sensible under both.

**Why it matters.** Run-length mass moves to short run lengths only after several post-change observations, so the flag may arrive after much of a 2–30 s trade has already played out.

**Fix.** State the model (e.g. Student-t on returns), hazard units and k in the same units as the holding period. Measure detection delay on known breaks and compare to τ_max_hold.

#### M10 — Major [Section 1.3E]: Slippage formula and square-root impact

**Issue.** (i) BookWalk is defined as execution VWAP minus mid, so it already contains the half-spread; adding s_q/2 double-counts it. (ii) Units are mixed: s_q is a fraction, BookWalk is in price units, and the result is labeled bps. (iii) σ_RV is a window-sum volatility over N increments, not the daily volatility the square-root law is calibrated to, and κ is neither defined nor calibrated. (iv) The square-root law is established for large metaorders over long horizons, while the engine trades small clips.

**Why it matters.** The cost term is overstated by the double count, and the impact term has no calibrated meaning at this size. Both distort the feasibility pre-test in M3.

**Fix.** Use exact book-walk from the L2 snapshot, expressed in bps of mid, plus an empirical slippage term calibrated from paper-trading fills. Drop s_q/2 when BookWalk is used. Keep the square-root form only for sizing-sensitivity studies, with σ and V_ADV on the same time basis.

#### M11 — Major [Section 1.5B]: Moment-adjusted Kelly condition has wrong coefficients

**Issue.** Expanding E[ln(1+fR)] to fourth order gives the first-order condition μ − f·E[R²] + f²·E[R³] − f³·E[R⁴] = 0. In central moments with small μ this is μ − fσ² + f²γ₁σ³ − f³(γ₂+3)σ⁴ ≈ 0. The spec has f²/2 and f³/6 on the last two terms, so the skew term is halved and the kurtosis term is divided by six. The expansion also drops μ terms, is only valid for |fR|<1 (which high leverage can violate), and a truncated series can have spurious roots.

**Why it matters.** The error understates the kurtosis and negative-skew penalties, so it inflates the Kelly fraction in exactly the heavy-tail regime the section is meant to protect against. The shrinkage factor κ_Kelly softens but does not fix this.

**Fix.** Correct the coefficients and state the root-selection rule (smallest positive root, with a validity check on |fR|). Better: avoid the series and maximize Σ ln(1+fR_i) over the empirical trade sample, including stop-limited losses, with uncertainty on μ handled through shrinkage.

### B.3.3 Minor

- **m1 — GKYZ (1.1B).** The formula is Garman-Klass plus an opening-jump term ln(O_i/C_{i−1}). It is derived under zero drift, so the heading's claim of handling drift is too strong (Rogers-Satchell or the Yang-Zhang combination is drift-robust). In continuous 24/7 bars O_i ≈ C_{i−1}, so the jump term vanishes and it reduces to Garman-Klass. Normalize range estimators by elapsed time, since volume bars have variable duration.
- **m2 — "Micro-price" naming (1.3A).** The size-weighted average of best bid and ask is an imbalance-weighted mid. Stoikov's micro-price is a martingale-adjusted conditional expectation. Rename, or implement the latter.
- **m3 — Kalman filter (1.4A).** Gaussian noise handles jumps poorly: use Student-t or innovation gating on ỹ_t. Micro-price noise is state-dependent (it embeds book imbalance), so velocity can duplicate the OBI signal if both enter a score.
- **m4 — Irregular-time EMA (1.2A).** The reduction to α=2/(N+1) holds only through a matching reparameterization of τ; state the interpolation rule (previous tick vs linear).
- **m5 — Decayed VWAP/variance (1.2D).** Define γ per unit time in irregular sampling (γ_i = exp(−Δt_i/τ)), and use a reliability-weight correction for the weighted variance.
- **m6 — Sampling clocks (1.1A).** Calibrate V_thresh adaptively (otherwise bars shrink in volatile regimes and expand in quiet ones); define notional correctly for inverse vs linear; the imbalance-clock expectation estimator is unspecified.
- **m7 — OFI and Kyle's lambda (1.3C, 1.3E).** CKS OFI is defined on best quotes; multi-level extensions exist and should be cited if used. The ΔP-on-OFI regression is contemporaneous and describes impact, not forward predictability.
- **m8 — Notation (throughout).** γ is used for VWAP decay, the Euler-Mascheroni constant, latency decay (γ_lat) and skewness/kurtosis (γ₁/γ₂ and γ̂₃/γ̂₄); κ for both the impact coefficient and κ_Kelly; S for spread, Kalman innovation variance, weighted variance and the HMM regime; λ for Hawkes intensity, OBI decay, Kyle's lambda and the change-point hazard. Unify.
- **m9 — Funding gate (1.5D).** Funding is paid on holding at the timestamp, so a straddling hold pays the full amount regardless of duration. For short holds this should be a hard rule (flatten or block before settlement when paying), not an alpha-vs-cost comparison.
- **m10 — Stationary bootstrap (1.4D).** State the mean block-length selection rule; for tick-level data with intraday seasonality, day-level (circular) block resampling is a useful cross-check.
- **m11 — RR_net (1.5A).** It subtracts C_RT/2 on each side, while E_net and p_BE charge the full C_RT to wins and losses. The consistent form is (R_w − C_RT)/(R_l + C_RT). Since this is tagged [DEF], it should be exact.
- **m12 — Named but undefined.** SE(β̂₁) inside t_reg (1.2E), Cornish-Fisher VaR (1.5C), "volatility-normalized RSI" (1.2B), ATR^tick (2.1) and the imbalance-clock expectation (1.1A).
- **m13 — Guards and scope.** RSI is undefined when D̄_t = 0. OBI weights levels by rank, not by price distance, so sparse books over-weight far levels (weight by ticks from the touch). OFI_t(τ) is unnormalized; depth-normalize before comparing across regimes.

### B.3.4 Formula verification log (Sections 1.1–1.5C)

Legend: ✓ correct as written · ⚠ correct but with an issue noted · ✗ error · — not checkable (equation not received).

| Section | Formula | Result |
|---|---|---|
| 1.1A | Volume-clock threshold, log return | ✓ (notional definition depends on contract type, m6) |
| 1.1B | RV, BV (π/2 · N/(N−1), N−1 terms), J = max(0, RV−BV), Parkinson | ✓ |
| 1.1B | GKYZ | ⚠ opening-jump GK, not drift-robust (m1) |
| 1.2A | Irregular EMA, α_i = 1−exp(−Δt_i/τ) | ✓ (interpolation rule unstated, m4) |
| 1.2B–C | Wilder RSI, TR, ATR, ATR% | ✓ (RSI zero-denominator guard, m13) |
| 1.2D | Decayed VWAP; decayed weighted-variance recursion | ✓ (γ per step, m5) |
| 1.2E | Slope β̂₁ and t_reg | ⚠ SE undefined (m12); inference invalid on log price (C1) |
| 1.3A | Quoted, relative, effective, realized spread; weighted mid | ✓ (naming, m2) |
| 1.3B | OBI | ✓ (rank-based weights, m13) |
| 1.3C | OFI e_n (Cont-Kukanov-Stoikov), OFI_t(τ), TFI | ✓ (OFI unnormalized, m13) |
| 1.3D | Hawkes intensity, η = α_H/β_H | ⚠ valid for self-excitation only; η_t undefined; redundancy with TFI (M1) |
| 1.3E | Kyle's lambda regression | ⚠ contemporaneous (m7) |
| 1.3E | Slippage formula | ✗ double count, mixed units (M10) |
| 1.3E | Latency decay of alpha | ⚠ [HYP]; functional form assumed; γ_lat collides with other γ (m8) |
| 1.4A | Kalman F, H, Q (white-noise acceleration), predict/update, R_t | ✓ (Gaussian, state-dependent noise, m3) |
| 1.4B | OU/AR(1) mapping, half-life, σ_eq | ✓ (needs 0<φ<1); ADF critical values (C2) |
| 1.4C | HMM forward filter | ✓ as a recursion; features and leakage (C3) |
| 1.4C | BOCPD recursion | ⚠ change-point term uses P(x_t\|∅), differs from Adams-MacKay (M9) |
| 1.4D | BHY k*, c(M) | ✓ (trial counting, C5) |
| 1.4D | SR_0 and DSR | ✓ as formulas (independence and iid assumptions, C5) |
| 1.5A | C_RT, E_net, p_BE | ✓ (per-leg fees, M3) |
| 1.5A | RR_net | ✗ inconsistent with E_net and p_BE (m11) |
| 1.5B | Moment-adjusted Kelly condition | ✗ coefficients (M11) |
| 1.5B | f_deploy | ✓ |
| 1.5C | CVaR definition | ✓; Cornish-Fisher VaR not defined (m12) |
| 1.5C | Risk of ruin | ⚠ fixed-barrier hitting probability under Gaussian assumptions (M8) |
| 1.5D | Liquidation boundary, hard-safety constraint | — equations not received |
| 2.1–2.2 | Normalized micro-price deviation, MPS, entry predicates, VCR, HII | — equations not received |

---

## B.4 Cross-cutting issues

- **Look-ahead leakage checklist.** HMM parameters, Kalman and BOCPD priors, rolling normalizations (Z-scores, ATR), volume-clock thresholds, and any funding-rate inputs must use only data available at decision time. Log refit times.
- **Replay realism.** Event-driven replay needs latency distributions (not a fixed value), cancel/replace delays, partial fills, API rate limits on order and cancel churn from the 500–3000 ms TTL loop, exchange downtime, auto-deleveraging and mark-price jumps.
- **Data availability.** 90–180 days of tick-level incremental L2 plus snapshots and trades is a binding constraint. Confirm vendor coverage for Delta, or start recording the live feed now; sequence gaps and snapshot reconciliation must be audited.
- **Total parameter budget.** Four strategy modules plus regime models imply a very large search space. Pre-register which modules and parameters will be tested, and count them all in the DSR ledger.
- **Hypothesis hygiene.** The H₀ statement is good. Add the test statistic, horizon, sample split and the family of tests it belongs to, so rejection is well defined.

---

## B.5 Delta-specific claims to verify before Stage 3

These items are stated as [EMP] or assumed in the spec. They must be confirmed from current Delta Exchange documentation (and the correct entity: Global vs India), because exchange rules change.

- Mark-price construction (spec: composite spot index plus exponentially smoothed basis), liquidation trigger, margin tiers and liquidation fee.
- Funding formula and settlement interval; whether the next funding rate is observable in advance.
- Contract specifications for the symbols used: linear vs inverse, margin currency, tick size, contract multiplier.
- Fee schedule: maker/taker rates, tiers or rebates, any taxes, and how fees are computed on notional.
- WebSocket channels: L2 depth available (spec assumes top 10 levels, sub-100 ms), snapshot/delta semantics, sequence numbers or checksums, trade-print fields (maker/taker flag).
- API limits: order, cancel and request rate limits; post-only reject behavior; order types supported (IOC, reduce-only, bracket orders).
- Historical data: availability of tick-level L2 and trades, and the retention window.

---

## B.6 Suggested validation gates (proposal, not a result)

| Gate | Name | Pass condition (to be set by the research owner) |
|---|---|---|
| G0 | Feasibility | Break-even move in bps (fees + spread + slippage) vs the empirical distribution of \|Δmid\| at each holding horizon. Stop a module that cannot clear costs. |
| G1 | Data audit | Sequence gaps, clock skew, snapshot reconciliation, mark vs index vs last coverage. |
| G2 | Event-driven replay | Queue-aware fills, latency distributions, rate limits; report filled vs unfilled signals. |
| G3 | Out-of-sample inference | Purged, embargoed walk-forward; stationary-bootstrap CI on net expectancy; DSR with a trial ledger; SPA or Romano-Wolf. |
| G4 | Paper trading | Fixed parameters, live feed; reconcile realized fills and fees against the replay. |
| G5 | Minimum-size live pilot | Hard kill-switches, mark-price-based risk limits, and a pre-registered stopping rule. |

---

## B.7 Handoff notes for Stage 3 and open items

**Apply before synthesis:** C1–C5 corrections; the H1 restatement (M1); the cost-model restructure and feasibility pre-test (M3); the slippage and Kelly formula corrections (M10, M11); the [MOD] tag (M6). Treat the remaining M-items and m-items as a punch list.

**Still needed to finish Stage 1 and the audit (not received):**

- Section 1.5D from the liquidation formula onward, with equations: the liquidation boundary, the second liquidation equation and the hard-safety constraint.
- Section 2 equations: Alpha-1 normalized micro-price deviation, MPS (two equations) and entry predicate; Alpha-2 VCR, HII, and the long and short entry predicates.
- Alpha-2: exit predicates, costs, failure modes, viability tests.
- Alpha-3 and Alpha-4 (including the intended consumer of the OU basis model).
- Sections after the strategies, including the Validation Matrix (Section 7 reference) and any execution/risk architecture.

---

*This report is a technical review of a research specification. It makes no profitability claim and is not financial or trading advice.*
