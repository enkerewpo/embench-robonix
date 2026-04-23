#!/usr/bin/env bash
# Generate Python protobuf+grpc stubs for Robonix runtime registration.
#
# Output: proto_gen/robonix_runtime_pb2.py + robonix_runtime_pb2_grpc.py
#
# Must be run inside the embench-robonix venv (needs grpcio-tools installed).
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

mkdir -p proto_gen
touch proto_gen/__init__.py

python -m grpc_tools.protoc \
  -I proto \
  --python_out=proto_gen \
  --grpc_python_out=proto_gen \
  proto/robonix_runtime.proto

# grpc_tools emits `import robonix_runtime_pb2` (top-level). Since we put the
# stubs into proto_gen/, we either add proto_gen to sys.path at runtime or
# rewrite the import. Skills do `sys.path.insert(0, proto_gen)` — match that.
echo "wrote $(ls proto_gen/ | grep pb2)"
