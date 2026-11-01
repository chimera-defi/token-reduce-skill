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

source "$SCRIPT_DIR/token-reduce-qmd-guard.sh"
REQUESTED_ROOT="${TOKEN_REDUCE_REPO_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"
ROOT_ARG_NEXT=0
for ARG in "$@"; do
  if [[ "$ROOT_ARG_NEXT" == 1 ]]; then
    REQUESTED_ROOT="$ARG"
    ROOT_ARG_NEXT=0
  elif [[ "$ARG" == --repo-root ]]; then
    ROOT_ARG_NEXT=1
  elif [[ "$ARG" == --repo-root=* ]]; then
    REQUESTED_ROOT="${ARG#--repo-root=}"
  fi
done
if token_reduce_qmd_root_is_aggregate "$REQUESTED_ROOT"; then
  exec env TOKEN_REDUCE_REPO_ROOT="$REQUESTED_ROOT" python3 "$TARGET" "$@"
elif command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run --no-project "$TARGET")
elif command -v python3 >/dev/null 2>&1; then
  RUNNER=(python3 "$TARGET")
else
  echo "token-reduce-adaptive: neither uv nor python3 found; skipping helper (fail open)" >&2
  exit 0
fi

exec timeout 20s "${RUNNER[@]}" "$@"
