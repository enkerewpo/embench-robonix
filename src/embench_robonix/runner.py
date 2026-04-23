"""Phase A task runner — drives EB-Habitat episodes through Robonix Pilot.

Flow per task:
1. Ask env_adapter to reset to the task's episode_id and return instruction.
2. Build a ``pilot.Task`` with ``text=instruction`` and submit via
   ``SrvPilot.Stream``. Stream back PilotEvents until a terminal one.
3. After Pilot finishes (or max turns hit), ask env_adapter for current
   ``task_success`` and step count.
4. Log per-task JSONL + aggregate summary.csv.

The Pilot process itself owns the VLM call, skill discovery via atlas,
and dispatch to Executor. We just feed it a prompt and record outcomes.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import socket
import sys
import time
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROTO_GEN = _REPO_ROOT / "proto_gen"
if _PROTO_GEN.is_dir():
    sys.path.insert(0, str(_PROTO_GEN))

log = logging.getLogger("embench.runner")


def _env_call(sock_path: str, method: str, params: dict | None = None) -> dict:
    """Talk to env_adapter's UNIX socket — newline-delimited JSON RPC."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sock_path)
    try:
        s.sendall((json.dumps({"method": method, "params": params or {}}) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(8192)
            if not chunk:
                raise RuntimeError("env_adapter closed socket")
            buf += chunk
        return json.loads(buf.split(b"\n", 1)[0].decode())
    finally:
        s.close()


def _load_tasks(cfg_path: Path) -> list[dict]:
    import yaml
    return yaml.safe_load(cfg_path.read_text())["tasks"]


def _submit_task_to_pilot(pilot_addr: str, instruction: str,
                          session_id: str, max_turns: int, timeout_s: float) -> dict:
    """Open a streaming RPC to Pilot. Collect events until terminal."""
    import grpc
    import pilot_pb2 as pilot_pb  # type: ignore
    import robonix_contracts_pb2_grpc as contracts_grpc  # type: ignore

    ch = grpc.insecure_channel(pilot_addr)
    stub = contracts_grpc.SrvPilotStub(ch)

    task = pilot_pb.Task(
        task_id=str(uuid.uuid4()),
        session_id=session_id,
        source=1,
        text=instruction,
        timestamp_ms=int(time.time() * 1000),
    )

    events: list[dict] = []
    final_text = ""
    turn_count = 0
    t0 = time.perf_counter()

    # event_kind: 1=text_chunk 2=task_graph 3=batch_result 4=status 5=final_text
    try:
        for ev in stub.Stream(task, timeout=timeout_s):
            kind = int(ev.event_kind)
            events.append({"kind": kind, "session_id": ev.session_id})
            if kind == 5:  # final_text
                final_text = ev.final_text
                events[-1]["final_text"] = final_text
            elif kind == 3:  # batch_result
                turn_count += 1
                events[-1]["batch_ok"] = not ev.batch_result.any_failed
            elif kind == 4:  # status
                events[-1]["state"] = int(ev.status.state)
                events[-1]["msg"] = ev.status.message
                # state enum: 0=unknown 1=running 2=done 3=aborted ... treat >=2 as terminal
                if int(ev.status.state) >= 2:
                    break
            if turn_count >= max_turns:
                break
    except grpc.RpcError as e:
        return {"pilot_ok": False, "error": str(e),
                "events": events, "final_text": final_text,
                "turns": turn_count, "wall_s": time.perf_counter() - t0}

    return {"pilot_ok": True, "events": events, "final_text": final_text,
            "turns": turn_count, "wall_s": time.perf_counter() - t0}


def run_one_task(task: dict, env_sock: str, pilot_addr: str,
                 out_dir: Path, max_turns: int, timeout_s: float) -> dict:
    tid = task["id"]
    log.info("[task %s] reset env to episode %s", tid, task.get("episode_id"))
    reset_res = _env_call(env_sock, "reset",
                          {"episode_id": task.get("episode_id")})
    instruction = reset_res.get("instruction", "")
    log.info("[task %s] instruction: %s", tid, instruction)

    session_id = f"embench-{tid}"
    t0 = time.perf_counter()
    pilot_res = _submit_task_to_pilot(pilot_addr, instruction, session_id,
                                      max_turns, timeout_s)
    wall_s = time.perf_counter() - t0

    # Query env for success — Pilot doesn't know the task-specific predicate
    scene = _env_call(env_sock, "describe_scene")
    success = False
    try:
        # We piggy-back on the latest step info — do a single no-op to fetch
        # task_success by calling describe_scene (free call).
        # For a more robust check, env_adapter could expose a .task_success
        # probe directly. Keeping it simple for now.
        success = bool(scene.get("task_success", False))
    except Exception:
        success = False

    result = {
        "task_id": tid,
        "episode_id": task.get("episode_id"),
        "instruction": instruction,
        "success": success,
        "steps": int(scene.get("step", 0)),
        "turns": pilot_res["turns"],
        "pilot_ok": pilot_res["pilot_ok"],
        "wall_s": round(wall_s, 2),
        "final_text": pilot_res["final_text"][:400],
        "error": pilot_res.get("error", ""),
    }

    (out_dir / f"task_{tid}.jsonl").write_text(
        json.dumps({**result, "events": pilot_res["events"]}) + "\n"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, default=Path("configs/tasks_phase_a.yaml"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--env-sock", default=os.environ.get("EMBENCH_ENV_SOCKET", "/tmp/embench.sock"))
    ap.add_argument("--pilot-addr", default=os.environ.get("ROBONIX_PILOT_ADDR", "127.0.0.1:50052"))
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--timeout-s", type=float, default=180.0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[runner %(asctime)s] %(message)s")

    args.out.mkdir(parents=True, exist_ok=True)
    tasks = _load_tasks(args.tasks)
    log.info("loaded %d tasks from %s", len(tasks), args.tasks)

    rows: list[dict] = []
    for i, task in enumerate(tasks):
        log.info("[%d/%d] task=%s", i + 1, len(tasks), task["id"])
        res = run_one_task(task, args.env_sock, args.pilot_addr,
                           args.out, args.max_turns, args.timeout_s)
        rows.append(res)
        log.info("  → success=%s steps=%d turns=%d wall=%.1fs",
                 res["success"], res["steps"], res["turns"], res["wall_s"])

    summary = args.out / "summary.csv"
    if rows:
        cols = sorted({k for r in rows for k in r})
        with summary.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        sr = sum(r["success"] for r in rows) / len(rows)
        log.info("Phase A SR = %.1f%% (%d/%d)", 100 * sr,
                 sum(r["success"] for r in rows), len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
