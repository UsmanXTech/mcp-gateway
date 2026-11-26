"""FastAPI app: /health, /oauth/token, /mcp (Bearer + scope protected)."""
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request

from . import audit, config
from .auth import Token, build_oauth2_request, require_token, server
from .proxy import dispatch


@asynccontextmanager
async def lifespan(app):
    audit.init_db(config.AUDIT_DB)
    yield


app = FastAPI(title="mcp-gateway", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "upstream": config.UPSTREAM_URL}


@app.post("/oauth/token")
async def issue_token(request: Request):
    form = await request.form()
    oauth_req = build_oauth2_request(request, dict(form))
    return server.create_token_response(oauth_req)


@app.post("/mcp")
async def mcp_endpoint(request: Request, token: Token = Depends(require_token)):
    payload = await request.json()
    method = payload.get("method", "")
    tool = (payload.get("params") or {}).get("name")
    start = time.monotonic()
    try:
        result = await dispatch(config.UPSTREAM_URL, payload)
        status = "ok"
        body = {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}
    except ValueError as exc:
        status = "error"
        body = {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "error": {"code": -32601, "message": str(exc)},
        }
    except Exception as exc:  # noqa: BLE001 — surfaced as JSON-RPC error
        status = "error"
        body = {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "error": {"code": -32603, "message": f"upstream error: {exc}"},
        }
    audit.log(
        token.client_id,
        method,
        tool,
        status,
        int((time.monotonic() - start) * 1000),
    )
    return body
