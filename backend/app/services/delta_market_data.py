import asyncio
import json
import logging
import math
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
import requests
import websockets
import pandas as pd
import numpy as np

from app.config import settings

logger = logging.getLogger("DeltaMarketData")
logging.basicConfig(level=logging.INFO)

class DeltaMarketDataService:
    def __init__(self):
        self.symbol = settings.SYMBOL
        self.rest_url = settings.DELTA_REST_URL
        self.ws_url = settings.DELTA_WS_URL
        self.lock = threading.Lock()
        
        # State
        self.is_connected = False
        self.connection_status = "DISCONNECTED"  # LIVE, DELAYED, DISCONNECTED
        self.last_update_ts = 0.0
        self.exchange_ts = 0.0
        self.exchange_status = "operational"
        
        # Real-time Market Data
        self.last_price = 0.0
        self.mark_price = 0.0
        self.spot_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.bid_size = 0.0
        self.ask_size = 0.0
        self.spread = 0.0
        self.spread_bps = 0.0
        self.volume_24h = 0.0
        self.turnover_24h = 0.0
        self.change_24h_pct = 0.0
        self.funding_rate = 0.0
        self.next_funding_ts = 0
        self.open_interest = 0.0
        self.oi_contracts = 0
        
        # Order Book (Top 15 Levels)
        self.bids: List[Dict[str, float]] = []  # [{"price": float, "size": float, "depth": float}]
        self.asks: List[Dict[str, float]] = []  # [{"price": float, "size": float, "depth": float}]
        self.ob_seq = 0
        
        # Microstructure Metrics
        self.order_flow_imbalance = 0.0
        self.trade_flow_imbalance = 0.0
        self.aggressive_buy_vol = 0.0
        self.aggressive_sell_vol = 0.0
        self.weighted_mid = 0.0
        self.micro_price_dev = 0.0
        self.recent_trades: List[Dict[str, Any]] = []
        
        # Historical & Live Candles (5m primary, plus 1m, 15m, 1h, etc.)
        self.candles_5m: pd.DataFrame = pd.DataFrame()
        self.candles_1m: pd.DataFrame = pd.DataFrame()
        self.candles_cache: Dict[str, pd.DataFrame] = {}
        
        # Listeners for completed candles & signals
        self.on_candle_close_callbacks: List[Callable[[pd.DataFrame], None]] = []
        self.on_state_update_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        self.ws_task = None
        self.polling_task = None
        self._running = False

    def get_market_state(self) -> Dict[str, Any]:
        """Thread-safe snapshot of market data and health."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update_ts if self.last_update_ts > 0 else 999.0
            
            # Determine Freshness Status
            if elapsed < settings.STALE_DATA_TIMEOUT_SEC and self.last_price > 0:
                status = "LIVE"
            elif elapsed < settings.DISCONNECT_TIMEOUT_SEC and self.last_price > 0:
                status = "DELAYED"
            else:
                status = "DISCONNECTED"
                
            self.connection_status = status
            
            # Compute funding countdown
            next_funding_sec = self._calc_next_funding_sec()
            
            # Basis calculation
            basis_val = 0.0
            basis_bps = 0.0
            if self.spot_price > 0 and self.last_price > 0:
                basis_val = self.last_price - self.spot_price
                basis_bps = (basis_val / self.spot_price) * 10000.0
                
            return {
                "symbol": self.symbol,
                "connection_status": self.connection_status,
                "exchange_status": self.exchange_status,
                "last_update_ts": self.last_update_ts,
                "data_age_sec": round(elapsed, 2),
                "last_price": self.last_price,
                "mark_price": self.mark_price,
                "spot_price": self.spot_price,
                "best_bid": self.best_bid,
                "best_ask": self.best_ask,
                "bid_size": self.bid_size,
                "ask_size": self.ask_size,
                "spread": self.spread,
                "spread_bps": self.spread_bps,
                "volume_24h": self.volume_24h,
                "turnover_24h": self.turnover_24h,
                "change_24h_pct": self.change_24h_pct,
                "funding_rate": self.funding_rate,
                "funding_rate_pct": round(self.funding_rate * 100, 4),
                "next_funding_countdown_sec": next_funding_sec,
                "open_interest": self.open_interest,
                "oi_contracts": self.oi_contracts,
                "bids": self.bids[:15],
                "asks": self.asks[:15],
                "order_flow_imbalance": round(self.order_flow_imbalance, 4),
                "trade_flow_imbalance": round(self.trade_flow_imbalance, 4),
                "aggressive_buy_vol": round(self.aggressive_buy_vol, 2),
                "aggressive_sell_vol": round(self.aggressive_sell_vol, 2),
                "weighted_mid": round(self.weighted_mid, 2),
                "micro_price_dev": round(self.micro_price_dev, 2),
                "basis_usd": round(basis_val, 2),
                "basis_bps": round(basis_bps, 2),
                "recent_trades": self.recent_trades[:20],
                "is_data_safe": (status == "LIVE" and self.exchange_status == "operational" and self.spread_bps < 15.0)
            }

    def _calc_next_funding_sec(self) -> int:
        now_utc = int(time.time())
        funding_sec = settings.FUNDING_INTERVAL_SEC
        next_snapshot = ((now_utc - 1) // funding_sec + 1) * funding_sec
        return max(0, next_snapshot - now_utc)

    # -------------------------------------------------------------
    # REST API Fetchers
    # -------------------------------------------------------------
    def fetch_ticker_rest(self) -> bool:
        """Fetch latest ticker from Delta Exchange India."""
        endpoint = f"{self.rest_url}/v2/tickers/{self.symbol}"
        try:
            res = requests.get(endpoint, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    r = data["result"]
                    with self.lock:
                        self.last_price = float(r.get("close", self.last_price))
                        self.mark_price = float(r.get("mark_price", self.last_price))
                        self.spot_price = float(r.get("spot_price", self.last_price))
                        quotes = r.get("quotes", {})
                        if quotes:
                            self.best_bid = float(quotes.get("best_bid", self.last_price))
                            self.best_ask = float(quotes.get("best_ask", self.last_price))
                            self.bid_size = float(quotes.get("bid_size", 0))
                            self.ask_size = float(quotes.get("ask_size", 0))
                            self.spread = max(0.0, self.best_ask - self.best_bid)
                            if self.last_price > 0:
                                self.spread_bps = (self.spread / self.last_price) * 10000.0
                        self.volume_24h = float(r.get("volume", 0))
                        self.turnover_24h = float(r.get("turnover_usd", 0))
                        self.change_24h_pct = float(r.get("ltp_change_24h", 0))
                        self.funding_rate = float(r.get("funding_rate", 0))
                        self.open_interest = float(r.get("oi", 0))
                        self.oi_contracts = int(r.get("oi_contracts", 0))
                        self.exchange_status = r.get("product_trading_status", "operational")
                        self.last_update_ts = time.time()
                    return True
        except Exception as e:
            logger.warning(f"Failed to fetch ticker via REST: {e}")
        return False

    def fetch_orderbook_rest(self) -> bool:
        """Fetch top 15 bids and asks via REST."""
        endpoint = f"{self.rest_url}/v2/l2orderbook/{self.symbol}"
        try:
            res = requests.get(endpoint, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    result = data.get("result", {})
                    buys = result.get("buy", [])
                    sells = result.get("sell", [])
                    with self.lock:
                        self.bids = [
                            {"price": float(b["price"]), "size": float(b["size"]), "depth": float(b.get("depth", b["size"]))}
                            for b in buys[:15]
                        ]
                        self.asks = [
                            {"price": float(a["price"]), "size": float(a["size"]), "depth": float(a.get("depth", a["size"]))}
                            for a in sells[:15]
                        ]
                        if self.bids and self.asks:
                            self.best_bid = self.bids[0]["price"]
                            self.best_ask = self.asks[0]["price"]
                            self.spread = max(0.0, self.best_ask - self.best_bid)
                            if self.last_price > 0:
                                self.spread_bps = (self.spread / self.last_price) * 10000.0
                            self._update_microstructure()
                        self.last_update_ts = time.time()
                    return True
        except Exception as e:
            logger.warning(f"Failed to fetch orderbook via REST: {e}")
        return False

    def fetch_candles_rest(self, resolution: str = "5m", count: int = 300) -> pd.DataFrame:
        """Fetch genuine historical candles from Delta India API."""
        sec_map = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400
        }
        bar_sec = sec_map.get(resolution, 300)
        end_ts = int(time.time())
        start_ts = end_ts - (count * bar_sec)
        
        endpoint = f"{self.rest_url}/v2/history/candles"
        try:
            res = requests.get(endpoint, params={
                "resolution": resolution,
                "symbol": self.symbol,
                "start": start_ts,
                "end": end_ts
            }, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    rows = data.get("result", [])
                    if rows:
                        df = pd.DataFrame(rows)
                        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
                        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
                        for col in ["open", "high", "low", "close", "volume"]:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                        df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
                        
                        with self.lock:
                            if resolution == "5m":
                                self.candles_5m = df
                            elif resolution == "1m":
                                self.candles_1m = df
                            self.candles_cache[resolution] = df
                        return df
        except Exception as e:
            logger.warning(f"Failed to fetch {resolution} candles via REST: {e}")
        return pd.DataFrame()

    def _update_microstructure(self):
        """Compute Order Flow Imbalance (OFI) and Weighted Micro-Price."""
        if not self.bids or not self.asks:
            return
        
        bid_vol = sum(b["size"] for b in self.bids[:10])
        ask_vol = sum(a["size"] for a in self.asks[:10])
        total_vol = bid_vol + ask_vol
        
        # Order Book Imbalance (OBI) [-1.0, 1.0]
        if total_vol > 0:
            self.order_flow_imbalance = (bid_vol - ask_vol) / total_vol
        
        # Weighted Mid-Price
        top_bid_p = self.bids[0]["price"]
        top_ask_p = self.asks[0]["price"]
        top_bid_q = self.bids[0]["size"]
        top_ask_q = self.asks[0]["size"]
        
        if top_bid_q + top_ask_q > 0:
            self.weighted_mid = (top_bid_q * top_ask_p + top_ask_q * top_bid_p) / (top_bid_q + top_ask_q)
            mid = (top_bid_p + top_ask_p) / 2.0
            self.micro_price_dev = self.weighted_mid - mid
            
        # Trade Flow Imbalance (TFI) over recent trades
        if self.recent_trades:
            buy_notional = sum(t["price"] * t["size"] for t in self.recent_trades if t.get("side") == "buy")
            sell_notional = sum(t["price"] * t["size"] for t in self.recent_trades if t.get("side") == "sell")
            tot_trade = buy_notional + sell_notional
            self.aggressive_buy_vol = buy_notional
            self.aggressive_sell_vol = sell_notional
            if tot_trade > 0:
                self.trade_flow_imbalance = (buy_notional - sell_notional) / tot_trade

    # -------------------------------------------------------------
    # WebSocket Streaming Client
    # -------------------------------------------------------------
    async def _ws_client_loop(self):
        """Persistent WebSocket loop with automatic reconnection and heartbeat."""
        retry_delay = 1.0
        while self._running:
            try:
                logger.info(f"Connecting to Delta Exchange WebSocket: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as ws:
                    self.is_connected = True
                    retry_delay = 1.0
                    logger.info("WebSocket connected. Subscribing to BTCUSD channels...")
                    
                    sub_msg = {
                        "type": "subscribe",
                        "payload": {
                            "channels": [
                                {"name": "ticker", "symbols": [self.symbol]},
                                {"name": "ob_l2", "symbols": [self.symbol]},
                                {"name": "trades", "symbols": [self.symbol]},
                                {"name": "mark_price", "symbols": [self.symbol]},
                                {"name": "candlestick_5m", "symbols": [self.symbol]},
                                {"name": "candlestick_1m", "symbols": [self.symbol]}
                            ]
                        }
                    }
                    await ws.send(json.dumps(sub_msg))
                    
                    while self._running:
                        msg_str = await ws.recv()
                        data = json.loads(msg_str)
                        self._handle_ws_message(data)
                        
            except asyncio.CancelledError:
                logger.info("WebSocket loop cancelled.")
                break
            except Exception as e:
                self.is_connected = False
                logger.warning(f"WebSocket error: {e}. Reconnecting in {retry_delay:.1f}s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 30.0)

    def _handle_ws_message(self, data: Dict[str, Any]):
        channel = data.get("channel") or data.get("type")
        now = time.time()
        
        with self.lock:
            # Freshness advances only on a parsed price update.
            
            # 1. Ticker channel
            if channel == "ticker":
                d_list = data.get("d", [])
                if d_list and isinstance(d_list, list):
                    item = d_list[0]
                    if "m" in item and item["m"] is not None:
                        self.mark_price = float(item["m"])
                    if "ohlc" in item and len(item["ohlc"]) >= 4:
                        self.last_price = float(item["ohlc"][3])
                        self.last_update_ts = now
                    if "m24hc" in item and item["m24hc"] is not None:
                        self.change_24h_pct = float(item["m24hc"])
                    if "oi" in item and len(item["oi"]) >= 1:
                        self.oi_contracts = int(item["oi"][0])

            # 2. Orderbook L2 channel
            elif channel == "ob_l2":
                buys = data.get("b", [])
                sells = data.get("a", [])
                if buys:
                    self.bids = [
                        {"price": float(b[0]), "size": float(b[1]), "depth": float(b[1])}
                        for b in buys[:15]
                    ]
                    self.best_bid = self.bids[0]["price"]
                    self.bid_size = self.bids[0]["size"]
                if sells:
                    self.asks = [
                        {"price": float(a[0]), "size": float(a[1]), "depth": float(a[1])}
                        for a in sells[:15]
                    ]
                    self.best_ask = self.asks[0]["price"]
                    self.ask_size = self.asks[0]["size"]
                    
                if self.best_bid > 0 and self.best_ask > 0:
                    self.spread = max(0.0, self.best_ask - self.best_bid)
                    if self.last_price > 0:
                        self.spread_bps = (self.spread / self.last_price) * 10000.0
                    self._update_microstructure()

            # 3. Trades channel
            elif channel == "trades":
                price = float(data.get("p", 0))
                size = float(data.get("s", 0))
                buyer_role = data.get("r", "m")  # maker/taker role
                side = "buy" if buyer_role == "t" else "sell"
                
                if price > 0:
                    self.last_price = price
                    self.last_update_ts = now
                    trade_item = {
                        "price": price,
                        "size": size,
                        "side": side,
                        "timestamp": int(data.get("t", now * 1000000) / 1000000),
                        "time_iso": datetime.now(timezone.utc).isoformat()
                    }
                    self.recent_trades.insert(0, trade_item)
                    if len(self.recent_trades) > 50:
                        self.recent_trades = self.recent_trades[:50]
                    self._update_microstructure()

            # 4. Candlestick channel (5m or 1m)
            elif channel in ("candlestick_5m", "candlestick_1m"):
                res = data.get("res", "5m")
                open_p = float(data.get("o", 0))
                high_p = float(data.get("h", 0))
                low_p = float(data.get("l", 0))
                close_p = float(data.get("c", 0))
                candle_start_us = data.get("cst", 0)
                candle_start_s = int(candle_start_us / 1000000) if candle_start_us > 1e11 else int(candle_start_us)
                
                if close_p > 0:
                    self.last_price = close_p
                    self.last_update_ts = now
                    
                # Update live bar in dataframe if exists
                target_df = self.candles_5m if res == "5m" else self.candles_1m
                if not target_df.empty and candle_start_s > 0:
                    last_idx = target_df.index[-1]
                    last_time = target_df.loc[last_idx, "time"]
                    
                    if last_time == candle_start_s:
                        # Update current in-progress bar
                        target_df.loc[last_idx, "volume"] = float(data.get("v", target_df.loc[last_idx, "volume"]))
                        target_df.loc[last_idx, ["high", "low", "close"]] = [
                            max(target_df.loc[last_idx, "high"], high_p),
                            min(target_df.loc[last_idx, "low"], low_p),
                            close_p
                        ]
                    elif candle_start_s > last_time:
                        # New bar started! The previous bar is finalized.
                        logger.info(f"New {res} candle started at {candle_start_s}. Previous bar completed.")
                        new_row = pd.DataFrame([{
                            "time": candle_start_s,
                            "open": open_p,
                            "high": high_p,
                            "low": low_p,
                            "close": close_p,
                            "volume": float(data.get("v", 10.0)),
                            "dt": pd.to_datetime(candle_start_s, unit="s", utc=True)
                        }])
                        target_df = pd.concat([target_df, new_row], ignore_index=True)
                        if res == "5m":
                            self.candles_5m = target_df
                            # Trigger completed candle callbacks
                            for cb in self.on_candle_close_callbacks:
                                try:
                                    cb(self.candles_5m)
                                except Exception as cb_err:
                                    logger.error(f"Error in candle close callback: {cb_err}")
                        else:
                            self.candles_1m = target_df

    # -------------------------------------------------------------
    # Fallback Background Polling Loop
    # -------------------------------------------------------------
    async def _polling_loop(self):
        """Ensures market data remains 100% fresh via REST even if WS drops."""
        while self._running:
            try:
                # Poll ticker every 2 seconds
                await asyncio.to_thread(self.fetch_ticker_rest)
                
                # If order book empty or stale, fetch it
                await asyncio.to_thread(self.fetch_orderbook_rest)
                    
                # Refresh 5m candles every 30 seconds
                if self.candles_5m.empty or (time.time() % 30 < 2):
                    await asyncio.to_thread(self.fetch_candles_rest, "5m", count=1000)
                    
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
            await asyncio.sleep(2.0)

    # -------------------------------------------------------------
    # Service Lifecycle
    # -------------------------------------------------------------
    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start both REST pre-fetch and background async loops."""
        self._running = True
        logger.info("Initializing Delta Market Data Service...")
        
        # Immediate initial REST fetch
        self.fetch_ticker_rest()
        self.fetch_orderbook_rest()
        self.fetch_candles_rest("5m", count=1000)
        self.fetch_candles_rest("1m", count=100)
        
        if loop is None:
            loop = asyncio.get_event_loop()
            
        self.ws_task = loop.create_task(self._ws_client_loop())
        self.polling_task = loop.create_task(self._polling_loop())
        logger.info("Delta Market Data background tasks started.")

    def stop(self):
        self._running = False
        if self.ws_task:
            self.ws_task.cancel()
        if self.polling_task:
            self.polling_task.cancel()
        logger.info("Delta Market Data service stopped.")

# Singleton instance
market_data_service = DeltaMarketDataService()
