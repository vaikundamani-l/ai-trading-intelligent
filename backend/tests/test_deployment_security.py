from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
from app.main import app


def test_foreign_browser_cannot_mutate_ledger():
    client = TestClient(app)
    response = client.post('/api/paper-trade/execute', headers={'origin': 'https://untrusted.example'})
    assert response.status_code == 403


def test_rebinding_host_is_rejected():
    client = TestClient(app)
    assert client.get('/health', headers={'host': 'untrusted.example'}).status_code == 400


def test_local_browser_allowed():
    client = TestClient(app)
    response = client.get('/health', headers={'origin': 'http://localhost:3000'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'


def test_foreign_websocket_rejected():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect('/ws', headers={'origin': 'https://untrusted.example'}):
            pass
    assert exc.value.code == 1008
