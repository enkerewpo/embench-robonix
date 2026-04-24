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

**Fix options (ranked, safest first)**:

1. **Wait.** The locked rwlock is in `nvidia-modeset`, not core CUDA or
   `nvidia-uvm`. zzb's vLLM (CUDA-only, no EGL) is still serving fine.
   If zzb finishes and no one else is rendering, a sysadmin can do
   `rmmod nvidia_drm nvidia_modeset && modprobe nvidia_modeset nvidia_drm`
   to clear the stuck lock without a full reboot. This does kill anyone
   currently using X/rendering on rtx, so coordinate first.

2. **Wait for maintenance window**, then full `sudo reboot`. Cleanest
   but kills all running jobs including zzb's vLLM — needs agreement.

3. **DO NOT** attempt more habitat runs in the meantime. Each attempt
   that touches habitat-sim becomes another D-state process holding
   another slice of the same rwlock, and the more that pile up the
   higher the risk the lock cascades into a fully global driver wedge
   that would also kill zzb's vLLM. Three D zombies already exist
   (pids 2031557, 2073940, 2134838 as of 2026-04-25 02:10).

Once unwedged, `scripts/overnight_compare.sh` is ready to run as-is
(already pins `resolution=256` for the EB-native invocation, which is
what avoided the CubeMap crash in smoke test #2).

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
