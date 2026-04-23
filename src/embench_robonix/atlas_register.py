"""Shared atlas registration helpers for skill MCP servers.

Each skill process:
1. Starts its MCP HTTP server on a free port.
2. Calls :func:`register` to tell atlas about its node_id + mcp_port +
   list of exported tool names (sent as SkillInfo records so Pilot can
   see them when planning).
3. Leaves :func:`heartbeat_loop` running so atlas doesn't evict the node.

Wire-format stubs live in ``proto_gen/`` (run scripts/codegen.sh to populate).
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROTO_GEN = _REPO_ROOT / "proto_gen"
if _PROTO_GEN.is_dir():
    sys.path.insert(0, str(_PROTO_GEN))


def _import_proto():
    try:
        import robonix_runtime_pb2 as pb  # type: ignore
        import robonix_runtime_pb2_grpc as pb_grpc  # type: ignore
        return pb, pb_grpc
    except ImportError as e:
        raise SystemExit(
            f"robonix_runtime proto stubs missing — run scripts/codegen.sh first ({e})"
        ) from None


def pick_port() -> int:
    """Reserve an ephemeral port and release it (caller binds)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def register(
    node_id: str,
    capability_namespace: str,
    mcp_port: int,
    skills: list[dict],
    contract_id: str = "",
    mcp_instance=None,
) -> "object":
    """Register this process with atlas. Returns the gRPC stub for heartbeat use.

    ``skills`` is the planner-facing SkillInfo list (name + description +
    path to CAPABILITY.md). Separately, the interface metadata must carry
    the live MCP tool schemas so executor's ``load_mcp_tools`` can dispatch
    — it reads ``endpoint`` + ``tools[]`` out of ``metadata_json``.
    Pass ``mcp_instance`` to have this helper introspect the FastMCP server
    for its live tool list (preferred). Falls back to ``skills`` if not.
    """
    import grpc
    pb, pb_grpc = _import_proto()

    atlas_addr = os.environ.get("ROBONIX_ATLAS", "127.0.0.1:50051")
    channel = grpc.insecure_channel(atlas_addr)
    stub = pb_grpc.RobonixRuntimeStub(channel)

    skill_pbs = [
        pb.SkillInfo(
            name=s["name"],
            description=s.get("description", ""),
            path=str(s.get("path", "")),
            metadata_json=json.dumps(s.get("metadata", {})),
        )
        for s in skills
    ]

    stub.RegisterNode(pb.RegisterNodeRequest(
        node_id=node_id,
        namespace=capability_namespace,
        kind="skill",
        skills=skill_pbs,
    ))

    # Build the tool catalogue the executor expects: [{name, description,
    # input_schema}]. Use ONLY the short description + minimal schema so the
    # aggregated ListTools response stays within HTTP/2 frame size (16 KB).
    # Any longer planner-facing docs live in CAPABILITY.md (skill.path) —
    # Pilot reads those via read_file when it needs detail.
    mcp_tools: list[dict] = [{
        "name": s["name"],
        "description": (s.get("description", "") or "")[:240],
        "input_schema": s.get("input_schema",
                              {"type": "object", "properties": {},
                               "additionalProperties": True}),
    } for s in skills]

    iface_meta = {
        "endpoint": f"http://127.0.0.1:{mcp_port}/mcp",
        "tools": mcp_tools,
    }

    stub.DeclareInterface(pb.DeclareInterfaceRequest(
        node_id=node_id,
        name="mcp_tools",
        supported_transports=["mcp"],
        metadata_json=json.dumps(iface_meta),
        listen_port=mcp_port,
        contract_id=contract_id or f"{capability_namespace}/tools",
    ))
    return stub


def heartbeat_loop(stub, node_id: str, interval: float = 5.0) -> None:
    """Background thread body — call atlas.NodeHeartbeat forever."""
    pb, _ = _import_proto()
    while True:
        try:
            stub.NodeHeartbeat(pb.NodeHeartbeatRequest(node_id=node_id))
        except Exception:
            pass
        time.sleep(interval)


def start_heartbeat(stub, node_id: str) -> threading.Thread:
    t = threading.Thread(target=heartbeat_loop, args=(stub, node_id), daemon=True)
    t.start()
    return t
