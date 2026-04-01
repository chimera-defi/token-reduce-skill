#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="${1:-/root/.openclaw/workspace/dev}"
HELPER="${2:-token-reduce-paths}"
QUERY="${3:-token reduce}"
PER_REPO_TIMEOUT="${PER_REPO_TIMEOUT:-15}"

if ! command -v "$HELPER" >/dev/null 2>&1; then
  echo "missing helper on PATH: $HELPER" >&2
  exit 2
fi

find "$WORKSPACE_ROOT" -maxdepth 1 -mindepth 1 -type d | sort -u | while read -r repo; do
  [[ -n "$repo" ]] || continue
  if git -C "$repo" rev-parse --show-toplevel >/dev/null 2>&1; then
    printf '== %s ==\n' "$repo"
    if (
      cd "$repo"
      timeout "$PER_REPO_TIMEOUT" "$HELPER" "$QUERY" | head -5
    ); then
      printf 'ok\n'
    else
      printf 'timeout-or-error\n'
    fi
  fi
done
