"""eb_navigate — MCP skill wrapping EB-Habitat `navigation` action.

Talks to the shared env adapter over a local socket; one env lives in
`embench_robonix.env_adapter`, all skill processes are clients.
"""
from __future__ import annotations

import os
import sys

# Wired to the shared env adapter at EMBENCH_ENV_SOCKET (default: /tmp/embench.sock)
from embench_robonix.env_client import EnvClient  # type: ignore

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError as e:
    raise SystemExit(f"mcp package not installed: {e}") from None


_SOCKET = os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock")
_env = EnvClient(_SOCKET)
_mcp = FastMCP("eb_navigate")


@_mcp.tool()
def navigate(target: str) -> dict:
    """Navigate to the named receptacle in the current EB-Habitat scene.

    target: receptacle name as returned by `describe_scene()` under the
    `receptacles` key. EB-Habitat does not permit navigating to arbitrary
    pickable items — use a receptacle.

    Returns {"success": bool, "agent_near": str|None, "step": int}.
    """
    return _env.call("navigate", {"target": target})


if __name__ == "__main__":
    _mcp.run()
