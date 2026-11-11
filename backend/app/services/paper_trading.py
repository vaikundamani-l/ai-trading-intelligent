import math
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pandas as pd

from app.config import settings
from app.database import get_connection, insert_alert, get_risk_state, update_risk_state

logger = logging.getLogger("PaperTrading")

class PaperTradingEngine:
    def __init__(self):
        self.initial_equity = 10000.0
        self.equity = 10000.0
        self.peak_equity = 10000.0
        self.losing_streak = 0
        self.cooldown_until_ts = 0
        self.is_halted = False
        self.halt_reason = ""
        self._load_state()

    def _load_state(self):
        state = get_risk_state()
        self.equity = state.get("equity", 10000.0)
        self.peak_equity = state.get("peak_equity", 10000.0)
        self.losing_streak = state.get("losing_streak", 0)
        self.cooldown_until_ts = state.get("cooldown_until_ts", 0)
        self.is_halted = bool(state.get("is_halted", 0))
        self.halt_reason = state.get("halt_reason", "")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Calculates win rate, profit factor, max drawdown, and open position."""
        self._load_state()
        conn = get_connection()
        
        # Open positions
        open_pos = conn.execute("""
        SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        # Closed positions
        closed_rows = conn.execute("""
        SELECT * FROM paper_trades WHERE status = 'CLOSED' ORDER BY id ASC
        """).fetchall()
        conn.close()

        closed_trades = [dict(r) for r in closed_rows]
        total_closed = len(closed_trades)
        
        wins = [t for t in closed_trades if (t.get("pnl_usd") or 0) > 0]
        losses = [t for t in closed_trades if (t.get("pnl_usd") or 0) < 0]
        
        win_rate = (len(wins) / total_closed * 100.0) if total_closed > 0 else 0.0
        total_win_usd = sum(t.get("pnl_usd", 0) for t in wins)
        total_loss_usd = abs(sum(t.get("pnl_usd", 0) for t in losses))
        profit_factor = (total_win_usd / total_loss_usd) if total_loss_usd > 0 else (None if len(wins) == 0 else 999.0)
        
        avg_expectancy_bps = (sum(t.get("net_bps", 0) for t in closed_trades) / total_closed) if total_closed > 0 else 0.0
        
        # Drawdown calculation
        equity_curve = [self.initial_equity] + [t.get("equity_after", self.initial_equity) for t in closed_trades]
        peak = self.initial_equity
        max_dd_pct = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak if peak > 0 else 0.0
            if dd < max_dd_pct:
                max_dd_pct = dd

        return {
            "initial_equity": self.initial_equity,
            "current_equity": round(self.equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "total_return_pct": round((self.equity / self.initial_equity - 1.0) * 100.0, 2),
            "max_drawdown_pct": round(max_dd_pct * 100.0, 2),
            "total_trades": total_closed,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "average_net_expectancy_bps": round(avg_expectancy_bps, 1),
            "losing_streak": self.losing_streak,
            "is_cooldown_active": (time.time() < self.cooldown_until_ts),
            "cooldown_remaining_sec": max(0, int(self.cooldown_until_ts - time.time())),
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
            "open_position": dict(open_pos) if open_pos else None,
            "closed_trades": closed_trades[-20:]  # Last 20 closed
        }

    def execute_signal(self, signal: Dict[str, Any], market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Simulates opening a paper position based on a validated SBR-5 signal."""
        self._load_state()
        if market_state.get("connection_status") != "LIVE" or not market_state.get("is_data_safe", False):
            return None
        from app.strategies.alpha5_sbr5 import funding_in_window
        if funding_in_window(int(time.time())):
            return None
        if min(market_state.get("best_bid", 0), market_state.get("best_ask", 0)) <= 0:
            return None
        # Risk checks
        if self.is_halted:
            logger.warning(f"Paper trade rejected: Account is halted ({self.halt_reason})")
            return None
            
        if time.time() < self.cooldown_until_ts:
            logger.warning("Paper trade rejected: In risk cooldown")
            return None

        # Check no simultaneous positions
        conn = get_connection()
        conn.execute("BEGIN IMMEDIATE")
        open_pos = conn.execute("SELECT id FROM paper_trades WHERE status = 'OPEN'").fetchone()
        if open_pos:
            conn.close()
            logger.warning("Paper trade rejected: Position already open (no simultaneous positions allowed)")
            return None

        if signal.get("id") and conn.execute("SELECT id FROM paper_trades WHERE signal_id = ?", (signal["id"],)).fetchone():
            conn.close()
            return None
        direction = signal.get("direction", 0)
        if direction not in (1, -1):
            conn.close()
            return None

        # Compute realistic entry price with slippage
        slip = settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0
        best_ask = market_state.get("best_ask", signal.get("entry_price", 80000.0))
        best_bid = market_state.get("best_bid", signal.get("entry_price", 80000.0))
        entry_px = (best_ask if direction == 1 else best_bid) * (1 + direction * slip)

        stop_px = float(signal.get("stop_loss", 0.0))
        target_px = float(signal.get("take_profit", 0.0))
        
        if not all(math.isfinite(v) and v > 0 for v in (entry_px, stop_px, target_px)) or direction * (target_px - entry_px) <= 0:
            conn.close()
            return None
        risk_move = direction * (entry_px - stop_px)
        if risk_move <= 0:
            conn.close()
            return None

        # Sizing: max 0.25% equity risk, max 2.0x notional multiple
        # Include taker fee (11.8 bps) and slippage (2 bps)
        two_leg_fee_frac = 2 * (settings.FEE_TAKER_BPS / 10000.0) * settings.GST_MULTIPLIER
        risk_per_notional = (risk_move / entry_px) + two_leg_fee_frac + (2 * slip)
        
        max_risk_usd = self.equity * settings.MAX_RISK_FRACTION
        notional_usd = min(max_risk_usd / risk_per_notional, self.equity * settings.MAX_NOTIONAL_EQUITY_MULTIPLE)
        
        # Round down to 0.001 BTC lot size
        lot_notional = entry_px * settings.CONTRACT_SIZE
        contracts = math.floor(notional_usd / lot_notional)
        actual_notional_usd = contracts * lot_notional
        
        if contracts <= 0 or actual_notional_usd <= 0:
            conn.close()
            logger.warning("Paper trade rejected: Position size too small for minimum 1 lot (0.001 BTC)")
            return None

        now_utc = datetime.now(timezone.utc).isoformat()
        
        with conn:
            cursor = conn.execute("""
            INSERT INTO paper_trades (
                signal_id, created_at, entry_time, symbol, direction,
                entry_price, stop_loss, take_profit, notional_usd, contracts, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """, (
                signal.get("id"), now_utc, now_utc, settings.SYMBOL, direction,
                entry_px, stop_px, target_px, actual_notional_usd, contracts
            ))
            trade_id = cursor.lastrowid
        conn.close()

        logger.info(f"Opened Paper Trade #{trade_id}: {'BUY' if direction == 1 else 'SELL'} {contracts} lots @ ${entry_px:.1f}")
        insert_alert("PAPER_TRADE", f"Simulated {'BUY' if direction == 1 else 'SELL'} {contracts} contracts @ ${entry_px:.1f} (Stop: ${stop_px:.1f}, TP: ${target_px:.1f})", "INFO")
        
        return {
            "id": trade_id,
            "direction": direction,
            "entry_price": round(entry_px, 1),
            "stop_loss": round(stop_px, 1),
            "take_profit": round(target_px, 1),
            "contracts": contracts,
            "notional_usd": round(actual_notional_usd, 2)
        }

    def update_open_positions(self, market_state: Dict[str, Any], current_bar: Optional[Dict[str, float]] = None):
        """Monitors open position against incoming ticks or completed bar extremes.
        Resolves ambiguous bars touching both stop and target against us (hits stop first).
        """
        if market_state.get("connection_status") != "LIVE" or market_state.get("last_price", 0) <= 0:
            return
        self._load_state()
        conn = get_connection()
        pos_row = conn.execute("SELECT * FROM paper_trades WHERE status = 'OPEN'").fetchone()
        if not pos_row:
            conn.close()
            return

        pos = dict(pos_row)
        direction = pos["direction"]
        entry = pos["entry_price"]
        stop = pos["stop_loss"]
        target = pos["take_profit"]
        notional = pos["notional_usd"]
        trade_id = pos["id"]

        slip = settings.DEFAULT_SLIP_PER_LEG_BPS / 10000.0
        exit_px = None
        exit_reason = None

        cur_high = current_bar.get("high") if current_bar else market_state.get("last_price", 0.0)
        cur_low = current_bar.get("low") if current_bar else market_state.get("last_price", 0.0)
        cur_open = current_bar.get("open") if current_bar else market_state.get("last_price", 0.0)

        # Conservative fill checks
        # 1. Stop hit or ambiguous both hit
        stop_hit = (direction == 1 and cur_low <= stop) or (direction == -1 and cur_high >= stop)
        target_hit = (direction == 1 and cur_high >= target) or (direction == -1 and cur_low <= target)

        if stop_hit:
            base = min(stop, cur_open) if direction == 1 else max(stop, cur_open)
            exit_px = base * (1 - direction * slip)
            exit_reason = "stop_or_ambiguous_both_hit"
        elif target_hit:
            exit_px = target * (1 - direction * slip)
            exit_reason = "target"

        if exit_px is None and time.time() - datetime.fromisoformat(pos["entry_time"]).timestamp() >= settings.SBR5_MAX_HOLD_BARS * 300:
            exit_px = cur_open * (1 - direction * slip)
            exit_reason = "time_limit_25m"

        if exit_px is not None:
            now_utc = datetime.now(timezone.utc).isoformat()
            gross_fraction = direction * (exit_px - entry) / entry
            # Exact per-leg taker fee with 18% GST: (fee_entry + fee_exit * P_x / P_e)
            fee_taker = settings.FEE_TAKER_BPS / 10000.0 * settings.GST_MULTIPLIER
            fee_fraction = fee_taker * (1.0 + (exit_px / entry))
            net_fraction = gross_fraction - fee_fraction
            pnl_usd = notional * net_fraction

            new_equity = self.equity + pnl_usd
            self.equity = new_equity
            self.peak_equity = max(self.peak_equity, new_equity)

            # Update streak and risk limits
            if pnl_usd <= 0:
                self.losing_streak += 1
                if self.losing_streak >= settings.MAX_CONSECUTIVE_LOSSES:
                    self.cooldown_until_ts = int(time.time()) + (settings.COOLDOWN_BARS * 300)
                    insert_alert("RISK", f"{settings.MAX_CONSECUTIVE_LOSSES} consecutive losses hit. 60-minute cooldown activated.", "WARNING")
            else:
                self.losing_streak = 0

            # Check daily realized loss against the current UTC day baseline.
            state = get_risk_state()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            baseline = state["daily_start_equity"] if state["current_day"] == today else new_equity - pnl_usd
            if new_equity <= baseline * (1 - settings.DAILY_LOSS_LIMIT_FRACTION):
                self.is_halted = True
                self.halt_reason = "Daily loss limit reached"

            # Check hard drawdown halt (5% peak drawdown)
            if self.equity <= self.peak_equity * (1 - settings.PEAK_DRAWDOWN_KILL_FRACTION):
                self.is_halted = True
                self.halt_reason = "Peak Drawdown Kill-Switch (5% Drawdown Limit Reached)"
                insert_alert("RISK", "Hard halt: 5% peak-to-trough drawdown reached. Trading halted.", "CRITICAL")

            # Update DB
            with conn:
                conn.execute("""
                UPDATE paper_trades SET
                    exit_time = ?,
                    exit_price = ?,
                    gross_bps = ?,
                    fees_bps = ?,
                    net_bps = ?,
                    pnl_usd = ?,
                    equity_after = ?,
                    status = 'CLOSED',
                    exit_reason = ?
                WHERE id = ?
                """, (
                    now_utc, exit_px, gross_fraction * 10000.0,
                    fee_fraction * 10000.0, net_fraction * 10000.0,
                    pnl_usd, new_equity, exit_reason, trade_id
                ))
            conn.close()

            update_risk_state(
                equity=self.equity,
                losing_streak=self.losing_streak,
                cooldown_until_ts=self.cooldown_until_ts,
                is_halted=1 if self.is_halted else 0,
                halt_reason=self.halt_reason
            )

            logger.info(f"Closed Paper Trade #{trade_id} via {exit_reason} @ ${exit_px:.1f}. PnL: ${pnl_usd:.2f} ({net_fraction*10000.0:+.1f} bps)")
            insert_alert("PAPER_TRADE", f"Position closed #{trade_id} ({exit_reason}): PnL ${pnl_usd:+.2f} ({net_fraction*10000.0:+.1f} bps)", "INFO")
        else:
            conn.close()

paper_trading_service = PaperTradingEngine()
