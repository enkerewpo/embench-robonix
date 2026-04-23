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
    """Return the world-model snapshot for the current EB-Habitat episode.

    CALL THIS FIRST before any navigate/pick/place/open/close. The returned
    `valid_targets` dict lists the EXACT phrases each tool accepts for this
    scene; any other string will fail.

    Returns:
      instruction       natural-language task goal
      receptacles       receptacle names (navigate targets)
      pickable_objects  pickable object names (pick targets)
      valid_targets     {navigate, pick, place, open, close} → list of the
                        only accepted phrases for that action this scene
      holding           currently held object or null
      agent_near        receptacle the agent is next to or null
      step              episode step counter

    Free call — does NOT advance the episode.
    """
    return _env.call("describe_scene", {})


def _serve_mcp(port: int) -> None:
    _mcp.settings.host = "127.0.0.1"
    _mcp.settings.port = port
    _mcp.run(transport="streamable-http")


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
        mcp_instance=_mcp,
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
