#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-paths.sh <query words...>" >&2
  exit 2
fi

QUERY="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"

if OUTPUT="$("$SCRIPT_DIR/token-reduce-search.sh" --paths-only "$QUERY")"; then
  printf '%s\n' "$OUTPUT"
  LINES=$(printf '%s\n' "$OUTPUT" | sed '/^$/d' | wc -l | tr -d ' ')
  CHARS=$(printf '%s' "$OUTPUT" | wc -c | tr -d ' ')
  uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
    --event helper_invocation \
    --source helper \
    --tool token_reduce_paths \
    --status ok \
    --query "$QUERY" \
    --meta-json "{\"lines\":$LINES,\"chars\":$CHARS}" >/dev/null 2>&1 || true
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi
uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
  --event helper_invocation \
  --source helper \
  --tool token_reduce_paths \
  --status error \
  --query "$QUERY" >/dev/null 2>&1 || true
exit $?
