#!/usr/bin/env bash
# Phase A launcher — real Robonix stack driving EB-Habitat via 3 skill MCP servers.
#
# Python environment layout (rtx):
#   conda `embench` (py3.9) — env_adapter ONLY (habitat-sim pins py3.9)
#   ~/embench-robonix/.venv (py3.12, uv) — skills + runner (mcp>=1.0 needs 3.10+)
#
# Run from repo root on rtx:
#   source ~/anaconda3/etc/profile.d/conda.sh
#   bash scripts/run_phase_a.sh
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
export ROBONIX_ATLAS ROBONIX_PILOT_PORT ROBONIX_PILOT_ADDR \
       EMBENCH_EVAL_SET EMBENCH_ENV_SOCKET OUT_DIR

RBNX_BIN="$ROBONIX_SRC/rust/target/release"
for b in robonix-atlas robonix-pilot robonix-executor; do
  [ -x "$RBNX_BIN/$b" ] || { echo "missing $RBNX_BIN/$b — cargo build first"; exit 1; }
done

SKILL_VENV="$HERE/.venv"
[ -x "$SKILL_VENV/bin/python" ] || { echo "$SKILL_VENV missing — create via uv venv"; exit 1; }

mkdir -p "$OUT_DIR"

# Regen proto stubs into proto_gen/ if missing (use skill venv which has grpcio-tools)
if [ ! -f "$HERE/proto_gen/robonix_runtime_pb2.py" ]; then
  echo "[run_phase_a] proto_gen/ empty — copy from a robonix package for now"
  echo "[run_phase_a] (upstream: rust/examples/packages/maniskill_vla_demo/proto_gen/)"
fi

# Compose PYTHONPATH (same for every process)
export PYTHONPATH="$HERE/src:$HERE/proto_gen:${PYTHONPATH:-}"

# ── process tracking ──────────────────────────────────────────────────────
declare -a PIDS=()
spawn() {
  local name="$1"; shift
  echo "[run_phase_a] starting $name: $*"
  "$@" > "$OUT_DIR/$name.log" 2>&1 &
  PIDS+=($!)
}
cleanup() {
  echo "[run_phase_a] shutting down ..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  rm -f "$EMBENCH_ENV_SOCKET"
}
trap cleanup EXIT INT TERM

SKILL_PY="$SKILL_VENV/bin/python"

# VLM credentials — single source of truth is the deploy manifest's
# system.pilot section (vlm_base_url / vlm_api_key / vlm_api_format /
# vlm_model). Until the pilot-reads-manifest refactor lands, we read them
# from env vars here and fan out to each consumer (vlm_service reads
# VLM_*, pilot reads ROBONIX_VLM_* — same values).
: "${VLM_API_KEY:=${OPENAI_API_KEY:?OPENAI_API_KEY or VLM_API_KEY must be set — this IS the manifest pilot.vlm_api_key value}}"
: "${VLM_BASE_URL:=${OPENAI_BASE_URL:-https://api.openai.com/v1}}"
: "${VLM_MODEL:=${OPENAI_MODEL:-gpt-4o-mini}}"
: "${VLM_MESSAGE_FORMAT:=openai}"
export VLM_API_KEY VLM_BASE_URL VLM_MODEL VLM_MESSAGE_FORMAT

# 1. Atlas
spawn atlas "$RBNX_BIN/robonix-atlas"
sleep 1.5

# 1b. VLM service (system service — registered for pilot to discover under
#     robonix/srv/cognition/reason). Not a scene service.
spawn vlm_service "$SKILL_PY" services/vlm_service/vlm_service/service.py
sleep 1.5

# 2. env_adapter inside embench conda (owns EBHabEnv)
spawn env_adapter conda run -n embench --live-stream python -m embench_robonix.env_adapter
# Wait up to 120s for socket to appear (habitat-sim init is slow).
for _ in $(seq 1 120); do
  [ -S "$EMBENCH_ENV_SOCKET" ] && break
  sleep 1
done
[ -S "$EMBENCH_ENV_SOCKET" ] || { echo "env_adapter did not come up"; exit 1; }
echo "[run_phase_a] env_adapter ready"

# 3. Skill MCP servers in uv venv (py3.12)
spawn eb_navigate "$SKILL_PY" skills/eb_navigate/src/skill.py
spawn eb_manipulate "$SKILL_PY" skills/eb_manipulate/src/skill.py
spawn eb_observe "$SKILL_PY" skills/eb_observe/src/skill.py
sleep 2

# 4. Pilot + Executor (rust binaries)
spawn pilot "$RBNX_BIN/robonix-pilot"
spawn executor "$RBNX_BIN/robonix-executor"
sleep 2

# 5. Runner (uv venv) drives the tasks through pilot
"$SKILL_PY" -m embench_robonix.runner \
  --tasks configs/tasks_phase_a.yaml \
  --out "$OUT_DIR"

echo "results: $OUT_DIR/summary.csv"
