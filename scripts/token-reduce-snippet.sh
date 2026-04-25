#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-snippet.sh <query words...>" >&2
  exit 2
fi

QUERY="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${TOKEN_REDUCE_REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
TELEMETRY_CONTEXT="${TOKEN_REDUCE_TELEMETRY_CONTEXT:-runtime}"
DIAG_FILE="$(mktemp 2>/dev/null || true)"

cleanup_diag() {
  if [[ -n "${DIAG_FILE:-}" && -f "$DIAG_FILE" ]]; then
    rm -f "$DIAG_FILE"
  fi
}

diag_value() {
  local key="$1"
  if [[ -z "${DIAG_FILE:-}" || ! -f "$DIAG_FILE" ]]; then
    return 0
  fi
  awk -F= -v needle="$key" '$1 == needle {print substr($0, index($0, "=") + 1); exit}' "$DIAG_FILE"
}

sanitize_number() {
  local raw="$1"
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s' "$raw"
  else
    printf '0'
  fi
}

trap cleanup_diag EXIT

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

if OUTPUT="$(TOKEN_REDUCE_DIAG_FILE="$DIAG_FILE" "$SCRIPT_DIR/token-reduce-search.sh" --snippets "$QUERY")"; then
  printf '%s\n' "$OUTPUT"
  LINES=$(printf '%s\n' "$OUTPUT" | sed '/^$/d' | wc -l | tr -d ' ')
  CHARS=$(printf '%s' "$OUTPUT" | wc -c | tr -d ' ')
  END_MS="$(now_ms)"
  LATENCY_MS="$(( END_MS - START_MS ))"
  BACKEND="$(diag_value backend)"
  [[ -n "$BACKEND" ]] || BACKEND="unknown"
  QMD_COLLECTION_ACTION="$(diag_value qmd_collection_action)"
  [[ -n "$QMD_COLLECTION_ACTION" ]] || QMD_COLLECTION_ACTION="not_checked"
  QMD_FILES_STATUS="$(diag_value qmd_files_status)"
  [[ -n "$QMD_FILES_STATUS" ]] || QMD_FILES_STATUS="not_run"
  QMD_ENSURE_MS="$(sanitize_number "$(diag_value qmd_ensure_ms)")"
  QMD_FILES_MS="$(sanitize_number "$(diag_value qmd_files_ms)")"
  QMD_SNIPPET_MS="$(sanitize_number "$(diag_value qmd_snippet_ms)")"
  FALLBACK_MS="$(sanitize_number "$(diag_value fallback_ms)")"
  FALLBACK_USED="$(sanitize_number "$(diag_value fallback_used)")"
  PATH_HINT_SHORT_CIRCUIT="$(sanitize_number "$(diag_value path_hint_short_circuit)")"
  uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
    --event helper_invocation \
    --source helper \
    --tool token_reduce_snippet \
    --status ok \
    --query "$QUERY" \
    --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"backend\":\"$BACKEND\",\"qmd_collection_action\":\"$QMD_COLLECTION_ACTION\",\"qmd_files_status\":\"$QMD_FILES_STATUS\",\"qmd_ensure_ms\":$QMD_ENSURE_MS,\"qmd_files_ms\":$QMD_FILES_MS,\"qmd_snippet_ms\":$QMD_SNIPPET_MS,\"fallback_ms\":$FALLBACK_MS,\"fallback_used\":$FALLBACK_USED,\"path_hint_short_circuit\":$PATH_HINT_SHORT_CIRCUIT,\"lines\":$LINES,\"chars\":$CHARS,\"latency_ms\":$LATENCY_MS,\"exit_code\":0}" >/dev/null 2>&1 || true
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi
STATUS=$?
END_MS="$(now_ms)"
LATENCY_MS="$(( END_MS - START_MS ))"
BACKEND="$(diag_value backend)"
[[ -n "$BACKEND" ]] || BACKEND="unknown"
QMD_COLLECTION_ACTION="$(diag_value qmd_collection_action)"
[[ -n "$QMD_COLLECTION_ACTION" ]] || QMD_COLLECTION_ACTION="not_checked"
QMD_FILES_STATUS="$(diag_value qmd_files_status)"
[[ -n "$QMD_FILES_STATUS" ]] || QMD_FILES_STATUS="not_run"
QMD_ENSURE_MS="$(sanitize_number "$(diag_value qmd_ensure_ms)")"
QMD_FILES_MS="$(sanitize_number "$(diag_value qmd_files_ms)")"
QMD_SNIPPET_MS="$(sanitize_number "$(diag_value qmd_snippet_ms)")"
FALLBACK_MS="$(sanitize_number "$(diag_value fallback_ms)")"
FALLBACK_USED="$(sanitize_number "$(diag_value fallback_used)")"
PATH_HINT_SHORT_CIRCUIT="$(sanitize_number "$(diag_value path_hint_short_circuit)")"
uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
  --event helper_invocation \
  --source helper \
  --tool token_reduce_snippet \
  --status error \
  --query "$QUERY" \
  --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"backend\":\"$BACKEND\",\"qmd_collection_action\":\"$QMD_COLLECTION_ACTION\",\"qmd_files_status\":\"$QMD_FILES_STATUS\",\"qmd_ensure_ms\":$QMD_ENSURE_MS,\"qmd_files_ms\":$QMD_FILES_MS,\"qmd_snippet_ms\":$QMD_SNIPPET_MS,\"fallback_ms\":$FALLBACK_MS,\"fallback_used\":$FALLBACK_USED,\"path_hint_short_circuit\":$PATH_HINT_SHORT_CIRCUIT,\"latency_ms\":$LATENCY_MS,\"exit_code\":$STATUS}" >/dev/null 2>&1 || true
exit "$STATUS"
