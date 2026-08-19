#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-adaptive.sh <query words...>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/token_reduce_adaptive.py"

if [[ ! -f "$TARGET" ]]; then
  echo "token-reduce-adaptive: $TARGET not found; skipping helper (fail open)" >&2
  exit 0
fi

if command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run "$TARGET")
elif command -v python3 >/dev/null 2>&1; then
  RUNNER=(python3 "$TARGET")
else
  echo "token-reduce-adaptive: neither uv nor python3 found; skipping helper (fail open)" >&2
  exit 0
fi

exec timeout 20s "${RUNNER[@]}" "$@"
