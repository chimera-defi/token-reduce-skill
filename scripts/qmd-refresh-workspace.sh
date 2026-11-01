#!/usr/bin/env bash
set -euo pipefail

PATH="/home/agents/.local/bin:/home/agents/.npm-global/bin:/home/agents/.bun/bin:$PATH"
QMD_STORE_MODULE="${QMD_STORE_MODULE:-/home/agents/.bun/install/global/node_modules/@tobilu/qmd/dist/store.js}"
QMD_INDEX_PATH="${QMD_INDEX_PATH:-${XDG_CACHE_HOME:-$HOME/.cache}/qmd/index.sqlite}"
STATE_DIR="${HOME:?HOME must be set}/.local/state"
LOCK_DIR="$STATE_DIR/qmd-refresh"
LOCK_PATH="$LOCK_DIR/workspace-refresh.lock"

if ! command -v flock >/dev/null 2>&1; then
  echo "qmd-refresh-workspace: flock is required to prevent overlapping refreshes" >&2
  exit 1
fi
umask 077
for directory in "$HOME" "$HOME/.local" "$STATE_DIR" "$LOCK_DIR"; do
  if [[ -L "$directory" ]]; then
    echo "qmd-refresh-workspace: refusing symlink lock directory: $directory" >&2
    exit 1
  fi
  if [[ ! -e "$directory" ]]; then mkdir -m 700 "$directory"; fi
  if [[ ! -d "$directory" || "$(stat -c '%u' "$directory")" != "$UID" ]]; then
    echo "qmd-refresh-workspace: lock path must be a real directory owned by uid $UID: $directory" >&2
    exit 1
  fi
  directory_mode="$(stat -c '%a' "$directory")"
  if (( (8#$directory_mode & 8#022) != 0 || (8#$directory_mode & 8#300) != 8#300 )); then
    echo "qmd-refresh-workspace: lock path must be owner-writable and not group/world writable: $directory" >&2
    exit 1
  fi
  if [[ "$directory" == "$LOCK_DIR" ]] && (( (8#$directory_mode & 8#077) != 0 )); then
    echo "qmd-refresh-workspace: lock leaf must be private (mode 0700): $directory" >&2
    exit 1
  fi
done
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
