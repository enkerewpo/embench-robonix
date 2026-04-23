"""Phase A task runner.

Sequence per task:
1. Reset the shared EB-Habitat env to the task's starting state.
2. Fetch the language instruction ("put the apple on the counter").
3. Hand it to Robonix Pilot → TaskGraph → Executor dispatches skills.
4. Watch the env until success / max steps (30 for EB-Habitat).
5. Log outcome + trajectory to a per-task JSONL + aggregate SR to CSV.

The Pilot/Executor/Atlas processes are started by scripts/run_phase_a.sh
BEFORE this runner is invoked — it assumes the stack is already up and
reachable at the HTTP endpoints configured in robonix_manifest.yaml.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("embench.runner")


def load_tasks(cfg_path: Path) -> list[dict]:
    import yaml
    with cfg_path.open() as f:
        cfg = yaml.safe_load(f)
    return cfg["tasks"]


def run_one_task(task: dict, out_dir: Path) -> dict:
    """Run one EB-Habitat task through the Robonix stack. Returns SR summary."""
    t0 = time.perf_counter()
    # TODO: reset env adapter to task["episode_id"] on eval_set task["eval_set"]
    # TODO: submit instruction to robonix-pilot (HTTP), wait for TaskGraph
    # TODO: stream execution events, record trajectory
    # TODO: check env success flag, record outcome

    # Stub implementation while EB-Habitat install is pending.
    result = {
        "task_id": task["id"],
        "eval_set": task.get("eval_set", "base"),
        "instruction": task.get("instruction", ""),
        "success": False,
        "steps": 0,
        "wall_s": time.perf_counter() - t0,
        "status": "not_implemented",
    }

    (out_dir / f"task_{task['id']}.jsonl").write_text(json.dumps(result) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, default=Path("configs/tasks_phase_a.yaml"))
    ap.add_argument("--out", type=Path, default=Path("results/phase_a"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="[runner %(asctime)s] %(message)s")

    args.out.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(args.tasks)
    log.info("loaded %d tasks from %s", len(tasks), args.tasks)

    rows: list[dict] = []
    for i, task in enumerate(tasks):
        log.info("[%d/%d] task=%s", i + 1, len(tasks), task["id"])
        res = run_one_task(task, args.out)
        rows.append(res)
        log.info("  → success=%s steps=%d wall=%.2fs",
                 res["success"], res["steps"], res["wall_s"])

    summary_path = args.out / "summary.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted(rows[0].keys())) if rows else None
        if w is not None:
            w.writeheader()
            for r in rows:
                w.writerow(r)
    if rows:
        sr = sum(r["success"] for r in rows) / len(rows)
        log.info("Phase A SR = %.2f%% (%d/%d)", 100 * sr, sum(r["success"] for r in rows), len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
