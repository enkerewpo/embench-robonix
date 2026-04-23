"""Phase A post-run report.

Reads a Phase A result directory (summary.csv + per-task JSONL) and prints:
1. Overall SR with confidence interval (Wilson 95%).
2. Per-task outcome with brief failure mode.
3. Tool-call breakdown (how many navigate/pick/place/open/close fired).
4. Side-by-side comparison with published EmbodiedBench numbers on EB-Habitat base.

Usage:
    python scripts/report_phase_a.py <results/phase_a_YYYYMMDD_HHMMSS/>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


# Paper Table 2 — EB-Habitat base, as of EmbodiedBench ICML 2025.
PUBLISHED_EB_HABITAT_BASE = {
    "Claude-3.5-Sonnet":         0.96,
    "Llama-3.2-90B-Vision":       0.94,
    "Gemini-1.5-Pro":             0.92,
    "GPT-4o":                     0.86,
    "Gemini-2.0-flash":           0.82,
    "InternVL2_5-78B":            0.80,
    "Gemini-1.5-flash":           0.76,
    "GPT-4o-mini":                0.74,
    "Qwen2-VL-72B":               0.70,
    "Llama-3.2-11B-Vision":       0.70,
    "InternVL2_5-38B":            0.60,
    "Qwen2-VL-7B":                0.48,
    "InternVL2_5-8B":             0.36,
}


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (center - half) / denom), min(1.0, (center + half) / denom)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()

    summary = list(csv.DictReader((args.run_dir / "summary.csv").open()))
    n = len(summary)
    wins = sum(1 for r in summary if r["success"] in ("True", "true", "1"))
    sr = wins / n if n else 0
    lo, hi = _wilson_ci(sr, n)

    print(f"# Phase A — {args.run_dir.name}\n")
    print(f"**Tasks**: {n}  **Success**: {wins}  **SR**: {sr:.1%}  "
          f"(95% Wilson CI [{lo:.1%}, {hi:.1%}])\n")

    # Per-task one-line trace
    print("## Per-task")
    print("| # | episode | instruction | success | steps | turns | wall s |")
    print("|---|---|---|---|---|---|---|")
    for r in summary:
        inst = (r["instruction"] or "").replace("|", "\\|")[:60]
        print(f"| {r['task_id']} | {r['episode_id']} | {inst} | "
              f"{'✓' if r['success'] in ('True','true','1') else '✗'} | "
              f"{r['steps']} | {r['turns']} | {r['wall_s']} |")

    # Aggregate tool-call mix from per-task JSONL
    tool_counts: Counter = Counter()
    for p in sorted(args.run_dir.glob("task_*.jsonl")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        for ev in d.get("events", []):
            if ev.get("kind") == 2:
                for c in ev.get("calls", []):
                    tool_counts[c.get("tool_name", "?")] += 1

    if tool_counts:
        print("\n## Tool-call frequency (across all tasks)")
        print("| tool | count |")
        print("|---|---|")
        for tool, c in tool_counts.most_common():
            print(f"| {tool} | {c} |")

    # Published comparison
    print("\n## Comparison — EB-Habitat base (paper Table 2)")
    print("| Model | SR |")
    print("|---|---|")
    print(f"| **Robonix (this run)** | **{sr:.1%}** |")
    for name, psr in sorted(PUBLISHED_EB_HABITAT_BASE.items(), key=lambda kv: -kv[1]):
        marker = "  ← peer" if abs(psr - sr) < 0.10 else ""
        print(f"| {name} | {psr:.1%}{marker} |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
