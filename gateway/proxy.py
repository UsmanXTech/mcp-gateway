"""JSON-RPC dispatch to the upstream MCP server via the MCP SDK client.

Phase 0: one upstream, one short-lived client session per request. A
persistent session pool and multi-upstream routing land in Phase 1.
"""
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SUPPORTED_METHODS = ("initialize", "tools/list", "tools/call")


def _http_client():
    """httpx client for upstream calls.

    ``trust_env=False`` on purpose: the sandbox sets NO_PROXY entries such
    as ``[::1]`` that httpx cannot parse as URL patterns, and upstreams are
    direct connections that must never go through an egress proxy anyway.
    """
    return httpx.AsyncClient(timeout=httpx.Timeout(30, read=300), trust_env=False)


async def dispatch(upstream_url, payload):
    """Run one JSON-RPC request against the upstream. Returns the result."""
    method = payload.get("method")
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"unsupported method: {method}")
    params = payload.get("params") or {}

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp-gateway", "version": "0.1.0"},
        }

    async with _http_client() as client:
        async with streamable_http_client(
            upstream_url, http_client=client
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if method == "tools/list":
                    tools = await session.list_tools()
                    return {"tools": [t.model_dump() for t in tools.tools]}
                result = await session.call_tool(
                    params["name"], params.get("arguments", {})
                )
                return result.model_dump()
