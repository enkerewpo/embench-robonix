# Overnight status — 2026-04-25

## What's committed tonight

1. **`scripts/overnight_compare.sh`** — orchestrates the 3-batch overnight
   comparison (Robonix claude-opus-4-7 on missing subsets → Robonix
   gpt-4o-mini on all 5 → EB native VLMPlanner gpt-4o-mini on all 5).
2. **`scripts/compare_report.py`** — pools Robonix summary.csv files and EB
   native `running/eb_habitat/*/<subset>/results/episode_*_final_res.json`
   into a single markdown table + grouped bar chart (`results/_compare/`).
3. **`docs/comparable_systems.md`** — ranked candidate baselines: EB's own
   `VLMPlanner` variants (tier 1, trivial), Inner Monologue / ReAct /
   Reflexion / RoboMatrix (tier 2), Voyager / OpenVLA (tier 3 conceptual).
4. **`configs/tasks_{common_sense,complex_instruction,spatial_relationship,
   visual_appearance}.yaml`** — first 20 episodes each, matching `base`.
5. **`scripts/run_phase_a_multi.sh`** — single-stack multi-subset runner,
   overridable via `SUBSETS` env var.

## What DID run tonight

- Robonix (claude-opus-4-7) on `common_sense` — **SR = 50.0% (10/20)**.
  Stored in `results/phase_a_common_sense_20260425_002721/summary.csv`.
  Noticeably lower than `base` (73.3% pooled) as expected — common_sense
  requires picking the *right* object ("something to clean a spill with")
  whereas base is literal ("a blue mug").

## What DIDN'T run — GPU wedged

Two EB-native smoke attempts (to validate the baseline CLI) hit
`habitat-sim CubeMap.cpp:315` framebuffer-complete assertion on rtx 5090
when `resolution` was left at the EB default (500). The crashes left the
processes in uninterruptible D-state holding a GPU driver rwlock
(`os_acquire_rwlock_write`). Consequences:

- `nvidia-smi` itself hangs.
- Every new habitat-sim init (including Robonix's `env_adapter`) hangs on
  socket-ready, never coming up.
- `kill -9` does not release D-state processes.

**Fix**: reboot rtx (`sudo reboot`), then retry with `resolution=256` in
the EB native invocation. Smoke test #2 with `resolution=256` did NOT hit
CubeMap — that's the correct setting to use. `scripts/overnight_compare.sh`
needs a one-line patch to add `resolution=256` to the EB hydra command.

## Once GPU is back — kickoff recipe

```bash
ssh RTX_server
# Patch EB hydra call (if not already done):
sed -i 's|down_sample_ratio=0.4|resolution=256 down_sample_ratio=0.4|' \
    ~/embench-robonix/scripts/overnight_compare.sh

# Launch overnight under screen
screen -dmS overnight bash -c 'source ~/anaconda3/etc/profile.d/conda.sh && bash ~/embench-robonix/scripts/overnight_compare.sh'
screen -ls
tail -f /tmp/overnight_compare_*.log
```

Estimated total wall time: ~4.5 h (Robonix batches ~1.5 h, EB native ~2.5 h,
serial to keep GPU contention out of the picture).

## Morning aggregation

```bash
# Aggregates all results/phase_a_* dirs + EB native output
python scripts/compare_report.py \
    --robonix-root results \
    --eb-root ~/EmbodiedBench/running/eb_habitat/gpt-4o-mini_phase_a_comparison \
    --out results/_compare/
# -> results/_compare/compare.md + fig_compare.png
```

The comparison markdown has three tables:
- **Table 1**: Robonix SR per (subset × backbone), so you can see the
  claude-opus vs gpt-4o-mini gap on the same architecture.
- **Table 2**: Head-to-head Robonix vs EB native at gpt-4o-mini, per subset,
  with Δ column.
- **Table 3**: Paper anchors (EB Table 2 gpt-4o-mini = 74% on base).

## The research question the comparison answers

Robonix's Pilot + Executor + MCP-skills is architecturally heavier than
EB's direct VLMPlanner-calls-action-id loop, even though both are
functionally ReAct. The comparison tests whether the architectural
overhead (multi-process tool dispatch, routing, etc.) costs any SR. If
Δ ≈ 0 across subsets, that's the finding: Robonix's modularity is free.
If Robonix wins on some subsets and loses on others, the distribution
tells us where the skill-routing layer helps or hurts.
