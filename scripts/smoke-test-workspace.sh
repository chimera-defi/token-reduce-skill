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

total=0
ok_count=0
fail_count=0
skip_count=0

while read -r repo; do
  [[ -n "$repo" ]] || continue

  # Only treat direct git roots/worktrees as projects. Do not inherit a parent git repo.
  if [[ ! -e "$repo/.git" ]]; then
    skip_count=$((skip_count + 1))
    continue
  fi
  if ! git -C "$repo" rev-parse --show-toplevel >/dev/null 2>&1; then
    skip_count=$((skip_count + 1))
    continue
  fi

  total=$((total + 1))
  printf '== %s ==\n' "$repo"
  if (
    cd "$repo"
    timeout "$PER_REPO_TIMEOUT" "$HELPER" "$QUERY" | head -5
  ); then
    printf 'ok\n'
    ok_count=$((ok_count + 1))
  else
    printf 'timeout-or-error\n'
    fail_count=$((fail_count + 1))
  fi
done < <(find "$WORKSPACE_ROOT" -maxdepth 1 -mindepth 1 -type d | sort -u)

printf '\nsummary: tested=%d ok=%d failed=%d skipped=%d\n' "$total" "$ok_count" "$fail_count" "$skip_count"
if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
