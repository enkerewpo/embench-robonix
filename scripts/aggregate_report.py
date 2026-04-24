"""Aggregate multiple Phase A runs (across models / configs) into one
comparison report with figures.

Usage:
    python scripts/aggregate_report.py results/ --labels \\
        "gpt-5.4-mini=phase_a_2026*231222,phase_a_2026*232032,phase_a_2026*232532" \\
        "gpt-5.4=phase_a_2026*..." \\
        "gemini-2.5-pro=phase_a_2026*..." \\
        "claude-opus-4-7=phase_a_2026*..."

For each label, pools its matching run dirs and computes:
  SR (±95% Wilson CI), mean steps, mean turns, mean wall_s,
  per-tool success rate.

Outputs:
  <out>/aggregate.md
  <out>/fig_sr.png, fig_steps.png, fig_turns.png, fig_wall.png, fig_tools.png
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (center - half) / denom), min(1.0, (center + half) / denom)


def _gather_group(root: Path, patterns: list[str]) -> dict:
    """Pool summary.csv rows across all matching run dirs."""
    rows: list[dict] = []
    used_dirs: list[str] = []
    for pat in patterns:
        for d in sorted(glob.glob(str(root / pat))):
            sp = Path(d) / "summary.csv"
            if sp.exists():
                used_dirs.append(os.path.basename(d))
                with sp.open() as f:
                    rows.extend(csv.DictReader(f))
    n = len(rows)
    wins = sum(1 for r in rows if r.get("success") in ("True", "true", "1"))
    steps = [int(float(r.get("steps", 0))) for r in rows]
    turns = [int(float(r.get("turns", 0))) for r in rows]
    walls = [float(r.get("wall_s", 0)) for r in rows]
    sr = wins / n if n else 0
    lo, hi = _wilson_ci(sr, n)
    return {
        "runs": used_dirs,
        "n": n,
        "wins": wins,
        "sr": sr,
        "sr_ci": (lo, hi),
        "mean_steps": sum(steps) / n if n else 0,
        "mean_turns": sum(turns) / n if n else 0,
        "mean_wall": sum(walls) / n if n else 0,
        "steps": steps,
        "turns": turns,
        "walls": walls,
    }


def _plot_bars(groups: dict, metric_key: str, title: str,
               ylabel: str, out_path: Path, percent: bool = False) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(groups.keys())
    vals = [g[metric_key] for g in groups.values()]
    if percent:
        vals = [v * 100 for v in vals]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    bars = ax.bar(names, vals, color="#3b82f6")
    if metric_key == "sr":
        errs = [[(v - g["sr_ci"][0] * 100) for v, g in zip(vals, groups.values())],
                [(g["sr_ci"][1] * 100 - v) for v, g in zip(vals, groups.values())]]
        ax.errorbar(names, vals, yerr=errs, fmt='none', ecolor='black', capsize=4)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}",
                ha="center", va="bottom", fontsize=9)
    plt.xticks(rotation=15, ha="right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="results/ dir")
    ap.add_argument("--labels", nargs="+", required=True,
                    help="label=glob1,glob2,... one per model/config group")
    ap.add_argument("--out", type=Path, default=None,
                    help="output dir (default: root/_aggregate)")
    ap.add_argument("--robonix-only", action="store_true",
                    help="skip paper-comparison table")
    args = ap.parse_args()

    out = args.out or (args.root / "_aggregate")
    out.mkdir(parents=True, exist_ok=True)

    groups: dict[str, dict] = {}
    for spec in args.labels:
        label, _, globs = spec.partition("=")
        patterns = [p.strip() for p in globs.split(",") if p.strip()]
        groups[label] = _gather_group(args.root, patterns)

    lines: list[str] = ["# Phase A cross-model aggregate\n"]

    lines.append("## Summary table")
    lines.append("| Model | N | SR | 95% CI | mean steps | mean turns | mean wall s |")
    lines.append("|---|---|---|---|---|---|---|")
    for lab, g in groups.items():
        lines.append(
            f"| {lab} | {g['n']} | {g['sr']:.1%} | "
            f"[{g['sr_ci'][0]:.1%}, {g['sr_ci'][1]:.1%}] | "
            f"{g['mean_steps']:.1f} | {g['mean_turns']:.1f} | {g['mean_wall']:.1f} |"
        )
    lines.append("")

    # Plots
    _plot_bars(groups, "sr", "Task Success Rate", "SR (%)",
               out / "fig_sr.png", percent=True)
    _plot_bars(groups, "mean_steps", "Mean env steps per task", "steps",
               out / "fig_steps.png")
    _plot_bars(groups, "mean_turns", "Mean VLM planner turns per task", "turns",
               out / "fig_turns.png")
    _plot_bars(groups, "mean_wall", "Mean end-to-end wall time per task", "sec",
               out / "fig_wall.png")
    lines.append("![SR](fig_sr.png)")
    lines.append("![steps](fig_steps.png)")
    lines.append("![turns](fig_turns.png)")
    lines.append("![wall](fig_wall.png)")
    lines.append("")

    # Runs used
    lines.append("## Runs pooled per group")
    for lab, g in groups.items():
        lines.append(f"- **{lab}** ({len(g['runs'])} runs): " +
                     ", ".join(g['runs']))
    lines.append("")

    (out / "aggregate.md").write_text("\n".join(lines))
    print(f"wrote {out}/aggregate.md + figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
