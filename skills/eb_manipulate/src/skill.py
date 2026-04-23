"""eb_manipulate — MCP tools for pick / place / open / close on EB-Habitat."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from embench_robonix.env_client import EnvClient  # type: ignore
from embench_robonix.atlas_register import (  # type: ignore
    pick_port, register, start_heartbeat,
)

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError as e:
    raise SystemExit(f"mcp package not installed: {e}") from None


_SOCKET = os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock")
_env = EnvClient(_SOCKET)

_SKILL_DIR = Path(__file__).resolve().parent.parent
_CAPABILITY_MD = _SKILL_DIR / "CAPABILITY.md"

_mcp = FastMCP("eb_manipulate")


@_mcp.tool()
def pick(obj: str) -> dict:
    """Pick up a named object from the currently-active receptacle.

    Requires prior ``navigate(receptacle)`` so the robot is next to where
    the object lives. Returns {"success", "holding", "step"}.
    """
    return _env.call("pick", {"obj": obj})


@_mcp.tool()
def place(obj: str, receptacle: str) -> dict:
    """Place a currently-held object on/in a receptacle the agent stands at."""
    return _env.call("place", {"obj": obj, "receptacle": receptacle})


@_mcp.tool()
def open_(receptacle: str) -> dict:
    """Open a door/drawer/fridge the agent has navigated to."""
    return _env.call("open", {"receptacle": receptacle})


@_mcp.tool()
def close_(receptacle: str) -> dict:
    """Inverse of `open_`."""
    return _env.call("close", {"receptacle": receptacle})


def _serve_mcp(port: int) -> None:
    _mcp.run(transport="streamable-http", host="127.0.0.1", port=port)


def main() -> None:
    mcp_port = pick_port()
    threading.Thread(target=_serve_mcp, args=(mcp_port,), daemon=True).start()
    time.sleep(0.5)

    stub = register(
        node_id="com.embench_robonix.skl.eb_manipulate",
        capability_namespace="embench/skill",
        mcp_port=mcp_port,
        skills=[
            {"name": "pick", "description": "Pick up a named object from the active receptacle (EB-Habitat).", "path": str(_CAPABILITY_MD)},
            {"name": "place", "description": "Place held object on/in a reachable receptacle (EB-Habitat).", "path": str(_CAPABILITY_MD)},
            {"name": "open_", "description": "Open a reachable door/drawer/fridge (EB-Habitat).", "path": str(_CAPABILITY_MD)},
            {"name": "close_", "description": "Close a reachable articulated receptacle (EB-Habitat).", "path": str(_CAPABILITY_MD)},
        ],
        contract_id="embench/skill/manipulate/tools",
    )
    start_heartbeat(stub, "com.embench_robonix.skl.eb_manipulate")

    print(f"[eb_manipulate] MCP :{mcp_port} registered", file=sys.stderr, flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
