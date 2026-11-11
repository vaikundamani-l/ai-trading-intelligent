import asyncio
import json
import logging
import os
import resource
import time
from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from app.config import settings
from app.database import init_db, get_connection
from app.services.delta_market_data import market_data_service
from app.decision_engine import decision_engine
from app.ml.prediction_engine import prediction_engine
from app.services.paper_trading import paper_trading_service
from app.api.endpoints import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BTCQuantumMain")

APP_START_TIME = time.time()

# Connected WebSocket clients manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead_connections = []
        for connection in self.active_connections:
            try:
                await asyncio.wait_for(connection.send_text(payload), timeout=2)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

prediction_snapshot = {"status": "UNAVAILABLE", "horizons": {}, "message": "Models are warming up"}

async def prediction_loop():
    global prediction_snapshot
    while True:
        try:
            state = market_data_service.get_market_state()
            if state.get("connection_status") == "LIVE":
                prediction_snapshot = await asyncio.to_thread(prediction_engine.generate_predictions, market_data_service.candles_5m.copy(), state.get("last_price", 0))
            else:
                prediction_snapshot = {"status": "UNAVAILABLE", "horizons": {}, "message": "Live market data unavailable"}
        except Exception:
            logger.exception("Prediction refresh failed")
            prediction_snapshot = {"status": "UNAVAILABLE", "horizons": {}}
        await asyncio.sleep(10)

# Background broadcast loop
async def broadcast_loop():
    executed_candle = None
    logger.info("Real-time WebSocket broadcaster loop started.")
    while True:
        try:
            # Get latest market snapshot
            m_state = market_data_service.get_market_state()
            df_5m = market_data_service.candles_5m
            decision = decision_engine.evaluate(df_5m, m_state)
            candle = decision.get("candle_timestamp")
            if decision.get("quality", {}).get("eligible_for_auto_paper") and candle != executed_candle:
                if paper_trading_service.execute_signal(decision, m_state):
                    executed_candle = candle
            paper_trading_service.update_open_positions(m_state)
            portfolio = paper_trading_service.get_portfolio_summary()
            preds = prediction_snapshot

            payload = {
                "type": "REALTIME_TICK",
                "market": m_state,
                "signal": decision,
                "predictions": preds,
                "portfolio": portfolio
            }
            await manager.broadcast(payload)
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")
        await asyncio.sleep(0.3)  # 300ms broadcast interval

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting BTC Quantum Intelligence Backend...")
    # 1. Initialize SQLite Database
    init_db()

    # 2. Start Delta Exchange India Market Data Service
    loop = asyncio.get_running_loop()
    market_data_service.start(loop=loop)

    # 3. Warm up Statistical AI Models in background thread
    async def warmup_ml():
        try:
            df_5m = market_data_service.candles_5m
            if df_5m.empty or len(df_5m) < 150:
                df_5m = await asyncio.to_thread(market_data_service.fetch_candles_rest, "5m", count=300)
            if not df_5m.empty and len(df_5m) >= 150:
                await asyncio.to_thread(prediction_engine.train_models, df_5m)
        except Exception as e:
            logger.warning(f"Initial ML training error: {e}")

    ml_task = asyncio.create_task(warmup_ml())

    # 4. Start Real-time Broadcaster task
    b_task = asyncio.create_task(broadcast_loop())
    p_task = asyncio.create_task(prediction_loop())

    yield

    # Teardown
    logger.info("Shutting down backend...")
    ml_task.cancel()
    b_task.cancel()
    p_task.cancel()
    await asyncio.gather(ml_task, b_task, p_task, return_exceptions=True)
    market_data_service.stop()

app = FastAPI(
    title="BTC Quantum Intelligence API",
    description="Real-Time Bitcoin Research & Quantitative Signal Engine for Delta Exchange India",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dynamic Trusted Host Middleware (configurable via settings.ALLOWED_HOSTS)
class DynamicTrustedHostMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            host_header = headers.get(b"host", b"").decode("latin1")
            host = host_header.split(":")[0] if host_header else ""
            allowed = settings.ALLOWED_HOSTS
            if "*" not in allowed and host not in allowed:
                response = Response("Invalid host header", status_code=400, media_type="text/plain")
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

app.add_middleware(DynamicTrustedHostMiddleware)

@app.middleware("http")
async def security_middleware(request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in settings.ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)

    # Optional API Token check for mutating trading actions
    if settings.API_AUTH_TOKEN and request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Exempt public safe endpoints if needed, but trading mutations require auth
        auth_header = request.headers.get("X-API-Key") or request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            auth_header = auth_header[7:].strip()
        if auth_header != settings.API_AUTH_TOKEN:
            return JSONResponse({"detail": "Unauthorized: Invalid or missing API token"}, status_code=401)

    response = await call_next(request)

    # Production HTTP Security Headers
    if settings.ENABLE_SECURITY_HEADERS:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"

    return response

# Include REST API Endpoints
app.include_router(api_router)

@app.get("/health")
def health_check():
    m_state = market_data_service.get_market_state()
    return {
        "status": "healthy",
        "market_status": m_state.get("connection_status"),
        "last_price": m_state.get("last_price"),
        "symbol": settings.SYMBOL
    }

@app.get("/health/live")
def liveness_probe():
    """Kubernetes/Container liveness probe to verify process is alive."""
    return {"status": "alive", "timestamp": int(time.time())}

@app.get("/health/ready")
def readiness_probe(response: Response):
    """Kubernetes/Container readiness probe checking DB and market connectivity."""
    db_ok = False
    try:
        conn = get_connection()
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"Readiness probe DB check failed: {e}")

    market_status = market_data_service.connection_status
    is_ready = db_ok and market_data_service._running

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "not_ready",
        "database": "connected" if db_ok else "error",
        "market_service": "running" if market_data_service._running else "stopped",
        "feed_status": market_status,
        "timestamp": int(time.time())
    }

@app.get("/health/status")
def system_status():
    """Detailed institutional production metrics and status."""
    m_state = market_data_service.get_market_state()
    portfolio = paper_trading_service.get_portfolio_summary()
    mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    
    return {
        "service": "btc-quantum-backend",
        "version": "1.0.0",
        "uptime_sec": round(time.time() - APP_START_TIME, 1),
        "environment": settings.ENVIRONMENT,
        "memory_rss_mb": round(mem_kb / 1024.0, 2),
        "active_ws_clients": len(manager.active_connections),
        "market": {
            "symbol": settings.SYMBOL,
            "feed_status": m_state.get("connection_status"),
            "last_price": m_state.get("last_price"),
            "data_age_sec": m_state.get("data_age_sec"),
            "is_data_safe": m_state.get("is_data_safe")
        },
        "portfolio": {
            "current_equity": portfolio.get("current_equity"),
            "open_position": portfolio.get("open_position") is not None,
            "closed_trades_count": len(portfolio.get("closed_trades", []))
        }
    }

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    # Optional Token check
    if settings.API_AUTH_TOKEN:
        token = websocket.query_params.get("token") or websocket.headers.get("x-api-key")
        if token != settings.API_AUTH_TOKEN:
            await websocket.close(code=1008)
            return

    await manager.connect(websocket)
    # Immediately send current state
    try:
        m_state = market_data_service.get_market_state()
        df_5m = market_data_service.candles_5m
        decision = decision_engine.evaluate(df_5m, m_state)
        preds = prediction_snapshot
        portfolio = paper_trading_service.get_portfolio_summary()

        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "market": m_state,
            "signal": decision,
            "predictions": preds,
            "portfolio": portfolio
        }))
        while True:
            # Keep receiving client pings or commands
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("action") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
