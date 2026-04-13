#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-paths.sh <query words...>" >&2
  exit 2
fi

QUERY="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${TOKEN_REDUCE_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
TELEMETRY_CONTEXT="${TOKEN_REDUCE_TELEMETRY_CONTEXT:-runtime}"

now_ms() {
  local raw
  raw="$(date +%s%3N 2>/dev/null || true)"
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s' "$raw"
    return
  fi
  printf '%s' "$(( $(date +%s) * 1000 ))"
}

START_MS="$(now_ms)"

if OUTPUT="$("$SCRIPT_DIR/token-reduce-search.sh" --paths-only "$QUERY")"; then
  printf '%s\n' "$OUTPUT"
  LINES=$(printf '%s\n' "$OUTPUT" | sed '/^$/d' | wc -l | tr -d ' ')
  CHARS=$(printf '%s' "$OUTPUT" | wc -c | tr -d ' ')
  END_MS="$(now_ms)"
  LATENCY_MS="$(( END_MS - START_MS ))"
  uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
    --event helper_invocation \
    --source helper \
    --tool token_reduce_paths \
    --status ok \
    --query "$QUERY" \
    --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"lines\":$LINES,\"chars\":$CHARS,\"latency_ms\":$LATENCY_MS,\"exit_code\":0}" >/dev/null 2>&1 || true
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi
STATUS=$?
END_MS="$(now_ms)"
LATENCY_MS="$(( END_MS - START_MS ))"
uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
  --event helper_invocation \
  --source helper \
  --tool token_reduce_paths \
  --status error \
  --query "$QUERY" \
  --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"latency_ms\":$LATENCY_MS,\"exit_code\":$STATUS}" >/dev/null 2>&1 || true
exit "$STATUS"
