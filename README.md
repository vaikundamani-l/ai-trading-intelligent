# BTC QUANTUM INTELLIGENCE
### Real-Time Bitcoin Trading Research & Signal Dashboard (Delta Exchange India)

**BTC Quantum Intelligence** is an institutional-grade, full-stack quantitative trading research platform built specifically for **Delta Exchange India** `BTCUSD` perpetual futures. It couples genuine live market data ingestion (REST + WebSocket) with deterministic strategy signal calculation, statistical AI price forecasting, risk governance, paper-trading simulation, and historical backtesting.

---

## 1. Epistemic Architecture & Financial Guardrails

Per the **Stage 3 Research Specification** (`QRS_BTC_DELTA_Stage3_Research_and_New_Strategies.md`):

* **READ-ONLY / PAPER TRADING ONLY**: The system does not place real-money orders. No API trading keys or withdrawal permissions are accepted or stored.
* **FACTUAL REAL-TIME MARKET DATA**: Prices originate directly from verified Delta Exchange India public feeds (`api.india.delta.exchange` and `public-socket.india.delta.exchange`). When data is stale (>5s) or disconnected, the system enforces **`NO TRADE — DATA UNAVAILABLE`** and disables active signals.
* **REALISTIC COST ACCOUNTING**: All trade models, risk budgets, and backtests incorporate conservative friction:
  * **Exchange Taker Fee**: $0.05\%$ per leg with $18\%$ GST on fees $\to 5.9\text{ bps}$ per leg ($11.80\text{ bps}$ round-trip).
  * **Execution Slippage**: Assumed $1.0\text{ bp}$ per leg ($2.0\text{ bps}$ round-trip) to model book-walking and queue crossing.
  * **Total Conservative Round-Trip Friction**: $\mathbf{13.80\text{ bps}}$ of entry notional.
* **UNPROVEN PROFITABILITY NOTICE**: Unit tests and backtests validate software correctness and mechanical execution rules; they do **not** constitute proof of future live trading profitability.

---

## 2. Quantitative Strategy Family

### ALPHA-5: SBR-5 Sweep and Reclaim (Primary Strategy)
Ported directly from the research backtester `btc_sbr5_backtest.py`. Operates on completed 5-minute candles:
1. **Range Lookback**: Lowest low ($L_{24}$) and highest high ($H_{24}$) of previous 24 completed bars (2 hours).
2. **Sweep Threshold**: $\text{Low}_t < L_{24} - \max(\$0.50, 0.12 \times \text{ATR}_{14})$.
3. **Reclaim Window**: Candle closes back inside the prior range: $L_{24} + 0.10 \times \text{ATR}_{14} < \text{Close}_t < L_{24} + 1.20 \times \text{ATR}_{14}$.
4. **Volume Impulse**: Candle volume $\ge 1.25 \times$ the 24-bar volume moving average.
5. **Execution**: Next-bar open fill at executable ask (for buy) or bid (for sell), plus modeled slippage.
6. **Stop & Target**: Stop buffered by $0.10 \times \text{ATR}_{14}$, clamped to $[0.15\%, 0.80\%]$. Target set at $1.80\text{R}$ gross. Maximum hold period strictly 25 minutes (5 candles).
7. **Funding Gate**: Trade blocked if a snapshot (00:00, 08:00, 16:00 UTC) occurs within 2 minutes before entry through 2 minutes after the 25-minute holding period.

### ALPHA-1R: Order-Flow Intelligence (Research Only)
Analyzes Top-15 order-book imbalance (OBI), trade flow imbalance (TFI), and weighted micro-price deviation ($P_{\text{wmid}} - P_{\text{mid}}$). Classifies instantaneous buying/selling pressure without assuming depth alone guarantees directional edge.

### ALPHA-2R: Volatility Compression Breakout (Research Only)
Calculates the Volatility Compression Ratio ($\text{VCR} = \text{RV}_6 / \text{median}(\text{RV}_6, 48\text{ bars})$). Rejects breakouts unless the completed 5m bar exceeds the 12-bar range by at least $\max(0.30 \times \text{ATR}_{14}, 3\times\text{spread}, 2\text{ ticks})$.

### ALPHA-3R: BTC Basis Analysis (Hedged Only / Disabled)
Tracks the difference between perpetual and reference spot prices ($B_t = \ln P_{\text{perp}} - \ln P_{\text{spot}}$) and fits an AR(1) Ornstein-Uhlenbeck mean-reversion process. Hedged basis trading remains disabled unless both spot and perp execution legs are verified.

### ALPHA-4R: Market Dislocation Protection (System Risk Governor)
Continuous risk governor monitoring for mark-to-mid dislocation ($>50\text{ bps}$), sudden 5m return jumps ($>2.5 \times \text{ATR} / \text{Close}$), and spread spikes ($>15\text{ bps}$). Triggers **`HALTED / DATA UNSAFE`** and initiates a 10-minute cooldown.

---

## 3. Statistical AI Price Prediction Engine

* **Horizons**: Next 5 minutes, 15 minutes, 30 minutes, 1 hour.
* **Model Pipeline**: Directional classifiers (Logistic Regression & Volatility Scaler) trained using chronological walk-forward splits ($70\%$ train, $30\%$ test).
* **Calibration Metrics**: Evaluated against Brier score, log loss, and directional accuracy.
* **Anti-Fabrication Guard**: If models lack sufficient clean historical candles or fail calibration, displays **`PREDICTION UNAVAILABLE — MODEL NOT VALIDATED`** rather than generating synthetic confidence percentages.

---

## 4. Multi-Timeframe Charting & Live 1-Second Trend Intelligence

The platform features an institutional-grade interactive chart powered by **Lightweight Charts** that continuously syncs with genuine Delta Exchange India market ticks:

* **8 Native Timeframes**: Full support for `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `4h`, and `1d` candle resolutions.
* **1-Second Real-Time Candle Updates**: When live price ticks arrive, the active forming candle is immediately updated on the chart canvas (`candleSeries.update(...)`), seamlessly advancing high, low, close, and volume. When the bar bucket rolls over, a new candle is automatically initialized without page reloading or jarring redrawing.
* **Dynamic 1-Second Trend Indicator**:
  * Evaluates trend direction every second: `STRONG BULLISH`, `BULLISH`, `STRONG BEARISH`, `BEARISH`, or `RANGING / CHOP`.
  * Real-time exponential moving average (EMA 9, EMA 21, EMA 50) and RSI 14 continuous recalculation.
  * Live pulsing status badge displayed prominently in the chart header: `[● 1s Trend: BULLISH ▲ (+0.14%) | EMA9 > EMA21 | RSI: 58.2]`.
* **Multi-Timeframe Trend Matrix Ribbon**:
  * An automated trend scanner continuously monitors all 8 timeframes.
  * Live colored indicators (Green `▲` Bullish, Red `▼` Bearish, Amber `■` Ranging) on each timeframe button allow traders to observe macro-to-micro market alignment at a glance.
  * One-click timeframe switching instantly re-centers the chart, adjusts indicator overlays, and transitions to 1-second live updating for the selected resolution.
* **Institutional Technical Overlays**:
  * EMA 9, EMA 21, EMA 50, EMA 200
  * Volume-Weighted Average Price (VWAP)
  * Bollinger Bands (20, 2)
  * Average True Range (ATR 14) & Relative Strength Index (RSI 14)
  * Dynamic SBR-5 24-period Range High ($H_{24}$) and Range Low ($L_{24}$) liquidity boundaries
  * Real-time Stop Loss (1.8R), Take Profit, and Entry zone price lines

---

## 5. Technology Stack

* **Frontend**: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, Lightweight Charts (v5), Lucide icons.
* **Backend**: Python 3.12, FastAPI, Uvicorn, WebSockets, Pandas, NumPy, Scikit-learn, Pydantic.
* **Database**: SQLite with Write-Ahead Logging (WAL mode) for persistent signals, paper trades, alerts, and risk states.
* **Deployment**: Docker & Docker Compose configuration, plus shell runner `run_dev.sh`.

---

## 6. Platform Control: Start, Stop & Management

You can control the entire application (both the Python FastAPI backend and Next.js frontend) directly from **any terminal** using the `ai-trading-intelligent` command.

### Quick Commands Reference

| Action | Terminal Command | Description |
| :--- | :--- | :--- |
| **Start Platform** | `ai-trading-intelligent start` | Starts Backend (port 8000) & Frontend (port 3000) in optimized production mode |
| **Start Dev Mode** | `ai-trading-intelligent start --dev` | Starts with hot-reloading development server for UI development |
| **Stop Platform** | `ai-trading-intelligent stop` | Cleanly stops all backend and frontend processes |
| **Check Status** | `ai-trading-intelligent status` | Displays process health, PIDs, active ports, and live Delta India BTC price |
| **System Health** | `ai-trading-intelligent health` | Formatted institutional metrics (uptime, memory RSS, WS clients, feed safety) |
| **Backup Ledger** | `ai-trading-intelligent backup` | Atomic online SQLite WAL snapshot with integrity verification |
| **Restore Ledger** | `ai-trading-intelligent restore <file>` | Restores database snapshot with pre-restore safety copies and WAL cleanup |
| **Restart Platform** | `ai-trading-intelligent restart` | Performs a clean stop and restart of both services |
| **Docker Control** | `ai-trading-intelligent docker [up\|prod\|down]` | Manages Docker containers (standard or production Nginx gateway) |
| **View Live Logs** | `ai-trading-intelligent logs` | Views real-time logs (`logs backend` or `logs frontend`) |

### How It Works

#### 1. How to Start
Open any terminal and run:
```bash
ai-trading-intelligent start
```
* **What happens**:
  1. The **FastAPI Backend** starts on `http://localhost:8000`, connects to the Delta Exchange India live WebSocket (`wss://public-socket.india.delta.exchange`), loads historical candles, and initializes the SBR-5 strategy & statistical AI prediction engine.
  2. The **Next.js Frontend** starts on `http://localhost:3000` with the institutional dark trading dashboard.
  3. Process IDs are tracked in `.pids/`, and logs are streamed to `logs/backend.log` and `logs/frontend.log`.
  4. Access the dashboard in your browser at **http://localhost:3000**.

#### 2. How to Stop
When you are done or want to halt the servers:
```bash
ai-trading-intelligent stop
```
* **What happens**:
  1. Gracefully terminates the backend and frontend background processes using their registered PIDs.
  2. Ensures ports `8000` and `3000` are completely freed.
  3. Confirms shutdown with `All services stopped cleanly.`

#### 3. How to Check Live Status
To see if both services and market feeds are running:
```bash
ai-trading-intelligent status
```
* **Sample output**:
  ```text
  === BTC Quantum Intelligence Platform Status ===
  Backend:  ● RUNNING (Port 8000, PID: 83271) | Feed: LIVE | BTC: $81081.5
  Frontend: ● RUNNING (Port 3000, PID: 71983) -> http://localhost:3000
  ```

#### 4. How to Inspect Live Logs
```bash
# View backend logs (market data, strategy evaluations, AI forecasts):
ai-trading-intelligent logs backend

# View frontend logs (Next.js compilation and routes):
ai-trading-intelligent logs frontend
```

#### 5. In-Browser One-Click Start / Stop (Engine Pause)
In addition to stopping the full platform from the command line, you can pause or resume trading evaluations directly from the website without shutting down the servers:
* Open **http://localhost:3000**
* In the top navigation bar, click **`[ ⏸ Stop Engine ]`** to pause signal evaluations and paper trade execution.
* Click **`[ ▶ Resume Engine ]`** to resume.

---

### Alternative Manual Step-by-Step Launch

#### 1. Start the Backend:
```bash
cd backend
python3 -m pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Start the Frontend:
```bash
cd frontend
npm install
npm run dev
```

---

## 7. Running Automated Tests

To run the complete test suite (both the baseline research tests and backend unit tests):

```bash
# 1. Run Backend Strategy & System Tests (7 tests)
PYTHONPATH=backend python3 -m pytest backend/tests/test_backend.py

# 2. Run Original Research Backtester Tests (6 tests)
python3 -m pytest BTC_Trading_Website_4_Files/test_btc_sbr5.py
```
All 13 tests execute deterministically and verify SBR-5 sweep/reclaim logic, stop/target calculations, conservative fee deductions, funding schedule blocks, and dislocation filters.

---

## 8. Docker Deployment

To launch the entire platform in isolated Docker containers:
```bash
docker compose up --build -d
```
* Frontend accessible at `http://localhost:3000`
* Backend API accessible at `http://localhost:8000`

---

## 9. Remaining Limitations & Research Notes

1. **Exchange Queue Priority**: Delta Exchange India order-book snapshots provide top-level depth but do not reproduce FIFO queue queue position. Passive maker orders can face adverse selection during directional price shocks.
2. **Cross-Venue Leadership**: Single-venue order flow on Delta Exchange India can lag global liquidity venues (e.g. Binance/Bybit). Future iterations may incorporate external reference price impulses.
3. **Funding Schedule Verification**: Delta Exchange India scheduled BTCUSD funding intervals are modeled at 05:30, 13:30, and 21:30 IST (00:00, 08:00, 16:00 UTC). Live changes should be verified periodically against exchange announcements.
