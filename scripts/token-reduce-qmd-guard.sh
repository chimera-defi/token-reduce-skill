#!/usr/bin/env bash

# Resolve the repository used by all token-reduce entry points. Explicit roots
# are honored; otherwise use the current Git worktree or the current directory.
token_reduce_resolve_repo_root() {
  local requested_root="${TOKEN_REDUCE_REPO_ROOT:-$PWD}"
  local resolved_root
  [[ -d "$requested_root" ]] || return 1
  if token_reduce_qmd_root_is_aggregate "$requested_root"; then
    (cd "$requested_root" && pwd -P)
    return
  fi

  if resolved_root="$(git -C "$requested_root" rev-parse --show-toplevel 2>/dev/null)"; then
    requested_root="$resolved_root"
  fi
  (cd "$requested_root" && pwd -P)
}

# QMD auto-indexing is limited to real Git worktrees. Aggregate home/workspace
# roots use only the bounded fallback; pytest disposable trees remain on scoped rg.
token_reduce_qmd_root_is_eligible() {
  local requested_root="${1:-}"
  local root git_root
  [[ -d "$requested_root" ]] || return 1
  root="$(cd "$requested_root" && pwd -P)" || return 1

  token_reduce_qmd_root_is_aggregate "$root" && return 1

  case "$root" in
    */pytest-of-*) return 1 ;;
  esac

  git_root="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)" || return 1
  git_root="$(cd "$git_root" && pwd -P)" || return 1
  [[ "$root" == "$git_root" ]]
}

# Aggregate roots must bypass QMD and the generic repository search path.
token_reduce_qmd_root_is_aggregate() {
  local requested_root="${1:-}"
  local root home_root workspace_root
  [[ -d "$requested_root" && -n "${HOME:-}" && -d "$HOME" ]] || return 1
  root="$(cd "$requested_root" && pwd -P)" || return 1
  home_root="$(cd "$HOME" && pwd -P)" || return 1
  [[ "$root" == "$home_root" ]] && return 0
  [[ -d "$home_root/workspace" ]] || return 1
  workspace_root="$(cd "$home_root/workspace" && pwd -P)" || return 1
  [[ "$root" == "$workspace_root" ]]
}

token_reduce_aggregate_path_is_private() {
  case "/$1/" in
    */agent-memory/*|*/secrets/*|*/.ssh/*|*/.gnupg/*|*/.codex/*|*/.claude/*|*/.config/*|*/.local/*|*/.cache/*|*/state/*|*/private/*|*/node_modules/*|*/.git/*|*/venv/*|*/.venv/*|*/venvs/*|*/.venvs/*|*/env/*|*/.env/*|*/virtualenv/*|*/.virtualenv/*|*[hH][oO][lL][dD][oO][uU][tT]*) return 0 ;;
  esac
  return 1
}

# One content search, paths only. Never follow symlinks or load rg config/ignore
# files, and apply negative globs after the extension allowlist so they win.
token_reduce_aggregate_fallback() {
  local root="$1" query="$2" home_root workspace_root scan_root depth=3 file name size
  local inputs=() excludes=() statuses=()
  printf '%s\n' "[token-reduce-search] aggregate root '$root': bounded fallback (no QMD, private dirs excluded); narrow with TOKEN_REDUCE_REPO_ROOT=<repo> or cd into it" >&2
  home_root="$(cd "$HOME" && pwd -P)" || return 1
  scan_root="$home_root"
  if [[ -d "$home_root/workspace" ]]; then
    workspace_root="$(cd "$home_root/workspace" && pwd -P)" || return 1
    if [[ "$workspace_root" != "$home_root" ]] && ! token_reduce_aggregate_path_is_private "$workspace_root"; then
      scan_root="$workspace_root"
      inputs+=(.)
    fi
  fi
  if [[ "$root" == "$home_root" ]]; then
    for file in "$home_root"/*.md; do
      [[ -f "$file" && ! -L "$file" ]] || continue
      token_reduce_aggregate_path_is_private "$file" && continue
      # rg applies --max-filesize only to discovered files, not explicit inputs.
      size="$(stat -c %s -- "$file" 2>/dev/null)" || continue
      [[ "$size" =~ ^[0-9]+$ && "$size" -le 1048576 ]] || continue
      inputs+=("$file")
    done
  fi
  [[ ${#inputs[@]} -gt 0 ]] || return 1
  [[ "$scan_root" != "$home_root" ]] || depth=1
  for name in agent-memory secrets .ssh .gnupg .codex .claude .config .local .cache state private node_modules .git venv .venv venvs .venvs env .env virtualenv .virtualenv; do
    excludes+=(-g "!$name")
  done
  (
    cd "$scan_root" || exit 1
    if rg --no-config --no-ignore --hidden --no-follow -l --max-depth "$depth" --max-filesize 1M \
      -g '*.md' -g '*.toml' -g '*.json' -g '*.sh' -g '*.py' \
      "${excludes[@]}" --iglob '!*holdout*' --color never -e "$query" -- "${inputs[@]}" | head -n 20; then
      exit 0
    else
      statuses=("${PIPESTATUS[@]}")
      # head may close the pipe once the result cap is reached.
      if [[ "${statuses[0]}" == 141 && "${statuses[1]}" == 0 ]]; then
        exit 0
      fi
      exit "${statuses[0]}"
    fi
  )
}
