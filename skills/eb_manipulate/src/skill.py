"""eb_manipulate — MCP tools for pick / place / open / close on EB-Habitat."""
from __future__ import annotations

import os

from embench_robonix.env_client import EnvClient  # type: ignore

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError as e:
    raise SystemExit(f"mcp package not installed: {e}") from None


_SOCKET = os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock")
_env = EnvClient(_SOCKET)
_mcp = FastMCP("eb_manipulate")


@_mcp.tool()
def pick(obj: str) -> dict:
    """Pick up a named object from the currently-active receptacle.

    Requires prior `navigate(receptacle)` so the robot is next to where the
    object lives. Returns {"success": bool, "holding": str|None, "step": int}.
    """
    return _env.call("pick", {"obj": obj})


@_mcp.tool()
def place(obj: str, receptacle: str) -> dict:
    """Place a currently-held object on/in a receptacle the agent stands at."""
    return _env.call("place", {"obj": obj, "receptacle": receptacle})


@_mcp.tool()
def open_(receptacle: str) -> dict:
    """Open a door/drawer/fridge receptacle the agent is reachable to."""
    return _env.call("open", {"receptacle": receptacle})


@_mcp.tool()
def close_(receptacle: str) -> dict:
    """Inverse of `open_`."""
    return _env.call("close", {"receptacle": receptacle})


if __name__ == "__main__":
    _mcp.run()
