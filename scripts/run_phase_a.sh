#!/usr/bin/env bash
# Phase A launcher — real Robonix stack (atlas + pilot + executor)
# driving EB-Habitat tasks through 3 skill MCP servers.
#
# Prereq on rtx:
#   - robonix-embench repo built: ~/robonix-embench/rust/target/release/{robonix-atlas,robonix-pilot,robonix-executor,rbnx}
#   - `embench` conda env with EmbodiedBench + habitat-sim installed
#   - scripts/codegen.sh already run once (populates proto_gen/)
#
# Env vars:
#   ROBONIX_SRC        (default: ~/robonix-embench)
#   ROBONIX_ATLAS      (default: 127.0.0.1:50051)
#   EMBENCH_EVAL_SET   (default: base)
#   EMBENCH_ENV_SOCKET (default: /tmp/embench.sock)
#   OUT_DIR            (default: results/phase_a_$ts)
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

: "${ROBONIX_SRC:=$HOME/robonix-embench}"
: "${ROBONIX_ATLAS:=127.0.0.1:50051}"
: "${ROBONIX_PILOT_PORT:=50071}"
: "${ROBONIX_PILOT_ADDR:=127.0.0.1:$ROBONIX_PILOT_PORT}"
: "${EMBENCH_EVAL_SET:=base}"
: "${EMBENCH_ENV_SOCKET:=/tmp/embench.sock}"
: "${OUT_DIR:=results/phase_a_$(date +%Y%m%d_%H%M%S)}"
export ROBONIX_ATLAS ROBONIX_PILOT_PORT ROBONIX_PILOT_ADDR EMBENCH_EVAL_SET EMBENCH_ENV_SOCKET OUT_DIR

RBNX_BIN="$ROBONIX_SRC/rust/target/release"
for b in robonix-atlas robonix-pilot robonix-executor; do
  [ -x "$RBNX_BIN/$b" ] || { echo "missing $RBNX_BIN/$b — cargo build first"; exit 1; }
done

mkdir -p "$OUT_DIR"

# Activate conda env (habitat-sim etc.)
source "$HOME/anaconda3/etc/profile.d/conda.sh"
conda activate embench

# Also ensure embench-robonix deps (mcp, grpcio, etc.) are in the conda env.
pip show mcp >/dev/null 2>&1 || pip install "mcp[cli]>=1.0" grpcio grpcio-tools

# Make embench_robonix importable + put proto_gen on sys.path for skills
export PYTHONPATH="$HERE/src:$HERE/proto_gen:${PYTHONPATH:-}"

# Regen proto stubs if missing
if [ ! -f proto_gen/robonix_runtime_pb2.py ]; then
  bash scripts/codegen.sh
fi

# ── Process tracking ──────────────────────────────────────────────────────
declare -a PIDS=()
spawn() {
  local name="$1"; shift
  echo "[run_phase_a] starting $name: $*"
  "$@" > "$OUT_DIR/$name.log" 2>&1 &
  PIDS+=($!)
}
cleanup() {
  echo "[run_phase_a] shutting down ..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  rm -f "$EMBENCH_ENV_SOCKET"
}
trap cleanup EXIT INT TERM

# 1. Atlas (capability registry)
spawn atlas "$RBNX_BIN/robonix-atlas"
sleep 1.5

# 2. Env adapter sidecar (owns the EBHabEnv instance)
spawn env_adapter python -m embench_robonix.env_adapter
# wait for UNIX socket up (env loading can take ~30s)
for _ in $(seq 1 120); do
  [ -S "$EMBENCH_ENV_SOCKET" ] && break
  sleep 1
done
[ -S "$EMBENCH_ENV_SOCKET" ] || { echo "env_adapter never came up"; exit 1; }

# 3. Skill MCP servers (each registers its tools to atlas + starts HTTP MCP)
spawn eb_navigate python skills/eb_navigate/src/skill.py
spawn eb_manipulate python skills/eb_manipulate/src/skill.py
spawn eb_observe python skills/eb_observe/src/skill.py
sleep 2

# 4. Pilot + Executor
spawn pilot "$RBNX_BIN/robonix-pilot"
spawn executor "$RBNX_BIN/robonix-executor"
sleep 2

# 5. Runner drives 20 tasks through the stack
python -m embench_robonix.runner \
  --tasks configs/tasks_phase_a.yaml \
  --out "$OUT_DIR"

echo "results: $OUT_DIR/summary.csv"
