"""eb_navigate — MCP skill wrapping EB-Habitat high-level `navigation` action.

Registers with Robonix atlas so Pilot can discover + dispatch the tool.
Talks to the shared env adapter over a UNIX socket; one EBHabEnv instance
lives there and serves all skill processes.
"""
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

_mcp = FastMCP("eb_navigate")


@_mcp.tool()
def navigate(target: str) -> dict:
    """Navigate to the named receptacle in the current EB-Habitat scene.

    ``target`` must be a receptacle name shown by ``describe_scene`` (in the
    ``receptacles`` list). EB-Habitat restricts navigation to receptacles,
    not arbitrary pickable objects.

    Returns {"success": bool, "agent_near": str|None, "step": int}.
    """
    return _env.call("navigate", {"target": target})


def _serve_mcp(port: int) -> None:
    # fastmcp defaults to stdio; switch to HTTP so atlas-registered port matches.
    _mcp.run(transport="streamable-http", host="127.0.0.1", port=port)


def main() -> None:
    mcp_port = pick_port()
    t = threading.Thread(target=_serve_mcp, args=(mcp_port,), daemon=True)
    t.start()
    # wait for server to bind
    time.sleep(0.5)

    stub = register(
        node_id="com.embench_robonix.skl.eb_navigate",
        capability_namespace="embench/skill",
        mcp_port=mcp_port,
        skills=[{
            "name": "navigate",
            "description": "Navigate to a receptacle in EB-Habitat (navigation action).",
            "path": str(_CAPABILITY_MD),
            "metadata": {"tool": "navigate", "env": "eb_habitat"},
        }],
        contract_id="embench/skill/navigate/tools",
    )
    start_heartbeat(stub, "com.embench_robonix.skl.eb_navigate")

    print(f"[eb_navigate] MCP :{mcp_port} registered", file=sys.stderr, flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
