#!/usr/bin/env bash
# End-to-end Phase A launcher for rtx server.
#
#   1. Activate the `embench` conda env (EmbodiedBench deps).
#   2. Start env_adapter as a background process (owns one EB-Habitat env).
#   3. Start Robonix atlas/executor/pilot (via `rbnx` from dev-packaging).
#   4. Run the runner → 20 tasks.
#   5. Tear down.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

: "${EMBENCH_ENV_SOCKET:=/tmp/embench.sock}"
: "${OUT_DIR:=results/phase_a_$(date +%Y%m%d_%H%M%S)}"
export EMBENCH_ENV_SOCKET OUT_DIR

# Activate conda env (caller should have run `source ~/anaconda3/etc/profile.d/conda.sh`)
conda activate embench

# 1. Sanity — embodiedbench importable
python -c "from embodiedbench.envs.eb_habitat.EBHabEnv import EBHabEnv; print('eb_habitat ok')"

# 2. Start env adapter (sidecar, background)
python -m embench_robonix.env_adapter > "$OUT_DIR/env_adapter.log" 2>&1 &
ADAPTER_PID=$!
trap "kill $ADAPTER_PID 2>/dev/null || true; rm -f $EMBENCH_ENV_SOCKET" EXIT

# wait for socket up
for _ in $(seq 1 30); do
  [ -S "$EMBENCH_ENV_SOCKET" ] && break
  sleep 0.5
done

# 3. Start Robonix stack (TODO: wire to `rbnx start` from dev-packaging)
#    For now we run skills as standalone MCP servers + a stub Pilot client.
#    Concrete `rbnx deploy ...` invocation will drop in once dev-packaging branch has it.
# rbnx deploy configs/robonix_manifest.yaml &
# ROBONIX_PID=$!
# trap "kill $ROBONIX_PID 2>/dev/null" EXIT

mkdir -p "$OUT_DIR"

# 4. Run 20 tasks
python -m embench_robonix.runner --tasks configs/tasks_phase_a.yaml --out "$OUT_DIR"

echo "results: $OUT_DIR/summary.csv"
