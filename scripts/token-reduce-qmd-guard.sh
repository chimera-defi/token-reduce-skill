#!/usr/bin/env bash

# Resolve the repository used by all token-reduce entry points. Explicit roots
# are honored; otherwise use the current Git worktree or the current directory.
token_reduce_resolve_repo_root() {
  local requested_root="${TOKEN_REDUCE_REPO_ROOT:-$PWD}"
  local resolved_root
  [[ -d "$requested_root" ]] || return 1

  if resolved_root="$(git -C "$requested_root" rev-parse --show-toplevel 2>/dev/null)"; then
    requested_root="$resolved_root"
  fi
  (cd "$requested_root" && pwd -P)
}

# QMD auto-indexing is limited to real Git worktrees. Aggregate home/workspace
# roots and pytest's disposable trees must remain on the scoped-rg path.
token_reduce_qmd_root_is_eligible() {
  local requested_root="${1:-}"
  local root home_root git_root
  [[ -d "$requested_root" ]] || return 1
  root="$(cd "$requested_root" && pwd -P)" || return 1

  if [[ -n "${HOME:-}" && -d "$HOME" ]]; then
    home_root="$(cd "$HOME" && pwd -P)" || home_root=""
    if [[ -n "$home_root" && ( "$root" == "$home_root" || "$root" == "$home_root/workspace" ) ]]; then
      return 1
    fi
  fi

  case "$root" in
    /tmp/pytest-of-*|/tmp/pytest-of-*/*) return 1 ;;
  esac

  git_root="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)" || return 1
  git_root="$(cd "$git_root" && pwd -P)" || return 1
  [[ "$root" == "$git_root" ]]
}
