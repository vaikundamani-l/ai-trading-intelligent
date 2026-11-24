import logging
import math
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config import settings
from app.timeframes import timeframe_seconds
from app.strategies.engine_safety import completed_history, executable_quote
from app.database import get_risk_state, insert_alert, insert_signal
from app.strategies.alpha1_orderflow import alpha1_strategy
from app.strategies.alpha2_volatility import alpha2_strategy
from app.strategies.alpha3_basis import alpha3_strategy
from app.strategies.alpha4_dislocation import alpha4_dislocation, Alpha4RDislocationProtection
from app.strategies.alpha5_sbr5 import sbr5_strategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / enums
# (str-mixin enums compare equal to their plain string values; decisions always
#  store `.value`, so downstream JSON / DB code keeps seeing plain strings.)
# ---------------------------------------------------------------------------
class Action(str, Enum):
    WAIT = "WAIT / NO TRADE"
    HALT_DATA = "HALTED / DATA UNSAFE"
    HALT_RISK = "HALTED / RISK LIMIT"


class Status(str, Enum):
    INITIALIZING = "INITIALIZING"
    DATA_UNAVAILABLE = "NO TRADE — DATA UNAVAILABLE"
    DATA_STALE = "NO TRADE — DATA STALE"
    EXCHANGE_DEGRADED = "EXCHANGE DEGRADED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DISLOCATED = "HALTED"
    RISK_HALTED = "RISK HALTED"
    COOLDOWN = "COOLDOWN"
    WAIT = "WAIT"
    INVALID_SETUP = "INVALID_SETUP"
    FILTERED_BY_FEES = "FILTERED_BY_FEES"
    ACTIVE_SETUP = "ACTIVE_SETUP"
    ENGINE_ERROR = "ENGINE_ERROR"


class Regime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"
    DISCONNECTED = "DISCONNECTED"
    DEGRADED = "DEGRADED"
    DISLOCATED = "DISLOCATED"


def _val(x: Any) -> Any:
    """Return the plain value of an Enum member, or the object unchanged."""
    return x.value if isinstance(x, Enum) else x


def _cfg(name: str, default: Any) -> Any:
    """Read an optional setting with a safe default."""
    return getattr(settings, name, default)


class SignalDecisionEngine:
    """
    Deterministic, fail-closed decision pipeline. Steps run in this order and
    the first gate that trips returns immediately:

      1.  Connection status / data freshness gate
      2.  Exchange status gate
      3.  Market regime detection (+ insufficient-data gate)
      4.  Alpha-4R market dislocation filter
      5.  Risk governor (account halt)
      6.  Losing-streak cooldown
      7.  Primary SBR-5 evaluation
      8.  Research telemetry (alpha 1/2/3) -- isolated, can never block a signal
      9.  Setup completeness validation
      10. Net-edge (fees + slippage) gate
      11. Signal / alert persistence, once per completed candle
    """

    REQUIRED_OHLC = {"high", "low", "close"}
    MIN_REGIME_BARS = 20
    REGIME_WINDOW = 25
    ER_LOOKBACK = 15      # bars (15 deltas) for the Kaufman efficiency ratio
    ATR_PERIOD = 14
    REQUIRED_SETUP_FIELDS = (
        "action",
        "direction",
        "entry_price",
        "stop_loss",
        "take_profit",
        "candle_timestamp",
    )

    def __init__(self, resolution: str = "5m", persist: bool = True) -> None:
        self.resolution = resolution
        self.bar_seconds = timeframe_seconds(resolution)
        self.persist = persist
        self.dislocation = alpha4_dislocation if resolution == "5m" else Alpha4RDislocationProtection()
        if resolution != "5m":
            self.dislocation.cooldown_duration_sec = 2 * self.bar_seconds
        self.last_decision: Dict[str, Any] = self._build(
            Action.WAIT,
            "SBR-5",
            Status.INITIALIZING,
            ["Awaiting initial market data feed"],
            [],
        )
        # Candle timestamp of the last signal that was successfully persisted.
        self.last_signaled_candle_ts: Optional[int] = None

        self._risk_cache: Optional[Dict[str, Any]] = None
        self._risk_cache_at: float = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _stamp() -> Dict[str, Any]:
        return {
            "timestamp": int(time.time()),
            "datetime_utc": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _build(
        cls,
        action: Any,
        strategy: str,
        status: Any,
        reasons: List[str],
        risks: List[str],
        regime: Any = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Build a non-trade decision (halt / wait / filtered)."""
        decision: Dict[str, Any] = {
            "action": _val(action),
            "direction": 0,
            "strategy": strategy,
            "status": _val(status),
            "reasons": list(reasons),
            "invalidation_risks": list(risks),
            **cls._stamp(),
        }
        if regime is not None:
            decision["market_regime"] = _val(regime)
        decision.update(extra)
        return decision

    def _get_risk_state(self) -> Dict[str, Any]:
        """Risk state with a short TTL cache to avoid a DB hit on every tick.

        Exceptions from the DB propagate (fail closed -> ENGINE_ERROR halt).
        Set RISK_STATE_CACHE_TTL_SEC = 0 to disable caching.
        """
        ttl = float(_cfg("RISK_STATE_CACHE_TTL_SEC", 2.0))
        now = time.monotonic()
        if self._risk_cache is not None and (now - self._risk_cache_at) < ttl:
            return self._risk_cache
        state = get_risk_state() or {}
        self._risk_cache = state
        self._risk_cache_at = now
        return state

    @staticmethod
    def _safe_telemetry(name: str, fn, *args) -> Dict[str, Any]:
        """Run a research-only alpha; its failure must never affect trading."""
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Research telemetry '%s' failed; continuing", name)
            return {"error": True, "detail": str(exc)}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def evaluate(self, df_5m: pd.DataFrame, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run the pipeline. Never raises; any unexpected error becomes a halt."""
        try:
            # Shallow copy so we never mutate the caller's dict.
            decision = self._evaluate(df_5m, dict(market_state or {}))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled error in SignalDecisionEngine.evaluate")
            decision = self._build(
                Action.HALT_DATA,
                "SYSTEM SAFETY GATE",
                Status.ENGINE_ERROR,
                [f"Decision pipeline exception: {exc}"],
                ["Unhandled runtime error in signal evaluation"],
                Regime.UNKNOWN,
            )
        decision.update(resolution=self.resolution, bar_seconds=self.bar_seconds,
                        max_hold_bars=settings.SBR5_MAX_HOLD_BARS,
                        max_hold_seconds=settings.SBR5_MAX_HOLD_BARS * self.bar_seconds)
        from app.suggestion_quality import assess_setup
        decision["quality"] = assess_setup(decision, market_state or {}, df_5m)
        self.last_decision = decision
        return decision

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    def _evaluate(self, df_5m: pd.DataFrame, state: Dict[str, Any]) -> Dict[str, Any]:
        symbol = state.get("symbol", "BTCUSD")
        conn_status = state.get("connection_status", "DISCONNECTED")
        data_age = state.get("data_age_sec")

        # Step 1: connection status / data freshness
        if conn_status != "LIVE":
            age_txt = f"{data_age}s" if data_age is not None else "unknown"
            return self._build(
                Action.HALT_DATA,
                "SYSTEM SAFETY GATE",
                Status.DATA_UNAVAILABLE,
                [
                    f"Exchange connection status is {conn_status} (data age: {age_txt})",
                    "Live signals are strictly blocked when real exchange data is delayed or disconnected",
                ],
                ["Stale market data execution risk"],
                Regime.DISCONNECTED,
            )

        # Optional hard freshness limit (opt-in: set MAX_DATA_AGE_SEC in settings)
        max_age = _cfg("MAX_DATA_AGE_SEC", None)
        if max_age is not None and data_age is not None and float(data_age) > float(max_age):
            return self._build(
                Action.HALT_DATA,
                "SYSTEM SAFETY GATE",
                Status.DATA_STALE,
                [f"Market data age {data_age}s exceeds limit of {max_age}s"],
                ["Stale market data execution risk"],
                Regime.DISCONNECTED,
            )

        # Step 2: exchange status
        exchange_status = state.get("exchange_status")
        if exchange_status != "operational":
            return self._build(
                Action.HALT_DATA,
                "SYSTEM SAFETY GATE",
                Status.EXCHANGE_DEGRADED,
                [f"Delta Exchange reporting status: {exchange_status}"],
                ["Exchange matching engine degraded"],
                Regime.DEGRADED,
            )

        # Executable quotes and history must be trustworthy before any alpha.
        try:
            if 'best_bid' not in state or 'best_ask' not in state:
                raise ValueError('Missing executable bid/ask')
            bid, ask = executable_quote(state, 0)
            quote_spread = (ask - bid) / ((ask + bid) / 2) * 10000
            reported_spread = float(state.get('spread_bps', quote_spread))
            if not math.isfinite(reported_spread) or reported_spread < 0:
                raise ValueError('Invalid quoted spread')
            if max(quote_spread, reported_spread) > settings.MAX_SIGNAL_SPREAD_BPS:
                raise ValueError(f'Spread exceeds {settings.MAX_SIGNAL_SPREAD_BPS:g} bps signal limit')
            if df_5m is not None and not df_5m.empty:
                df_5m = completed_history(df_5m, self.bar_seconds, time.time())
                if not df_5m.empty and time.time() - float(df_5m.iloc[-1]['time']) > 2 * self.bar_seconds:
                    raise ValueError(f'Stale completed {self.resolution} candle history')
        except (ValueError, TypeError) as exc:
            return self._build(Action.HALT_DATA, 'EXECUTION DATA GATE', 'INVALID_EXECUTION_DATA',
                               [str(exc)], ['Invalid quotes, spread or candle history'], Regime.UNKNOWN)

        # Step 3: regime detection (fails closed to UNKNOWN on bad / short data)
        regime = self._detect_regime(df_5m)
        if regime is Regime.UNKNOWN:
            return self._build(
                Action.WAIT,
                "SYSTEM SAFETY GATE",
                Status.INSUFFICIENT_DATA,
                [
                    f"Fewer than {self.MIN_REGIME_BARS} valid {self.resolution} bars "
                    "(or missing/non-numeric OHLC data); regime cannot be classified"
                ],
                ["Indicators unreliable on insufficient history"],
                Regime.UNKNOWN,
            )
        state["market_regime"] = regime.value  # visible to downstream strategies

        # Step 4: Alpha-4R market dislocation protection
        is_safe, dislocation_msg, _details = self.dislocation.evaluate(df_5m, state)
        if not is_safe:
            return self._build(
                Action.HALT_DATA,
                "ALPHA-4R DISLOCATION FILTER",
                Status.DISLOCATED,
                [dislocation_msg],
                ["Severe market dislocation shock"],
                Regime.DISLOCATED,
            )

        # Step 5: risk governor
        risk_state = self._get_risk_state()
        if risk_state.get("is_halted"):
            return self._build(
                Action.HALT_RISK,
                "RISK GOVERNOR",
                Status.RISK_HALTED,
                [f"Risk limit triggered: {risk_state.get('halt_reason')}"],
                ["Account drawdown limit enforcement"],
                regime,
            )

        # Step 6: losing-streak cooldown
        now_ts = int(time.time())
        cooldown_until_ts = risk_state.get("cooldown_until_ts", 0) or 0
        if now_ts < cooldown_until_ts:
            return self._build(
                Action.WAIT,
                "RISK COOLDOWN",
                Status.COOLDOWN,
                [f"In losing streak cooldown: {int(cooldown_until_ts - now_ts)}s remaining"],
                ["Consecutive losses protection"],
                regime,
            )

        # Step 7: Multi-Strategy Quantum Evaluation Engine
        # 7a. Alpha-2: High-momentum Volatility Compression Breakout (catches explosive expansions)
        alpha2_res = self._safe_telemetry("alpha2", alpha2_strategy.evaluate, df_5m, state, self.resolution)
        if not isinstance(alpha2_res, dict):
            alpha2_res = {}

        # 7b. Alpha-5: Momentum Continuation & SBR-5 Sweep & Reclaim
        sbr5_res = (sbr5_strategy.evaluate(df_5m, state) if self.resolution == "5m"
                    else sbr5_strategy.evaluate(df_5m, state, resolution=self.resolution)) or {}

        # Strategy Selection:
        # Volatility Breakout takes priority for explosive expansion events;
        # otherwise Momentum Trend & SBR-5 liquidity setups
        chosen_res = None
        if settings.ENABLE_RESEARCH_ALPHA2_SIGNALS and not settings.SCALP5_BIG_MOVE_ONLY and alpha2_res.get("is_setup"):
            chosen_res = alpha2_res
        elif sbr5_res.get("is_setup"):
            chosen_res = sbr5_res
        else:
            chosen_res = sbr5_res  # default WAIT decision

        # Step 8: Telemetry, Order-Flow & Statistical AI Confluence
        alpha1_res = self._safe_telemetry("alpha1", alpha1_strategy.evaluate, state)
        telemetry = {
            "alpha1_orderflow": alpha1_res,
            "alpha2_breakout": alpha2_res,
            "alpha3_basis": self._safe_telemetry("alpha3", alpha3_strategy.evaluate, state),
        }

        # Order-flow confirmation check: warn if order flow strongly opposes the setup
        if chosen_res.get("is_setup") and isinstance(alpha1_res, dict) and not alpha1_res.get("error"):
            ofi_score = alpha1_res.get("metrics", {}).get("composite_score", 0.0)
            if chosen_res.get("direction") == 1 and ofi_score < -0.45:
                chosen_res.setdefault("invalidation_risks", []).append("Adverse order flow: aggressive seller volume tape")
            elif chosen_res.get("direction") == -1 and ofi_score > 0.45:
                chosen_res.setdefault("invalidation_risks", []).append("Adverse order flow: aggressive buyer volume tape")

        strategy_name = chosen_res.get("strategy", "SBR-5 SWEEP & RECLAIM")

        # No setup -> WAIT
        if not chosen_res.get("is_setup"):
            return self._build(
                Action.WAIT,
                f"BIG MOVE ONLY · {self.resolution}" if settings.SCALP5_BIG_MOVE_ONLY else strategy_name,
                Status.WAIT,
                chosen_res.get("reasons", ["No valid setup detected on completed candle"]),
                chosen_res.get("invalidation_risks", []),
                regime,
                research_telemetry=telemetry,
            )

        expires = chosen_res.get("valid_until_ts")
        if expires is not None and time.time() >= float(expires):
            return self._build(
                Action.WAIT, strategy_name, "EXPIRED_SETUP",
                [f"The completed {self.resolution} setup entry window expired; wait for a new setup"],
                ["Late entry after signal expiry"], regime,
            )

        # Step 9: setup completeness validation
        missing = [f for f in self.REQUIRED_SETUP_FIELDS if chosen_res.get(f) in (None, "")]
        if not chosen_res.get("direction") and "direction" not in missing:
            missing.append("direction")  # direction 0 is not a tradable setup
        if missing:
            logger.error("Strategy flagged a setup but it is incomplete; missing/invalid: %s", missing)
            return self._build(
                Action.WAIT,
                strategy_name,
                Status.INVALID_SETUP,
                [f"Setup flagged but incomplete; missing/invalid fields: {', '.join(missing)}"],
                ["Malformed strategy output"],
                regime,
                research_telemetry=telemetry,
            )

        # Step 10: net-edge gate (fees + slippage already netted by the strategy)
        try:
            net_reward_bps = float(chosen_res.get("net_reward_bps", 0.0) or 0.0)
        except (TypeError, ValueError):
            net_reward_bps = 0.0
        if not math.isfinite(net_reward_bps):
            net_reward_bps = 0.0

        min_edge_bps = float(_cfg("MIN_NET_EDGE_BPS", 1.0))
        if net_reward_bps <= 0 or net_reward_bps < min_edge_bps:
            return self._build(
                Action.WAIT,
                strategy_name,
                Status.FILTERED_BY_FEES,
                [
                    f"Setup rejected: net reward after fees/slippage is {net_reward_bps:.2f} bps "
                    f"(minimum required: {min_edge_bps:.2f} bps)"
                ]
                + list(chosen_res.get("reasons", [])),
                ["Fee and slippage drag exceeds target edge"],
                regime,
                research_telemetry=telemetry,
            )

        decision: Dict[str, Any] = {
            "action": chosen_res["action"],
            "direction": chosen_res["direction"],
            "strategy": strategy_name,
            "entry_price": chosen_res["entry_price"],
            "stop_loss": chosen_res["stop_loss"],
            "take_profit": chosen_res["take_profit"],
            "risk_reward": chosen_res.get("risk_reward"),
            "gross_reward_bps": chosen_res.get("gross_reward_bps"),
            "estimated_fees_bps": chosen_res.get("estimated_fees_bps", 0.0),
            "estimated_slippage_bps": chosen_res.get("estimated_slippage_bps", 0.0),
            "net_reward_bps": net_reward_bps,
            "candle_timestamp": chosen_res["candle_timestamp"],
            "valid_until_ts": chosen_res.get("valid_until_ts"),
            "reasons": chosen_res.get("reasons", []),
            "invalidation_risks": chosen_res.get("invalidation_risks", []),
            "market_regime": regime.value,
            "status": Status.ACTIVE_SETUP.value,
            **self._stamp(),
            "research_telemetry": telemetry,
        }

        # Step 11: persistence (never allowed to turn a valid decision into a halt)
        if self.persist:
            self._persist_signal(decision, symbol)
        return decision

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist_signal(self, decision: Dict[str, Any], symbol: str) -> None:
        """Record signal + alert once per completed candle.

        The dedup marker is only advanced after insert_signal succeeds, so a
        transient DB failure is retried on the next evaluation. Alert failures
        are isolated so they can't cause a duplicate signal insert.
        """
        candle_ts = decision.get("candle_timestamp")
        if candle_ts is None or candle_ts == self.last_signaled_candle_ts:
            return

        try:
            decision["id"] = insert_signal(decision)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist signal for candle %s; will retry", candle_ts)
            return

        self.last_signaled_candle_ts = candle_ts

        try:
            insert_alert(
                "SIGNAL",
                f"New {decision['action']} setup on {symbol} via {decision['strategy']} "
                f"@ ${decision['entry_price']}",
                "INFO",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Signal persisted but alert insert failed for candle %s", candle_ts)

    # ------------------------------------------------------------------
    # Regime detection
    # ------------------------------------------------------------------
    def _detect_regime(self, df_5m: Optional[pd.DataFrame]) -> Regime:
        """Classify the market as TRENDING, RANGING or VOLATILE.

        Returns UNKNOWN (not RANGING) when data is missing, too short or
        non-numeric, so callers can fail closed.

        Tunable via settings (optional):
          REGIME_VOLATILE_ATR_PCT   default 0.0025  (14-bar ATR as fraction of price)
          REGIME_TREND_EFFICIENCY   default 0.45    (Kaufman efficiency ratio)
        Calibrate both against your own 5m history for the instrument.
        """
        if (
            df_5m is None
            or len(df_5m) < self.MIN_REGIME_BARS
            or not self.REQUIRED_OHLC.issubset(df_5m.columns)
        ):
            return Regime.UNKNOWN

        d = df_5m.tail(self.REGIME_WINDOW)
        high = pd.to_numeric(d["high"], errors="coerce")
        low = pd.to_numeric(d["low"], errors="coerce")
        close = pd.to_numeric(d["close"], errors="coerce")
        if high.isna().any() or low.isna().any() or close.isna().any():
            return Regime.UNKNOWN

        # Kaufman Efficiency Ratio: |C_t - C_{t-15}| / sum(|dC|) over 15 deltas
        window = close.tail(self.ER_LOOKBACK + 1)
        path = window.diff().abs().sum()
        efficiency = abs(window.iloc[-1] - window.iloc[0]) / path if path > 0 else 0.0

        # 14-period ATR as a fraction of price
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(self.ATR_PERIOD).mean().iloc[-1]
        last_close = close.iloc[-1]
        if pd.isna(atr) or last_close <= 0:
            return Regime.UNKNOWN
        atr_pct = atr / last_close

        volatile_thr = float(_cfg("REGIME_VOLATILE_ATR_PCT", 0.0025))
        trend_thr = float(_cfg("REGIME_TREND_EFFICIENCY", 0.45))

        if atr_pct > volatile_thr:
            return Regime.VOLATILE
        if efficiency > trend_thr:
            return Regime.TRENDING
        return Regime.RANGING


decision_engine = SignalDecisionEngine()
