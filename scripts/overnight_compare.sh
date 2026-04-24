#!/usr/bin/env bash
# Overnight comparison: Robonix vs EmbodiedBench native VLMPlanner on
# EB-Habitat, 5 subsets × first 20 episodes each.
#
# Runs three sequential batches:
#   1. Robonix (claude-opus-4-7) on complex/spatial/visual  — extends
#      existing base/common_sense claude-opus data to full 5-subset
#      profile.
#   2. Robonix (gpt-4o-mini) on all 5 subsets — apples-to-apples backbone
#      for the EB baseline.
#   3. EB native VLMPlanner (gpt-4o-mini, chat_history=True) on all 5
#      subsets — the comparable external agent.
#
# All three read API creds from ~/embench-robonix/.env (ofox proxy).
# Expected total wall time: ~4-5 hours on rtx.
set -uo pipefail   # no -e: individual subset failure must not kill the batch

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

BATCH_LOG="/tmp/overnight_compare_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$BATCH_LOG") 2>&1

echo "=== overnight compare starting $(date) ==="
echo "batch log: $BATCH_LOG"

# Load ofox credentials — Robonix reads VLM_*, EB reads OPENAI_*
set -a; source "$HERE/.env"; set +a

# run_phase_a.sh re-sources .env via `set -a`, overwriting any VLM_MODEL
# we export. Patch .env in place per batch and restore on EXIT.
ORIG_VLM_MODEL="$(grep -E '^VLM_MODEL=' "$HERE/.env" | cut -d= -f2-)"
trap 'sed -i "s|^VLM_MODEL=.*|VLM_MODEL=${ORIG_VLM_MODEL}|" "$HERE/.env"' EXIT
set_env_model() { sed -i "s|^VLM_MODEL=.*|VLM_MODEL=$1|" "$HERE/.env"; echo "[overnight] VLM_MODEL=$1"; }

# ── BATCH 1: Robonix claude-opus-4-7 on the 3 remaining subsets ─────────
set_env_model claude-opus-4-7
for subset in complex_instruction spatial_relationship visual_appearance; do
  echo
  echo "--- Robonix[$VLM_MODEL] / $subset ---"
  stamp="$(date +%Y%m%d_%H%M%S)"
  EMBENCH_EVAL_SET="$subset" \
    TASKS_YAML="configs/tasks_${subset}.yaml" \
    OUT_DIR="results/phase_a_${subset}_${stamp}" \
    bash scripts/run_phase_a.sh || echo "[WARN] Robonix $subset failed"
done

# ── BATCH 2: Robonix with gpt-4o-mini on all 5 subsets ──────────────────
set_env_model gpt-4o-mini
for subset in base common_sense complex_instruction spatial_relationship visual_appearance; do
  echo
  echo "--- Robonix[$VLM_MODEL] / $subset ---"
  stamp="$(date +%Y%m%d_%H%M%S)"
  tasks_cfg="configs/tasks_${subset}.yaml"
  [[ "$subset" == "base" ]] && tasks_cfg="configs/tasks_phase_a.yaml"
  EMBENCH_EVAL_SET="$subset" \
    TASKS_YAML="$tasks_cfg" \
    OUT_DIR="results/phase_a_${subset}_gpt4omini_${stamp}" \
    bash scripts/run_phase_a.sh || echo "[WARN] Robonix $subset gpt-4o-mini failed"
done

# ── BATCH 3: EB native VLMPlanner with gpt-4o-mini ──────────────────────
echo
echo "--- EmbodiedBench native / gpt-4o-mini / all 5 subsets ---"
export OPENAI_API_KEY="$VLM_API_KEY"
export OPENAI_BASE_URL="$VLM_BASE_URL"

(
  cd ~/EmbodiedBench
  source ~/anaconda3/etc/profile.d/conda.sh
  conda activate embench
  # chat_history=True matches Robonix's multi-turn with env feedback.
  # down_sample_ratio=0.4 → first 20/50 episodes per subset.
  # resolution=256 is MANDATORY — EB's default 500 hits a CubeMap
  # framebuffer assertion on rtx 5090 and leaves processes in
  # uninterruptible D state, wedging the GPU until reboot.
  # See docs/overnight_status_2026-04-25.md.
  python -m embodiedbench.main \
    env=eb-hab \
    model_name=gpt-4o-mini \
    exp_name=phase_a_comparison \
    chat_history=True \
    resolution=256 \
    down_sample_ratio=0.4 \
    eval_sets='[base,common_sense,complex_instruction,spatial_relationship,visual_appearance]' \
    || echo "[WARN] EB native run failed"
)

echo
echo "=== overnight compare done $(date) ==="
echo "robonix results under $HERE/results/phase_a_*"
echo "EB native results under ~/EmbodiedBench/running/eb_habitat/gpt-4o-mini_phase_a_comparison/"
