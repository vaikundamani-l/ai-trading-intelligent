import os
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class Settings:
    # Delta Exchange India Configurations
    DELTA_REST_URL: str = os.getenv("DELTA_REST_URL", "https://api.india.delta.exchange")
    DELTA_WS_URL: str = os.getenv("DELTA_WS_URL", "wss://public-socket.india.delta.exchange")
    FALLBACK_DELTA_WS_URL: str = "wss://socket.india.delta.exchange"
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSD")
    
    # Contract Specifications (Delta India)
    CONTRACT_SIZE: float = 0.001       # 0.001 BTC per lot
    TICK_SIZE: float = 0.5             # $0.50 tick size
    FEE_MAKER_BPS: float = 2.0         # 0.02%
    FEE_TAKER_BPS: float = 5.0         # 0.05%
    GST_MULTIPLIER: float = 1.18       # 18% GST on exchange fees
    DEFAULT_SLIP_PER_LEG_BPS: float = 1.0  # 1 bp per leg modeled execution slippage
    
    # Derived two-leg taker roundtrip cost in bps: (2 * 5.0 * 1.18) + (2 * 1.0) = 11.8 + 2.0 = 13.8 bps
    ROUNDTRIP_TAKER_FEE_BPS: float = 2 * 5.0 * 1.18  # 11.80 bps
    
    # Funding Schedule
    # 00:00, 08:00, 16:00 UTC = 05:30, 13:30, 21:30 IST
    FUNDING_INTERVAL_SEC: int = 8 * 3600
    FUNDING_BUFFER_SEC: int = 120      # 2 minutes safety buffer around funding snapshot
    
    # SBR-5 Baseline Parameters (from Stage 3 research)
    SBR5_LOOKBACK: int = 24            # previous 2 hours at 5m
    SBR5_VOL_LOOKBACK: int = 24
    SBR5_ATR_LOOKBACK: int = 14
    SBR5_VOLUME_MULTIPLIER: float = 1.25
    SBR5_SWEEP_ATR: float = 0.12
    SBR5_RECLAIM_ATR: float = 0.10
    SBR5_MAX_RECLAIM_ATR: float = 1.20
    SBR5_STOP_BUFFER_ATR: float = 0.10
    SBR5_TARGET_R: float = 1.80
    SBR5_MAX_HOLD_BARS: int = 5        # 25 minutes
    SBR5_MIN_STOP_FRACTION: float = 0.0015  # 15 bps minimum
    SBR5_MAX_STOP_FRACTION: float = 0.0080  # 80 bps maximum
    
    # Risk Limits (Capital Preservation Architecture)
    MAX_RISK_FRACTION: float = 0.0025          # 0.25% equity per trade
    MAX_NOTIONAL_EQUITY_MULTIPLE: float = 2.0  # 2.0x equity max modeled exposure
    DAILY_LOSS_LIMIT_FRACTION: float = 0.01    # 1.0% daily loss limit
    PEAK_DRAWDOWN_KILL_FRACTION: float = 0.05  # 5.0% peak drawdown hard halt
    MAX_CONSECUTIVE_LOSSES: int = 4            # 4 consecutive losses trigger cooldown
    COOLDOWN_BARS: int = 12                    # 12 bars (60 min) cooldown
    
    # Database and Server
    DB_PATH: str = os.getenv("DB_PATH", "btc_quantum.db")
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    ALLOWED_ORIGINS: tuple = tuple(origin.strip() for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if origin.strip())
    ALLOWED_HOSTS: tuple = tuple(h.strip() for h in os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1,backend,testserver"
    ).split(",") if h.strip())
    
    # Production Security & Auth
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    API_AUTH_TOKEN: Optional[str] = os.getenv("API_AUTH_TOKEN", "").strip() or None
    ENABLE_SECURITY_HEADERS: bool = os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() in ("true", "1", "yes")

    # Data Freshness Thresholds
    STALE_DATA_TIMEOUT_SEC: float = 5.0     # Mark DELAYED if no data for 5s
    DISCONNECT_TIMEOUT_SEC: float = 15.0    # Mark DISCONNECTED if no data for 15s

settings = Settings()
