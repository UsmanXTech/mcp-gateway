"""Demo echo MCP server — the gateway's first upstream (Phase 0).

One tool: ``echo(text)`` returns ``"echo: <text>"``. Proves the proxy +
auth path end to end before any real upstream is wired in.

Run:  python -m upstream.echo_server   (listens on 127.0.0.1:8765)
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-demo")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back."""
    return f"echo: {text}"


if __name__ == "__main__":
    mcp.settings.port = 8765
    mcp.run(transport="streamable-http")
