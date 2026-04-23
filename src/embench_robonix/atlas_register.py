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
) -> "object":
    """Register this process with atlas. Returns the gRPC stub for heartbeat use.

    ``skills`` is a list of {"name", "description", "path"} dicts — one per
    MCP tool exposed by this process. ``path`` is the filesystem path to
    CAPABILITY.md so Pilot can read the description in-depth when planning.
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

    stub.DeclareInterface(pb.DeclareInterfaceRequest(
        node_id=node_id,
        name="mcp_tools",
        supported_transports=["mcp"],
        metadata_json=json.dumps({"mcp_http_port": mcp_port}),
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
