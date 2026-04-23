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
    _mcp.settings.host = "127.0.0.1"
    _mcp.settings.port = port
    _mcp.run(transport="streamable-http")


def main() -> None:
    mcp_port = pick_port()
    threading.Thread(target=_serve_mcp, args=(mcp_port,), daemon=True).start()
    time.sleep(0.5)

    stub = register(
        node_id="com.embench_robonix.skl.eb_manipulate",
        capability_namespace="robonix/skill/embench",
        mcp_port=mcp_port,
        skills=[
            {
                "name": "pick",
                "description": "Pick up an object from the receptacle the agent is next to (EB-Habitat). Must navigate first. `obj` from describe_scene().valid_targets.pick.",
                "path": str(_CAPABILITY_MD),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "obj": {"type": "string", "description": "Object phrase from describe_scene().valid_targets.pick (e.g. 'pear', 'apple')."},
                    },
                    "required": ["obj"],
                },
            },
            {
                "name": "place",
                "description": "Place currently-held object on/in a reachable receptacle (EB-Habitat). Must hold object first and stand at target receptacle.",
                "path": str(_CAPABILITY_MD),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "obj": {"type": "string", "description": "Object being placed (currently held)."},
                        "receptacle": {"type": "string", "description": "Receptacle phrase from describe_scene().valid_targets.place."},
                    },
                    "required": ["obj", "receptacle"],
                },
            },
            {
                "name": "open_",
                "description": "Open a reachable door/drawer/fridge (EB-Habitat). Must navigate to it first.",
                "path": str(_CAPABILITY_MD),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "receptacle": {"type": "string", "description": "Receptacle phrase from describe_scene().valid_targets.open."},
                    },
                    "required": ["receptacle"],
                },
            },
            {
                "name": "close_",
                "description": "Close a reachable articulated receptacle (EB-Habitat). Must navigate to it first.",
                "path": str(_CAPABILITY_MD),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "receptacle": {"type": "string", "description": "Receptacle phrase from describe_scene().valid_targets.close."},
                    },
                    "required": ["receptacle"],
                },
            },
        ],
        contract_id="robonix/skill/embench/manipulate/tools",
        mcp_instance=_mcp,
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
