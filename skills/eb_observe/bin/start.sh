#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python "$SKILL_DIR/src/skill.py" "$@"
