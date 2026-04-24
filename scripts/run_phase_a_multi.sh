#!/usr/bin/env bash
# Run Phase A across all 5 EB-Habitat eval subsets sequentially.
# Each subset gets a fresh Robonix stack (env_adapter owns one EBHabEnv
# and can only host one subset at a time). Takes ~1 hour per subset
# with gpt-4o-mini; set SUBSETS to a subspace for a quicker pass.
#
# Usage (on rtx, from repo root):
#   source ~/anaconda3/etc/profile.d/conda.sh
#   bash scripts/run_phase_a_multi.sh
#
# Override subsets or add a run index suffix:
#   SUBSETS="base common_sense" RUN_TAG=r1 bash scripts/run_phase_a_multi.sh
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

: "${SUBSETS:=base common_sense complex_instruction spatial_relationship visual_appearance}"
: "${RUN_TAG:=}"

for subset in $SUBSETS; do
  cfg="configs/tasks_${subset}.yaml"
  [[ -f "$cfg" ]] || { echo "missing $cfg"; exit 1; }
  stamp="$(date +%Y%m%d_%H%M%S)"
  out="results/phase_a_${subset}_${stamp}${RUN_TAG:+_$RUN_TAG}"
  echo "=== $subset -> $out ==="
  EMBENCH_EVAL_SET="$subset" TASKS_YAML="$cfg" OUT_DIR="$out" \
    bash scripts/run_phase_a.sh
done

echo
echo "done. runs:"
ls -d results/phase_a_*_"$(date +%Y%m%d)"* 2>/dev/null
