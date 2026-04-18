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
ORCH_MODE="${TOKEN_REDUCE_ORCH_MODE:-auto}"      # auto|adaptive|paths|snippet|structural
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
    --meta-json "{\"context\":\"$TELEMETRY_CONTEXT\",\"backend\":\"$backend\",\"fallback_used\":$fallback_used,\"mode\":\"$ORCH_MODE\",\"latency_ms\":$latency_ms,\"lines\":$lines,\"chars\":$chars}" >/dev/null 2>&1 || true
}

is_symbol_like_query() {
  if [[ "$QUERY" != *" "* ]]; then
    [[ "$QUERY" =~ [A-Z] ]] && return 0
    [[ "$QUERY" == *"_"* ]] && return 0
    [[ "$QUERY" == *"::"* ]] && return 0
  fi
  return 1
}

query_has_impact_terms() {
  local lowered
  lowered="${QUERY,,}"
  [[ "$lowered" =~ impact|blast|dependency|dependencies|affected|caller|callee|upstream|downstream ]]
}

resolve_fallback_cmd() {
  if [[ "$FALLBACK_MODE" == "snippet" ]]; then
    printf '%s\0%s' "$SCRIPT_DIR/token-reduce-snippet.sh" "$QUERY"
  else
    printf '%s\0%s' "$SCRIPT_DIR/token-reduce-paths.sh" "$QUERY"
  fi
}

pick_backend() {
  case "$ORCH_MODE" in
    auto)
      if command -v token-reduce-adaptive >/dev/null 2>&1; then
        printf '%s\0%s\0%s' "token-reduce-adaptive" "$QUERY" "adaptive"
      else
        printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-adaptive.sh" "$QUERY" "adaptive"
      fi
      ;;
    adaptive)
      if command -v token-reduce-adaptive >/dev/null 2>&1; then
        printf '%s\0%s\0%s' "token-reduce-adaptive" "$QUERY" "adaptive"
      else
        printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-adaptive.sh" "$QUERY" "adaptive"
      fi
      ;;
    paths)
      printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-paths.sh" "$QUERY" "paths"
      ;;
    snippet)
      printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-snippet.sh" "$QUERY" "snippet"
      ;;
    structural)
      if command -v token-reduce-structural >/dev/null 2>&1 && is_symbol_like_query; then
        if query_has_impact_terms; then
          printf '%s\0%s\0%s\0%s\0%s\0%s' "token-reduce-structural" "--project-root" "$REPO_ROOT" "change-impact" "$QUERY" "structural"
        else
          printf '%s\0%s\0%s\0%s\0%s\0%s' "token-reduce-structural" "--project-root" "$REPO_ROOT" "find-symbol" "$QUERY" "structural"
        fi
      else
        printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-adaptive.sh" "$QUERY" "adaptive"
      fi
      ;;
    *)
      printf '%s\0%s\0%s' "$SCRIPT_DIR/token-reduce-adaptive.sh" "$QUERY" "adaptive"
      ;;
  esac
}

START_MS="$(now_ms)"

mapfile -d '' -t CMD_PARTS < <(pick_backend)
BACKEND_LABEL="${CMD_PARTS[-1]}"
unset 'CMD_PARTS[-1]'

set +e
OUT="$("${CMD_PARTS[@]}" 2>&1)"
STATUS=$?
set -e

if [[ "$STATUS" -eq 0 ]]; then
  printf '%s\n' "$OUT"
  log_event "ok" "$BACKEND_LABEL" false "$START_MS" "$OUT"
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi

mapfile -d '' -t FALLBACK_CMD < <(resolve_fallback_cmd)
set +e
FALLBACK_OUT="$("${FALLBACK_CMD[@]}" 2>&1)"
FALLBACK_STATUS=$?
set -e

if [[ "$FALLBACK_STATUS" -eq 0 ]]; then
  printf '%s\n' "$FALLBACK_OUT"
  log_event "ok" "$BACKEND_LABEL" true "$START_MS" "$FALLBACK_OUT"
  "$SCRIPT_DIR/token-reduce-state.sh" clear --all >/dev/null 2>&1 || true
  exit 0
fi

printf '%s\n' "$OUT" >&2
printf '%s\n' "$FALLBACK_OUT" >&2
log_event "error" "$BACKEND_LABEL" true "$START_MS" ""
exit "$FALLBACK_STATUS"
