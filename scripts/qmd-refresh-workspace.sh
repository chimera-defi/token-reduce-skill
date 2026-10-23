#!/usr/bin/env bash
set -euo pipefail

PATH="/home/agents/.local/bin:/home/agents/.npm-global/bin:/home/agents/.bun/bin:$PATH"
QMD_STORE_MODULE="${QMD_STORE_MODULE:-/home/agents/.bun/install/global/node_modules/@tobilu/qmd/dist/store.js}"
QMD_INDEX_PATH="${QMD_INDEX_PATH:-${XDG_CACHE_HOME:-$HOME/.cache}/qmd/index.sqlite}"
LOCK_DIR="${HOME:?HOME must be set}/.cache/qmd"
LOCK_PATH="$LOCK_DIR/workspace-refresh.lock"

if ! command -v flock >/dev/null 2>&1; then
  echo "qmd-refresh-workspace: flock is required to prevent overlapping refreshes" >&2
  exit 1
fi
umask 077
mkdir -p "$LOCK_DIR"
if [[ -L "$LOCK_DIR" || "$(stat -c '%u' "$LOCK_DIR")" != "$UID" ]]; then
  echo "qmd-refresh-workspace: lock directory must be a real directory owned by uid $UID: $LOCK_DIR" >&2
  exit 1
fi
lock_dir_mode="$(stat -c '%a' "$LOCK_DIR")"
if (( (8#$lock_dir_mode & 8#022) != 0 )); then
  echo "qmd-refresh-workspace: lock directory must not be group/world writable: $LOCK_DIR" >&2
  exit 1
fi
if [[ -L "$LOCK_PATH" ]]; then
  echo "qmd-refresh-workspace: refusing symlink lock file: $LOCK_PATH" >&2
  exit 1
fi
if [[ -e "$LOCK_PATH" ]]; then
  if [[ ! -f "$LOCK_PATH" || "$(stat -c '%u' "$LOCK_PATH")" != "$UID" ]]; then
    echo "qmd-refresh-workspace: lock file must be a regular file owned by uid $UID: $LOCK_PATH" >&2
    exit 1
  fi
  lock_file_mode="$(stat -c '%a' "$LOCK_PATH")"
  if (( (8#$lock_file_mode & 8#022) != 0 )); then
    echo "qmd-refresh-workspace: lock file must not be group/world writable: $LOCK_PATH" >&2
    exit 1
  fi
fi
exec 9>>"$LOCK_PATH"
if ! flock -n 9; then
  echo "qmd-refresh-workspace: another workspace refresh is running" >&2
  exit 1
fi

repos=(
  /home/agents/workspace/Etc-mono-repo
  /home/agents/workspace/eth2-quickstart
  /home/agents/workspace/specforge
  /home/agents/workspace/walletradar
  /home/agents/workspace/ethglobal-cannes-2026-intelligence-exchange
  /home/agents/workspace/chimericlabs-llc
  /home/agents/workspace/SharedDeposit
  /home/agents/workspace/token-reduce-skill
)

args=(--db "$QMD_INDEX_PATH" --store-module "$QMD_STORE_MODULE")
for arg in "$@"; do
  if [[ "$arg" == "--dry-run" ]]; then
    args+=(--dry-run)
  else
    echo "qmd-refresh-workspace: unsupported argument: $arg" >&2
    exit 2
  fi
done
for repo in "${repos[@]}"; do args+=(--repo "$repo"); done
exec node "$(dirname "$0")/qmd-refresh-workspace.mjs" "${args[@]}"
