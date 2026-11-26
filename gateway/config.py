"""Runtime settings, read from the environment (sane dev defaults)."""
import os

UPSTREAM_URL = os.environ.get("GATEWAY_UPSTREAM_URL", "http://127.0.0.1:8765/mcp")
AUDIT_DB = os.environ.get("GATEWAY_AUDIT_DB", "data/audit.db")
HOST = os.environ.get("GATEWAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
