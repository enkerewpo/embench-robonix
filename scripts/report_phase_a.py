"""Phase A post-run report.

Reads a Phase A result directory (summary.csv + runner.log + executor.log +
per-task JSONL) and writes a markdown report:

1. Overall SR with Wilson 95% CI.
2. Per-task detail:
   - instruction (natural language goal)
   - Robonix's plan (ordered sequence of tool calls dispatched by Pilot→Executor)
   - per-call result (ok / error + short output)
   - final env task_success
3. Aggregate tool-call breakdown.
4. Side-by-side comparison with published EmbodiedBench EB-Habitat base SR.

Usage:
    python scripts/report_phase_a.py <results/phase_a_YYYYMMDD_HHMMSS/>

The per-task plan comes from `executor.log` (ground truth of every dispatch
+ each call's stdout). Pilot's Stream events occasionally emit empty
TaskGraph messages, so the executor log is a more reliable source.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PUBLISHED_EB_HABITAT_BASE = {
    "Claude-3.5-Sonnet":       0.96,
    "Llama-3.2-90B-Vision":     0.94,
    "Gemini-1.5-Pro":           0.92,
    "GPT-4o":                   0.86,
    "Gemini-2.0-flash":         0.82,
    "InternVL2_5-78B":          0.80,
    "Gemini-1.5-flash":         0.76,
    "GPT-4o-mini":              0.74,
    "Qwen2-VL-72B":             0.70,
    "Llama-3.2-11B-Vision":     0.70,
    "InternVL2_5-38B":          0.60,
    "Qwen2-VL-7B":              0.48,
    "InternVL2_5-8B":           0.36,
}


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (center - half) / denom), min(1.0, (center + half) / denom)


# ── log parsing ──────────────────────────────────────────────────────────
_RUNNER_TS_RE = re.compile(
    r"\[runner (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\] \[task (eb_base_\d+)\] (reset env to episode|instruction:|→ success=)")

_EXEC_TS_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z INFO[^\]]*\] \[executor\] (dispatching|'[a-z_]+' (?:ok|failed)):?\s+'?([a-z_]+)'?")

_DISPATCH_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z INFO[^\]]*\] \[executor\] dispatching '([a-z_]+)' \(call_id=([A-Za-z0-9_-]+)\)")
_DISPATCH_OK_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z INFO[^\]]*\] \[executor\] '([a-z_]+)' ok: (.*)", re.DOTALL)
_DISPATCH_ERR_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z WARN[^\]]*\] \[executor\] '([a-z_]+)' failed: (.*)", re.DOTALL)


def _parse_runner_windows(runner_log: Path) -> list[tuple[str, datetime, datetime]]:
    """Return [(task_id, start_utc, end_utc)] from runner.log timestamps."""
    if not runner_log.exists():
        return []
    lines = runner_log.read_text().splitlines()
    events: list[tuple[datetime, str, str]] = []  # (ts, task_id, marker)
    for line in lines:
        m = _RUNNER_TS_RE.search(line)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)
        events.append((ts, m.group(2), m.group(3)))
    # pair "reset env" (start) with "→ success=" (end) per task
    tasks: list[tuple[str, datetime, datetime]] = []
    starts: dict[str, datetime] = {}
    for ts, tid, marker in events:
        if marker.startswith("reset env"):
            starts[tid] = ts
        elif marker.startswith("→ success="):
            s = starts.get(tid)
            if s:
                tasks.append((tid, s, ts))
    return tasks


def _parse_executor_dispatches(exec_log: Path) -> list[dict]:
    """Return an ordered list of {ts, tool, call_id, status, body} events."""
    if not exec_log.exists():
        return []
    # Split log into entries by the leading [YYYY-MM-DDTHH:MM:SSZ
    text = exec_log.read_text()
    entries = re.split(r"(?m)(?=^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z (?:INFO|WARN))", text)
    pending: dict[str, dict] = {}
    out: list[dict] = []
    for entry in entries:
        m = _DISPATCH_RE.match(entry)
        if m:
            pending[m.group(3)] = {
                "ts": datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc),
                "tool": m.group(2),
                "call_id": m.group(3),
            }
            continue
        ok = _DISPATCH_OK_RE.match(entry)
        err = _DISPATCH_ERR_RE.match(entry)
        if ok or err:
            status = "ok" if ok else "failed"
            ts_s, tool, body = (ok or err).group(1, 2, 3)
            ts = datetime.strptime(ts_s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            body = body.strip().splitlines()[0:8]
            body = "\n".join(body)[:400]
            # match pending by nearest tool name (most recent)
            match_cid = None
            for cid, p in list(pending.items()):
                if p["tool"] == tool:
                    match_cid = cid
                    break
            if match_cid:
                del pending[match_cid]
            out.append({
                "ts": ts, "tool": tool, "call_id": match_cid or "?",
                "status": status, "body": body,
            })
    return out


def _plan_for(task_id: str, windows: list, dispatches: list) -> list[dict]:
    window = next((s, e) for (tid, s, e) in windows if tid == task_id)
    return [d for d in dispatches if window[0] <= d["ts"] <= window[1]]


# ── main ─────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()

    summary = list(csv.DictReader((args.run_dir / "summary.csv").open()))
    n = len(summary)
    wins = sum(1 for r in summary if r["success"] in ("True", "true", "1"))
    sr = wins / n if n else 0
    lo, hi = _wilson_ci(sr, n)

    windows = _parse_runner_windows(args.run_dir / "runner.log")
    dispatches = _parse_executor_dispatches(args.run_dir / "executor.log")

    out: list[str] = []
    out.append(f"# Phase A — {args.run_dir.name}\n")
    out.append(f"**Tasks**: {n}  **Success**: {wins}  "
               f"**SR**: {sr:.1%}  (95% Wilson CI [{lo:.1%}, {hi:.1%}])\n")

    # Per-task detail with Robonix's plan
    out.append("## Per-task detail\n")
    for r in summary:
        tid = r["task_id"]
        success = r["success"] in ("True", "true", "1")
        mark = "✓ SUCCESS" if success else "✗ FAILED"
        out.append(f"### {tid}  ({mark})")
        out.append(f"**instruction**: {r['instruction']}\n")
        out.append(f"- steps: {r['steps']}  turns: {r['turns']}  wall: {r['wall_s']}s")
        try:
            plan = _plan_for(tid, windows, dispatches) if windows else []
        except StopIteration:
            plan = []
        if plan:
            out.append(f"\n**Robonix plan** ({len(plan)} calls):\n")
            out.append("| # | tool | status | result snippet |")
            out.append("|---|---|---|---|")
            for i, p in enumerate(plan, 1):
                body = (p["body"] or "").replace("|", "\\|").replace("\n", " ")[:120]
                out.append(f"| {i} | `{p['tool']}` | {p['status']} | {body} |")
        else:
            out.append("\n*(no executor dispatches logged for this task window)*")
        out.append("")

    # Aggregate tool-call breakdown
    tool_counts = Counter(d["tool"] for d in dispatches)
    ok_counts = Counter(d["tool"] for d in dispatches if d["status"] == "ok")
    if tool_counts:
        out.append("## Tool-call aggregate")
        out.append("| tool | total | ok | fail | ok% |")
        out.append("|---|---|---|---|---|")
        for tool, total in tool_counts.most_common():
            ok = ok_counts.get(tool, 0)
            out.append(f"| `{tool}` | {total} | {ok} | {total - ok} | {100*ok/total:.0f}% |")
        out.append("")

    # Published comparison
    out.append("## Comparison — EB-Habitat base (paper Table 2)")
    out.append("| Model | SR |")
    out.append("|---|---|")
    out.append(f"| **Robonix (this run)** | **{sr:.1%}** |")
    for name, psr in sorted(PUBLISHED_EB_HABITAT_BASE.items(), key=lambda kv: -kv[1]):
        marker = "  ← peer" if abs(psr - sr) < 0.08 else ""
        out.append(f"| {name} | {psr:.1%}{marker} |")

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
