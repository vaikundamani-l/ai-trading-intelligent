import sqlite3
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.config import settings

def get_connection():
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency between reader/writer threads
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_db():
    conn = get_connection()
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            datetime_utc TEXT NOT NULL,
            strategy TEXT NOT NULL,
            direction INTEGER NOT NULL,
            action TEXT NOT NULL,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            risk_reward REAL,
            estimated_fees_bps REAL,
            estimated_slippage_bps REAL,
            net_reward_bps REAL,
            reasons TEXT,
            invalidation_risks TEXT,
            market_regime TEXT,
            status TEXT DEFAULT 'ACTIVE',
            candle_timestamp INTEGER
        );
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            created_at TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            symbol TEXT NOT NULL,
            direction INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            notional_usd REAL NOT NULL,
            contracts INTEGER NOT NULL,
            gross_bps REAL,
            fees_bps REAL,
            net_bps REAL,
            pnl_usd REAL,
            equity_after REAL,
            status TEXT DEFAULT 'OPEN',
            exit_reason TEXT
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            datetime_utc TEXT NOT NULL,
            horizon TEXT NOT NULL,
            observed_price REAL NOT NULL,
            bullish_prob REAL,
            bearish_prob REAL,
            expected_move_usd REAL,
            volatility_pct REAL,
            model_version TEXT NOT NULL,
            training_date TEXT NOT NULL,
            calibration_status TEXT NOT NULL,
            is_validated INTEGER DEFAULT 0,
            actual_future_price REAL,
            is_correct INTEGER
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            datetime_utc TEXT NOT NULL,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL,
            acknowledged INTEGER DEFAULT 0
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            equity REAL NOT NULL,
            peak_equity REAL NOT NULL,
            daily_start_equity REAL NOT NULL,
            current_day TEXT NOT NULL,
            losing_streak INTEGER DEFAULT 0,
            cooldown_until_ts INTEGER DEFAULT 0,
            is_halted INTEGER DEFAULT 0,
            halt_reason TEXT DEFAULT ''
        );
        """)

        # Initialize risk_state if not present
        row = conn.execute("SELECT id FROM risk_state WHERE id = 1").fetchone()
        if not row:
            now_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            conn.execute("""
            INSERT INTO risk_state (id, equity, peak_equity, daily_start_equity, current_day, losing_streak, cooldown_until_ts, is_halted, halt_reason)
            VALUES (1, 10000.0, 10000.0, 10000.0, ?, 0, 0, 0, '')
            """, (now_day,))

    conn.close()

# Helper queries
def insert_signal(signal: Dict[str, Any]) -> int:
    conn = get_connection()
    with conn:
        cursor = conn.execute("""
        INSERT INTO signals (
            timestamp, datetime_utc, strategy, direction, action,
            entry_price, stop_loss, take_profit, risk_reward,
            estimated_fees_bps, estimated_slippage_bps, net_reward_bps,
            reasons, invalidation_risks, market_regime, status, candle_timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal["timestamp"],
            signal["datetime_utc"],
            signal["strategy"],
            signal["direction"],
            signal["action"],
            signal.get("entry_price"),
            signal.get("stop_loss"),
            signal.get("take_profit"),
            signal.get("risk_reward"),
            signal.get("estimated_fees_bps"),
            signal.get("estimated_slippage_bps"),
            signal.get("net_reward_bps"),
            json.dumps(signal.get("reasons", [])),
            json.dumps(signal.get("invalidation_risks", [])),
            signal.get("market_regime", "RANGING"),
            signal.get("status", "ACTIVE"),
            signal.get("candle_timestamp")
        ))
        sig_id = cursor.lastrowid
    conn.close()
    return sig_id

def get_recent_signals(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
    SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"]) if d["reasons"] else []
        d["invalidation_risks"] = json.loads(d["invalidation_risks"]) if d["invalidation_risks"] else []
        result.append(d)
    return result

def insert_alert(alert_type: str, message: str, severity: str = "INFO"):
    conn = get_connection()
    now_ts = int(time.time())
    now_utc = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("""
        INSERT INTO alerts (timestamp, datetime_utc, type, message, severity)
        VALUES (?, ?, ?, ?, ?)
        """, (now_ts, now_utc, alert_type, message, severity))
    conn.close()

def get_recent_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
    SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_risk_state() -> Dict[str, Any]:
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
        conn.close()
        if row:
            return dict(row)
    except sqlite3.OperationalError:
        init_db()
        try:
            conn = get_connection()
            row = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception:
            pass
    return {
        "equity": 10000.0,
        "peak_equity": 10000.0,
        "daily_start_equity": 10000.0,
        "current_day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "losing_streak": 0,
        "cooldown_until_ts": 0,
        "is_halted": 0,
        "halt_reason": ""
    }

def update_risk_state(equity: float, losing_streak: int, cooldown_until_ts: int, is_halted: int, halt_reason: str):
    conn = get_connection()
    now_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with conn:
        curr = conn.execute("SELECT * FROM risk_state WHERE id = 1").fetchone()
        peak = max(curr["peak_equity"] if curr else equity, equity)
        daily_start = curr["daily_start_equity"] if curr and curr["current_day"] == now_day else equity
        conn.execute("""
        UPDATE risk_state SET
            equity = ?,
            peak_equity = ?,
            daily_start_equity = ?,
            current_day = ?,
            losing_streak = ?,
            cooldown_until_ts = ?,
            is_halted = ?,
            halt_reason = ?
        WHERE id = 1
        """, (equity, peak, daily_start, now_day, losing_streak, cooldown_until_ts, is_halted, halt_reason))
    conn.close()

# Auto-initialize database on import
try:
    init_db()
except Exception:
    pass

