"""Phase 0 smoke tests: token issue, auth enforcement, echo via gateway, audit."""
import os
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

os.environ["GATEWAY_UPSTREAM_URL"] = "http://127.0.0.1:8765/mcp"
os.environ["GATEWAY_AUDIT_DB"] = "/tmp/mcp-gateway-test-audit.db"
os.environ["GATEWAY_CLIENT_ID"] = "demo-client"
os.environ["GATEWAY_CLIENT_SECRET"] = "demo-secret"

if os.path.exists("/tmp/mcp-gateway-test-audit.db"):
    os.remove("/tmp/mcp-gateway-test-audit.db")

from gateway import audit  # noqa: E402
from gateway.app import app  # noqa: E402
from upstream.echo_server import mcp as echo_mcp  # noqa: E402


def _wait_for_port(host, port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"port {host}:{port} never opened")


@pytest.fixture(scope="module")
def echo_server():
    server = uvicorn.Server(
        uvicorn.Config(echo_mcp.streamable_http_app(), host="127.0.0.1", port=8765, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port("127.0.0.1", 8765)
    yield
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def client(echo_server):
    with TestClient(app) as c:
        yield c


def _get_token(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "demo-client",
            "client_secret": "demo-secret",
            "scope": "mcp:tools",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_token_wrong_secret(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "demo-client",
            "client_secret": "wrong-secret",
        },
    )
    assert r.status_code in (400, 401)


def test_mcp_requires_token(client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert r.status_code == 401


def test_tools_list(client):
    token = _get_token(client)
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert "echo" in names


def test_echo_call(client):
    token = _get_token(client)
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hello"}},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert "hello" in r.text


def test_audit_log_written(client):
    assert audit.count() >= 2
