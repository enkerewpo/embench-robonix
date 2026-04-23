"""eb_observe — read-only scene inspection for the planner (no env step)."""
from __future__ import annotations

import os

from embench_robonix.env_client import EnvClient  # type: ignore

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError as e:
    raise SystemExit(f"mcp package not installed: {e}") from None


_SOCKET = os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock")
_env = EnvClient(_SOCKET)
_mcp = FastMCP("eb_observe")


@_mcp.tool()
def describe_scene() -> dict:
    """Return the current scene snapshot — receptacles, pickables, agent state.

    Free call: does NOT advance the episode. Use at task start + after major
    state changes (e.g. after opening a container).
    """
    return _env.call("describe_scene", {})


if __name__ == "__main__":
    _mcp.run()
