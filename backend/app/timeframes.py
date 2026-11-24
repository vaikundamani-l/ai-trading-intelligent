TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}


def timeframe_seconds(resolution: str) -> int:
    if resolution not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {resolution}")
    return TIMEFRAME_SECONDS[resolution]
