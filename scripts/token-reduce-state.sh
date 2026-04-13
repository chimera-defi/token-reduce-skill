#!/usr/bin/env bash
set -euo pipefail

repo_root="${TOKEN_REDUCE_REPO_ROOT:-${CLAUDE_PROJECT_DIR:-$(pwd)}}"
if git -C "$repo_root" rev-parse --show-toplevel >/dev/null 2>&1; then
  repo_root="$(git -C "$repo_root" rev-parse --show-toplevel)"
fi
state_dir="$repo_root/.claude/token-reduce-state"

if [[ "${1:-}" != "clear" ]]; then
  echo "usage: ./scripts/token-reduce-state.sh clear [--all|--session-key KEY]" >&2
  exit 2
fi

mkdir -p "$state_dir"

if [[ "${2:-}" == "--all" ]]; then
  rm -f "$state_dir"/*.json
  exit 0
fi

if [[ "${2:-}" == "--session-key" && -n "${3:-}" ]]; then
  rm -f "$state_dir/$3.json" "$state_dir/default.json"
  exit 0
fi

echo "usage: ./scripts/token-reduce-state.sh clear [--all|--session-key KEY]" >&2
exit 2
