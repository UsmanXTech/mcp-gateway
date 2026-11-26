# MCP Gateway + OAuth

An OAuth 2.1-secured gateway fronting multiple MCP servers — per-user scopes,
audit log, rate limits, tool routing. Python + FastAPI, MCP Python SDK, Authlib.

## Status

**Phase 0 — DONE (2026-11-26):** gateway scaffold + demo echo MCP server.
`client_credentials` token issue, Bearer + scope check on `/mcp`, JSON-RPC
proxy to the upstream echo server, SQLite audit log. Smoke tests pass.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1. Start the demo upstream (echo MCP server, port 8765)
python -m upstream.echo_server

# 2. In another shell, start the gateway (port 8000)
uvicorn gateway.app:app --host 127.0.0.1 --port 8000

# 3. Get a token (demo client — change the secret in production!)
curl -X POST http://127.0.0.1:8000/oauth/token \
  -d "grant_type=client_credentials&client_id=demo-client&client_secret=demo-secret&scope=mcp:tools"

# 4. Call a tool through the gateway
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
       "params": {"name": "echo", "arguments": {"text": "hello"}}}'
```

## Run the tests

```bash
pytest -q
```

## Architecture (Phase 0)

```
client --(OAuth2 Bearer, scope mcp:tools)--> gateway (FastAPI :8000)
        --(MCP streamable HTTP)--> echo upstream (FastMCP :8765)
        audit log --> data/audit.db (SQLite)
```

- `gateway/auth.py` — Authlib authorization server (`client_credentials`
  grant), in-memory client + opaque token store, Bearer validator.
- `gateway/proxy.py` — JSON-RPC dispatch to the upstream via the MCP SDK
  client (`tools/list`, `tools/call`, `initialize`).
- `gateway/audit.py` — SQLite audit log (who called what, when, how long).
- `upstream/echo_server.py` — demo echo MCP server, one tool: `echo(text)`.

## Roadmap

- **Phase 0** — audit + demo echo upstream first (this). ✅
- **Phase 1** — real upstream #1: chess-mcp via stdio→HTTP bridge; persistent
  upstream sessions (no per-request handshake); per-client rate limits.
- **Phase 2** — per-user scopes + JWT access tokens; authorization-code +
  PKCE flow for user login; persistent client store (SQLite → Postgres).
- **Phase 3** — tool routing across many upstreams, allow-lists per client,
  audit-log UI, Docker + deploy on Oracle VPS free tier.

## Security notes

- The default client secret (`demo-secret`) is for local dev only. Set
  `GATEWAY_CLIENT_ID` / `GATEWAY_CLIENT_SECRET` from the environment.
- Phase 0 tokens are opaque and stored in memory; a gateway restart
  invalidates them. JWT + persistent store land in Phase 2.
- Never commit real secrets: `.env` and `data/` are gitignored.
