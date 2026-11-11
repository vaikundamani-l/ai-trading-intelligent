# Production Operations & Deployment Guide

This guide details the institutional operational procedures for running, monitoring, securing, backing up, and recovering the **BTC Quantum Intelligence** platform (`ai-trading-intelligent`).

---

## 1. Architecture & Deployment Modes

The platform supports two institutional deployment topologies:

### Mode A: Production Gateway (Nginx + Standalone Next.js + FastAPI)
* **Single Public Port (80 / 443)**: Nginx reverse proxy handles routing, HTTP security headers, static caching, and persistent WebSocket connection upgrades.
* **Internal Network Isolation**: Backend (port 8000) and Frontend (port 3000) run on an isolated container network. No direct exposure of internal ports to the host or internet.
* **Minimal Attack Surface**: Next.js runs in `standalone` mode as unprivileged `nextjs` (UID 1001), and backend runs as `appuser` (UID 10001) with `no-new-privileges:true`.

Launch command:
```bash
ai-trading-intelligent docker prod
# or
docker compose -f docker-compose.prod.yml up -d --build
```

### Mode B: Host Systemd Daemon (Linux Bare-Metal or VM)
* Managed background daemons supervised by `systemd`.
* Automatic restart on process exit or server reboot.
* Log shipping via `journald`.

Install services:
```bash
sudo ./systemd/install_systemd.sh
```

---

## 2. Platform CLI Control Reference

The application is controlled globally from any shell using `ai-trading-intelligent`:

| Command | Action |
| :--- | :--- |
| `ai-trading-intelligent start` | Starts Backend and Frontend in production mode |
| `ai-trading-intelligent start --dev` | Starts in development mode with Next.js Turbopack |
| `ai-trading-intelligent stop` | Cleanly stops all services and releases ports 8000 & 3000 |
| `ai-trading-intelligent restart` | Performs a clean stop and instant restart |
| `ai-trading-intelligent status` | Shows process health, PIDs, active ports, and live BTC price |
| `ai-trading-intelligent health` | Formatted institutional metrics (uptime, RSS memory, WS clients, feed safety) |
| `ai-trading-intelligent backup` | Executes online atomic SQLite snapshot with integrity verification |
| `ai-trading-intelligent restore <file>` | Restores ledger database with safety snapshots and WAL cleanup |
| `ai-trading-intelligent logs [backend\|frontend]` | Live streaming logs |
| `ai-trading-intelligent docker [up\|prod\|down\|status]` | Docker container lifecycle management |
| `ai-trading-intelligent alias <name>` | Creates custom alias (e.g. `ai-trading-intelligent alias btc`) |

---

## 3. Security & Governance Guardrails

### Host Header & Origin Enforcement
* Configured via `ALLOWED_HOSTS` in `.env` (default: `localhost,127.0.0.1,backend,frontend,gateway`).
* Requests with foreign or re-bound host headers are rejected with HTTP 400.
* Browser origins are validated against `ALLOWED_ORIGINS` (HTTP 403 on untrusted origins).

### API Token Protection for Mutating Operations
To protect execution endpoints on exposed or remote servers:
1. Set `API_AUTH_TOKEN=your_strong_secret_token` in `.env`.
2. Mutating operations (`/api/paper-trade/order`, `/api/engine/toggle`, `/api/predictions/retrain`) require:
   * Header `X-API-Key: your_strong_secret_token`, or
   * Header `Authorization: Bearer your_strong_secret_token`.
3. WebSockets require `ws://.../ws?token=your_strong_secret_token`.
4. If `API_AUTH_TOKEN` is unset, the system operates in local trusted paper-trading mode.

### HTTP Security Headers
Every HTTP response automatically includes:
* `X-Content-Type-Options: nosniff`
* `X-Frame-Options: DENY`
* `Referrer-Policy: strict-origin-when-cross-origin`
* `X-XSS-Protection: 1; mode=block`

---

## 4. Automated Database Ledger Backup & Recovery

The persistent ledger lives at `backend/data/btc_quantum.db` running in **SQLite WAL (Write-Ahead Logging)** mode.

### Online Atomic Backup
Never perform a raw file copy of an active SQLite database in WAL mode. Use the automated backup utility:
```bash
ai-trading-intelligent backup
```
* Uses SQLite Online Backup API (`src.backup(dst)`).
* Performs `PRAGMA integrity_check` on the completed copy before saving.
* Automatically rotates and retains the last 30 snapshots in `backups/ledger-YYYYMMDD-HHMMSS.db`.

### Disaster Recovery / Database Restore
To restore from a verified snapshot:
```bash
ai-trading-intelligent restore backups/ledger-20261111-134304.db
```
* Verifies snapshot integrity before touching production files.
* Creates a safety backup of the existing database (`safety-pre-restore-TIMESTAMP.db`).
* Purges orphaned `-wal` and `-shm` index files to prevent cache desynchronization.
* Atomically installs the restored database.

---

## 5. Health Probes & Monitoring

The platform provides Kubernetes- and orchestrator-compliant health endpoints:

* **Liveness Probe**: `GET /health/live`
  * Returns `{"status": "alive", "timestamp": ...}` with HTTP 200.
  * Verifies process responsiveness.

* **Readiness Probe**: `GET /health/ready`
  * Checks database query responsiveness and market data streaming status.
  * Returns HTTP 200 when ready; HTTP 503 Service Unavailable when disconnected or corrupted.

* **Observability Status**: `GET /health/status`
  * Returns uptime, RSS memory consumption (MB), active WebSocket client count, market feed latency, and portfolio summary.
  * Inspected on terminal with `ai-trading-intelligent health`.
