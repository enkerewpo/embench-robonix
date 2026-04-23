#!/usr/bin/env bash
# Launch eb_navigate MCP server. Expects the embench-robonix venv on PATH
# (Robonix manifest sets this up) and EMBENCH_ENV_SOCKET env var pointing
# at the shared env adapter socket.
set -euo pipefail
SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python "$SKILL_DIR/src/skill.py" "$@"
