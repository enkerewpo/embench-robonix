"""eb_observe — read-only scene inspection (no env step consumed)."""
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

_mcp = FastMCP("eb_observe")


@_mcp.tool()
def describe_scene() -> dict:
    """Return the current scene snapshot (receptacles, pickables, agent state).
    Free call: does NOT advance the episode.
    """
    return _env.call("describe_scene", {})


def _serve_mcp(port: int) -> None:
    _mcp.run(transport="streamable-http", host="127.0.0.1", port=port)


def main() -> None:
    mcp_port = pick_port()
    threading.Thread(target=_serve_mcp, args=(mcp_port,), daemon=True).start()
    time.sleep(0.5)

    stub = register(
        node_id="com.embench_robonix.skl.eb_observe",
        capability_namespace="robonix/skill/embench",
        mcp_port=mcp_port,
        skills=[{
            "name": "describe_scene",
            "description": "Return a scene snapshot. Free call — no env step consumed.",
            "path": str(_CAPABILITY_MD),
            "metadata": {"disable_model_invocation": False, "free_call": True},
        }],
        contract_id="robonix/skill/embench/observe/tools",
    )
    start_heartbeat(stub, "com.embench_robonix.skl.eb_observe")

    print(f"[eb_observe] MCP :{mcp_port} registered", file=sys.stderr, flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
