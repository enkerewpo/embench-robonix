#!/usr/bin/env bash
# Generate Python protobuf+grpc stubs for every Robonix proto this repo
# needs (runtime registration + pilot service + contracts + msg deps).
#
# Must be run with the uv venv's python ($REPO/.venv) — needs grpcio-tools.
# The Robonix source tree (default: ~/robonix-embench) is the authoritative
# proto origin.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

: "${ROBONIX_SRC:=$HOME/robonix-embench}"
PROTO_SRC_DIRS=(
  "$ROBONIX_SRC/rust/proto"
  "$ROBONIX_SRC/rust/crates/robonix-interfaces/robonix_proto"
)

mkdir -p proto_gen
touch proto_gen/__init__.py

# Collect every .proto under the two sources
PROTOS=()
for d in "${PROTO_SRC_DIRS[@]}"; do
  while IFS= read -r -d '' f; do
    PROTOS+=("$f")
  done < <(find "$d" -name '*.proto' -print0)
done

INCLUDES=()
for d in "${PROTO_SRC_DIRS[@]}"; do INCLUDES+=("-I$d"); done

echo "[codegen] generating ${#PROTOS[@]} protos into proto_gen/"
python -m grpc_tools.protoc \
  "${INCLUDES[@]}" \
  --python_out=proto_gen \
  --grpc_python_out=proto_gen \
  "${PROTOS[@]}"

echo "[codegen] done — $(ls proto_gen/ | grep -c _pb2) pb2 files"
