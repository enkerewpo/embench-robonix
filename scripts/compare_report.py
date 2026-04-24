"""Generate a cross-system Robonix vs EmbodiedBench comparison report.

Inputs
------
- results/phase_a_<subset>[_<tag>]_<ts>/summary.csv
    Per-run Robonix summary. `tag` distinguishes model: absent (default, the
    original claude-opus-4-7 runs) or `gpt4omini`.
- ~/EmbodiedBench/running/eb_habitat/<model>_<exp>/<subset>/summary.json
    EB native VLMPlanner summary — has avg success_rate etc.

Groups the Robonix runs by (model, subset) and pairs each against the
matching EB native SR. Emits a markdown table with pooled SR + N, plus
a bar chart side-by-side per subset.

Usage:
    python scripts/compare_report.py \
        --robonix-root results \
        --eb-root ~/EmbodiedBench/running/eb_habitat/gpt-4o-mini_phase_a_comparison \
        --out results/_compare/
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


SUBSETS = [
    "base",
    "common_sense",
    "complex_instruction",
    "spatial_relationship",
    "visual_appearance",
]


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    half = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    return max(0.0, (center - half) / denom), min(1.0, (center + half) / denom)


# ── parse Robonix runs ──────────────────────────────────────────────────
_DIR_RE = re.compile(r"phase_a_(?P<subset>[a-z_]+?)(?:_(?P<tag>gpt4omini|claudeopus))?_\d{8}_\d{6}")


def _guess_model(dirname: str) -> tuple[str, str]:
    m = _DIR_RE.search(dirname)
    if not m:
        return "unknown", "unknown"
    subset = m.group("subset")
    tag = m.group("tag") or "claudeopus"  # default = original claude runs
    model = {"gpt4omini": "gpt-4o-mini", "claudeopus": "claude-opus-4-7"}[tag]
    return subset, model


def load_robonix(root: Path) -> dict[tuple[str, str], list[dict]]:
    """-> {(subset, model): [{run_dir, n, wins, sr, ...}, ...]}"""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for d in sorted(root.glob("phase_a_*")):
        if d.name == "_aggregate" or d.name == "_compare":
            continue
        csv_path = d / "summary.csv"
        if not csv_path.exists():
            continue
        # The original base runs use dir name `phase_a_20260424_HHMMSS` with
        # NO subset segment — those are claude-opus base data.
        name = d.name
        if re.match(r"phase_a_\d{8}_\d{6}$", name):
            subset, model = "base", "claude-opus-4-7"
        else:
            subset, model = _guess_model(name)
            if subset == "unknown":
                continue
        rows = list(csv.DictReader(csv_path.open()))
        n = len(rows)
        wins = sum(1 for r in rows if r["success"] in ("True", "true", "1"))
        out[(subset, model)].append({
            "dir": d.name, "n": n, "wins": wins,
            "sr": wins / n if n else 0,
        })
    return out


# ── parse EB native runs ────────────────────────────────────────────────
def load_eb_native(root: Path) -> dict[str, dict]:
    """-> {subset: {n, wins, sr}}. EB stores per-episode json in results/."""
    out: dict[str, dict] = {}
    if not root.exists():
        return out
    # EB layout: <eb_root>/<subset>/results/episode_*_final_res.json
    for subset_dir in sorted(root.iterdir()):
        if not subset_dir.is_dir():
            continue
        subset = subset_dir.name
        res_dir = subset_dir / "results"
        if not res_dir.exists():
            continue
        episodes = sorted(res_dir.glob("episode_*_final_res.json"))
        n, wins = 0, 0
        for ep in episodes:
            try:
                d = json.load(ep.open())
            except Exception:
                continue
            # EB episode JSON typically has 'task_success' or last step reward.
            ok = bool(d.get("task_success"))
            n += 1
            wins += int(ok)
        if n:
            out[subset] = {"n": n, "wins": wins, "sr": wins / n}
    return out


# ── pooling helpers ─────────────────────────────────────────────────────
def pool(runs: list[dict]) -> dict:
    n = sum(r["n"] for r in runs)
    wins = sum(r["wins"] for r in runs)
    sr = wins / n if n else 0
    lo, hi = _wilson_ci(sr, n)
    return {"n": n, "wins": wins, "sr": sr, "ci": (lo, hi), "runs": len(runs)}


# ── report ──────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robonix-root", type=Path, default=Path("results"))
    ap.add_argument("--eb-root", type=Path,
                    default=Path.home() / "EmbodiedBench/running/eb_habitat/gpt-4o-mini_phase_a_comparison")
    ap.add_argument("--out", type=Path, default=Path("results/_compare"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    rob = load_robonix(args.robonix_root)
    eb = load_eb_native(args.eb_root)

    lines: list[str] = []
    lines.append("# Robonix vs EmbodiedBench native — EB-Habitat comparison\n")
    lines.append(f"- Robonix results: `{args.robonix_root}/phase_a_*`")
    lines.append(f"- EB native results: `{args.eb_root}`")
    lines.append(f"- First 20/50 episodes per subset (matches Robonix `configs/tasks_*.yaml`).\n")

    # ── Table 1: Robonix multi-model per subset ──────────────────────────
    lines.append("## Robonix SR per subset/model\n")
    lines.append("| Subset | Model | Runs | N | Wins | SR | 95% CI (Wilson) |")
    lines.append("|---|---|---|---|---|---|---|")
    for subset in SUBSETS:
        for model in ("claude-opus-4-7", "gpt-4o-mini"):
            runs = rob.get((subset, model), [])
            if not runs:
                lines.append(f"| {subset} | {model} | 0 | – | – | – | – |")
                continue
            p = pool(runs)
            lines.append(f"| {subset} | {model} | {p['runs']} | {p['n']} | "
                         f"{p['wins']} | {p['sr']:.1%} | "
                         f"[{p['ci'][0]:.1%}, {p['ci'][1]:.1%}] |")
    lines.append("")

    # ── Table 2: Apples-to-apples at gpt-4o-mini ─────────────────────────
    lines.append("## Head-to-head: Robonix vs EB native (gpt-4o-mini)\n")
    lines.append("| Subset | Robonix SR | EB native SR | Δ (Robonix − EB) | Robonix N | EB N |")
    lines.append("|---|---|---|---|---|---|")
    for subset in SUBSETS:
        rob_runs = rob.get((subset, "gpt-4o-mini"), [])
        rp = pool(rob_runs) if rob_runs else None
        ep = eb.get(subset)
        if rp and ep:
            delta = rp["sr"] - ep["sr"]
            lines.append(
                f"| {subset} | {rp['sr']:.1%} | {ep['sr']:.1%} | "
                f"{delta:+.1%} | {rp['n']} | {ep['n']} |"
            )
        else:
            lines.append(f"| {subset} | "
                         f"{(rp['sr'] if rp else 'n/a') if isinstance(rp, dict) else 'n/a'} | "
                         f"{(ep['sr'] if ep else 'n/a') if isinstance(ep, dict) else 'n/a'} | "
                         "– | – | – |")
    lines.append("")

    # ── Table 3: Paper anchors ──────────────────────────────────────────
    lines.append("## Paper anchors (EmbodiedBench Table 2 on base, gpt-4o-mini)\n")
    lines.append("- Paper reports gpt-4o-mini SR on EB-Habitat base = **74%** (50 episodes).")
    lines.append("- Our runs use 20 episodes → looser CI but same backbone + same env.")
    lines.append("")

    # Figure — grouped bar chart: subset on x, bars for robonix/gpt-4o-mini and EB native
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = SUBSETS
        rob_bars = [pool(rob.get((s, "gpt-4o-mini"), []))["sr"] if rob.get((s, "gpt-4o-mini")) else 0 for s in labels]
        eb_bars = [eb.get(s, {}).get("sr", 0) for s in labels]
        x = range(len(labels))
        fig, ax = plt.subplots(figsize=(9, 4.5))
        w = 0.35
        ax.bar([i - w/2 for i in x], rob_bars, w, label="Robonix (gpt-4o-mini)", color="#3b82f6")
        ax.bar([i + w/2 for i in x], eb_bars, w, label="EB native (gpt-4o-mini)", color="#f97316")
        ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_ylabel("Success rate"); ax.set_ylim(0, 1); ax.grid(axis="y", alpha=0.3)
        ax.legend()
        fig.tight_layout(); fig.savefig(args.out / "fig_compare.png", dpi=120)
        plt.close(fig)
        lines.append("![side-by-side SR](fig_compare.png)\n")
    except Exception as e:
        lines.append(f"(no figure: {e})\n")

    (args.out / "compare.md").write_text("\n".join(lines))
    print(f"wrote {args.out}/compare.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
