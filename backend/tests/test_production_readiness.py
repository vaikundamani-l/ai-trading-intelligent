import time
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
from app.main import app
from app.config import settings

def test_liveness_probe():
    client = TestClient(app)
    res = client.get("/health/live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "alive"
    assert "timestamp" in data

def test_readiness_probe():
    client = TestClient(app)
    res = client.get("/health/ready")
    # In test environment, DB is initialized and ready
    assert res.status_code in (200, 503)
    data = res.json()
    assert data["database"] == "connected"
    assert "timestamp" in data

def test_system_status_endpoint():
    client = TestClient(app)
    res = client.get("/health/status")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "btc-quantum-backend"
    assert "uptime_sec" in data
    assert "memory_rss_mb" in data
    assert "active_ws_clients" in data
    assert "market" in data

def test_security_headers_present():
    client = TestClient(app)
    res = client.get("/health", headers={"origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert res.headers.get("x-xss-protection") == "1; mode=block"

def test_custom_allowed_hosts(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ("production.example.com", "localhost"))
    # Re-instantiate test client
    client = TestClient(app)
    # Production host allowed
    assert client.get("/health", headers={"host": "production.example.com"}).status_code == 200
    # Still rejects foreign untrusted host
    assert client.get("/health", headers={"host": "malicious.hacker.com"}).status_code == 400

def test_api_auth_token_protection(monkeypatch):
    monkeypatch.setattr(settings, "API_AUTH_TOKEN", "prod_secret_token_12345")
    client = TestClient(app)

    # 1. Mutating request without token is rejected
    res = client.post("/api/engine/toggle")
    assert res.status_code == 401
    assert "Unauthorized" in res.json()["detail"]

    # 2. Mutating request with invalid token is rejected
    res = client.post("/api/engine/toggle", headers={"X-API-Key": "wrong_token"})
    assert res.status_code == 401

    # 3. Mutating request with valid X-API-Key is authorized
    res = client.post("/api/engine/toggle", headers={"X-API-Key": "prod_secret_token_12345"})
    assert res.status_code == 200

    # 4. Mutating request with valid Bearer token is authorized
    res = client.post("/api/engine/toggle", headers={"Authorization": "Bearer prod_secret_token_12345"})
    assert res.status_code == 200

    # 5. Read-only GET requests remain accessible
    assert client.get("/health").status_code == 200

def test_api_auth_token_websocket(monkeypatch):
    monkeypatch.setattr(settings, "API_AUTH_TOKEN", "prod_secret_token_12345")
    client = TestClient(app)

    # WebSocket without token is rejected
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 1008

    # WebSocket with valid token query parameter connects
    with client.websocket_connect("/ws?token=prod_secret_token_12345") as ws:
        init_data = ws.receive_json()
        assert init_data["type"] == "INITIAL_STATE"
