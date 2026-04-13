#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-orchestrate.sh <query words...>" >&2
  exit 2
fi

QUERY="$*"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TELEMETRY_CONTEXT="${TOKEN_REDUCE_TELEMETRY_CONTEXT:-runtime}"

GRAPHIFY_ENABLED="${TOKEN_REDUCE_ENABLE_GRAPHIFY:-0}"
GRAPH_PATH="${TOKEN_REDUCE_GRAPH_PATH:-$REPO_ROOT/graphify-out/graph.json}"
GRAPH_BUDGET="${TOKEN_REDUCE_GRAPHIFY_BUDGET:-1200}"
GRAPHIFY_UV_DIR="${TOKEN_REDUCE_GRAPHIFY_UV_DIR:-}"
FALLBACK_MODE="${TOKEN_REDUCE_ORCH_FALLBACK:-paths}" # paths|snippet

now_ms() {
  local raw
  raw="$(date +%s%3N 2>/dev/null || true)"
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    printf '%s' "$raw"
    return
  fi
  printf '%s' "$(( $(date +%s) * 1000 ))"
}

log_event() {
  local status="$1"
  local backend="$2"
  local fallback_used="$3"
  local started_ms="$4"
  local output="$5"
  local end_ms latency_ms lines chars
  end_ms="$(now_ms)"
  latency_ms="$(( end_ms - started_ms ))"
  lines="$(printf '%s\n' "$output" | sed '/^$/d' | wc -l | tr -d ' ')"
  chars="$(printf '%s' "$output" | wc -c | tr -d ' ')"
  uv run "$SCRIPT_DIR/token_reduce_telemetry.py" --repo-root "$REPO_ROOT" log \
    --event helper_invocation \
    --source helper \
    --tool token_reduce_orchestrate \
    --status "$status" \
    --query "$QUERY" \
    --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"backend\":\"$backend\",\"fallback_used\":$fallback_used,\"mode\":\"$FALLBACK_MODE\",\"latency_ms\":$latency_ms,\"lines\":$lines,\"chars\":$chars}" >/dev/null 2>&1 || true
}

is_symbol_like_query() {
  if [[ "$QUERY" != *" "* ]]; then
    [[ "$QUERY" =~ [A-Z] ]] && return 0
    [[ "$QUERY" == *"_"* ]] && return 0
    [[ "$QUERY" == *"::"* ]] && return 0
  fi
  return 1
}

graphify_available() {
  if command -v graphify >/dev/null 2>&1; then
    return 0
  fi
  if [[ -n "$GRAPHIFY_UV_DIR" ]] && [[ -d "$GRAPHIFY_UV_DIR" ]]; then
    return 0
  fi
  return 1
}

run_graphify_query() {
  if command -v graphify >/dev/null 2>&1; then
    graphify query "$QUERY" --graph "$GRAPH_PATH" --budget "$GRAPH_BUDGET"
    return
  fi
  uv run --directory "$GRAPHIFY_UV_DIR" graphify query "$QUERY" --graph "$GRAPH_PATH" --budget "$GRAPH_BUDGET"
}

fallback_helper() {
  if [[ "$FALLBACK_MODE" == "snippet" ]]; then
    "$SCRIPT_DIR/token-reduce-snippet.sh" "$QUERY"
  else
    "$SCRIPT_DIR/token-reduce-paths.sh" "$QUERY"
  fi
}

START_MS="$(now_ms)"

can_try_graphify=0
if [[ "$GRAPHIFY_ENABLED" == "1" ]] && graphify_available && [[ -f "$GRAPH_PATH" ]] && is_symbol_like_query; then
  can_try_graphify=1
fi

if [[ "$can_try_graphify" == "1" ]]; then
  set +e
  GRAPHIFY_OUTPUT="$(run_graphify_query 2>&1)"
  GRAPHIFY_STATUS=$?
  set -e

  if [[ "$GRAPHIFY_STATUS" -eq 0 ]] && [[ "$GRAPHIFY_OUTPUT" != *"No matching nodes found."* ]]; then
    printf '%s\n' "$GRAPHIFY_OUTPUT"
    log_event "ok" "graphify" false "$START_MS" "$GRAPHIFY_OUTPUT"
    "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
    exit 0
  fi
fi

if HELPER_OUTPUT="$(fallback_helper)"; then
  printf '%s\n' "$HELPER_OUTPUT"
  log_event "ok" "token-reduce" "$can_try_graphify" "$START_MS" "$HELPER_OUTPUT"
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi

STATUS=$?
log_event "error" "token-reduce" "$can_try_graphify" "$START_MS" ""
exit "$STATUS"
