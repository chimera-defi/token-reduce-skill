#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-search.sh [--paths-only|--snippets] <query> [glob]" >&2
  exit 2
fi

MODE="paths-only"
if [[ "${1:-}" == "--paths-only" ]]; then
  MODE="paths-only"
  shift
elif [[ "${1:-}" == "--snippets" ]]; then
  MODE="snippets"
  shift
fi

if [[ $# -lt 1 ]]; then
  echo "usage: ./scripts/token-reduce-search.sh [--paths-only|--snippets] <query> [glob]" >&2
  exit 2
fi

QUERY="$1"
GLOB="${2:-}"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
COLLECTION_NAME="repo-$(printf '%s' "$REPO_ROOT" | sha1sum | cut -c1-12)"
QMD_EXTENSION_FILE="${REPO_ROOT}/scripts/qmd-file-extensions.txt"
QMD_EXTENSIONS_DEFAULT="md,txt,rst,py,sh,bash,zsh,js,jsx,ts,tsx,mjs,cjs,json,yml,yaml,toml,ini,cfg,go,rs,java,rb,php"
if [[ -f "$QMD_EXTENSION_FILE" ]]; then
  QMD_EXTENSIONS_DEFAULT="$(tr -d '[:space:]' <"$QMD_EXTENSION_FILE")"
fi
QMD_EXTENSIONS="${TOKEN_REDUCE_QMD_EXTENSIONS:-$QMD_EXTENSIONS_DEFAULT}"
QMD_MASK_DEFAULT="**/*.{${QMD_EXTENSIONS}}"
QMD_MASK="${TOKEN_REDUCE_QMD_MASK:-$QMD_MASK_DEFAULT}"
IFS=',' read -r -a QMD_EXTENSION_LIST <<<"$QMD_EXTENSIONS"
QMD_COLLECTION_EXISTS_REGEX="^${COLLECTION_NAME}[[:space:]]"
QMD_STAMP_DIR="${REPO_ROOT}/artifacts"
QMD_STAMP_PATH="${QMD_STAMP_DIR}/qmd-${COLLECTION_NAME}.stamp"
QMD_REFRESH_TTL_SECONDS="${TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS:-180}"
NEEDS_PATH_HINT=0
PREFER_SKILL_SCRIPTS=0
NEEDS_HOOK_FOCUS=0
PREFER_SCRIPT_CONTENT=0
DEFAULT_EXCLUDES=(
  -g '!graphify-out/**'
  -g '!artifacts/token-reduction/events.jsonl'
  -g '!artifacts/token-reduction/snapshots/**'
  -g '!tools/token-reduce-skill/**'
)
FINGERPRINT_EXCLUDES=(
  -g '!.git/**'
  -g '!node_modules/**'
  -g '!graphify-out/**'
  -g '!artifacts/**'
  -g '!.worktrees/**'
  -g '!tools/token-reduce-skill/**'
)

debug() {
  if [[ "${TOKEN_REDUCE_DEBUG:-0}" == "1" ]]; then
    printf '%s\n' "$*" >&2
  fi
}

warn() {
  printf '%s\n' "$*" >&2
}

if [[ "$QUERY" =~ (^|[[:space:]])(script|hook)([[:space:]]|$) || "$QUERY" == *".py"* || "$QUERY" == *".sh"* || "$QUERY" == *"_"* ]]; then
  NEEDS_PATH_HINT=1
fi

if [[ "$QUERY" =~ (^|[[:space:]])hook([[:space:]]|$) ]]; then
  NEEDS_HOOK_FOCUS=1
fi

if [[ "$QUERY" =~ [Tt]oken[[:space:]-]?[Rr]eduction ]]; then
  PREFER_SKILL_SCRIPTS=1
fi

if [[ "$QUERY" =~ (^|[[:space:]])(benchmark|measure|adoption)([[:space:]]|$) ]]; then
  PREFER_SCRIPT_CONTENT=1
fi

symbol_like_pattern() {
  local input="$1"
  local token
  local tokens=()

  while IFS= read -r token; do
    [[ "$token" == *"_"* ]] || continue
    [[ -n "$token" ]] || continue
    tokens+=("$token")
    [[ ${#tokens[@]} -ge 3 ]] && break
  done < <(printf '%s' "$input" | tr -cs '[:alnum:]_.:-' '\n')

  if [[ ${#tokens[@]} -eq 0 ]]; then
    return 1
  fi

  local pattern="${tokens[0]}"
  local i
  for ((i = 1; i < ${#tokens[@]}; i++)); do
    pattern="${pattern}|${tokens[i]}"
  done
  printf '%s' "$pattern"
}

path_pattern() {
  local lowered token symbol_pattern
  lowered="$(printf '%s' "$QUERY" | tr '[:upper:]' '[:lower:]')"
  if symbol_pattern="$(symbol_like_pattern "$lowered" 2>/dev/null)"; then
    printf '%s' "$symbol_pattern"
    return 0
  fi
  if [[ "$lowered" == *".py"* || "$lowered" == *".sh"* || "$lowered" == *"-"* ]]; then
    printf '%s' "$QUERY"
    return 0
  fi

  local tokens=()
  while IFS= read -r token; do
    case "$token" in
      ""|find|path|paths|repo|this|that|only|return|script|scripts|hook|python|workflow|broad|exploratory|scans|blocks|block|minimum|context|possible|the)
        continue
        ;;
    esac
    if [[ ${#token} -ge 4 ]]; then
      tokens+=("$token")
    fi
    [[ ${#tokens[@]} -ge 4 ]] && break
  done < <(printf '%s' "$lowered" | tr -cs '[:alnum:]_.-' '\n')

  if [[ ${#tokens[@]} -eq 0 ]]; then
    printf '%s' "$QUERY"
    return 0
  fi

  local pattern="${tokens[0]}"
  local i
  for ((i = 1; i < ${#tokens[@]}; i++)); do
    pattern="${pattern}|${tokens[i]}"
  done
  printf '%s' "$pattern"
}

content_pattern() {
  local lowered token symbol_pattern
  lowered="$(printf '%s' "$QUERY" | tr '[:upper:]' '[:lower:]')"
  if symbol_pattern="$(symbol_like_pattern "$lowered" 2>/dev/null)"; then
    printf '%s' "$symbol_pattern"
    return 0
  fi

  local tokens=()
  while IFS= read -r token; do
    case "$token" in
      ""|find|path|paths|repo|this|that|only|return|min*|context|possible|the|use|using|token|reduction|workflow)
        continue
        ;;
    esac
    if [[ ${#token} -ge 4 ]]; then
      tokens+=("$token")
    fi
    [[ ${#tokens[@]} -ge 5 ]] && break
  done < <(printf '%s' "$lowered" | tr -cs '[:alnum:]_.-' '\n')

  if [[ ${#tokens[@]} -eq 0 ]]; then
    printf '%s' "$QUERY"
    return 0
  fi

  local pattern="${tokens[0]}"
  local i
  for ((i = 1; i < ${#tokens[@]}; i++)); do
    pattern="${pattern}|${tokens[i]}"
  done
  printf '%s' "$pattern"
}

collection_fingerprint() {
  local globs ext listed path stat_payload
  globs=()
  for ext in "${QMD_EXTENSION_LIST[@]}"; do
    ext="${ext//[[:space:]]/}"
    [[ -z "$ext" ]] && continue
    globs+=(-g "*.${ext}")
  done
  globs+=("${FINGERPRINT_EXCLUDES[@]}")

  listed="$(
    cd "$REPO_ROOT" &&
      rg --files "${globs[@]}" . 2>/dev/null | sort || true
  )"
  if [[ -z "$listed" ]]; then
    printf '%s' "empty"
    return 0
  fi

  while IFS= read -r path; do
    path="${path#./}"
    [[ -z "$path" ]] && continue
    if [[ -f "$REPO_ROOT/$path" ]]; then
      stat_payload="$(stat -c '%Y\t%s' "$REPO_ROOT/$path" 2>/dev/null || true)"
      [[ -n "$stat_payload" ]] && printf '%s\t%s\n' "$path" "$stat_payload"
    fi
  done <<<"$listed" | sort | sha1sum | cut -d' ' -f1
}

stamp_is_fresh() {
  local stamp_path="$1"
  local ttl_seconds="$2"
  local now_s mtime_s

  if [[ "${ttl_seconds:-0}" -le 0 ]]; then
    return 1
  fi
  if [[ ! -f "$stamp_path" ]]; then
    return 1
  fi
  now_s="$(date +%s)"
  mtime_s="$(stat -c '%Y' "$stamp_path" 2>/dev/null || printf '0')"
  [[ "$mtime_s" =~ ^[0-9]+$ ]] || return 1
  (( now_s - mtime_s <= ttl_seconds ))
}

sanitize_qmd_files_output() {
  local raw_output="$1"
  local filtered_output
  local filter_pattern

  if [[ -z "$raw_output" || "$raw_output" == "No results found." ]]; then
    printf '%s\n' "$raw_output"
    return 0
  fi

  filter_pattern='qmd://[^,]+/(tools/token-reduce-skill/|\.worktrees/|node_modules/)'
  if [[ "$PREFER_SCRIPT_CONTENT" -eq 0 ]]; then
    filter_pattern='qmd://[^,]+/(tools/token-reduce-skill/|\.worktrees/|node_modules/|artifacts/token-reduction/|references/benchmarks/|scripts/benchmark-)'
  fi

  filtered_output="$(printf '%s\n' "$raw_output" | rg -v "$filter_pattern" | head -8 || true)"
  if [[ -n "$filtered_output" ]]; then
    printf '%s\n' "$filtered_output"
    return 0
  fi

  printf '%s\n' "$raw_output"
}

ensure_qmd_collection() {
  local current_fingerprint existing_fingerprint
  mkdir -p "$QMD_STAMP_DIR"

  if qmd collection list 2>/dev/null | grep -q "$QMD_COLLECTION_EXISTS_REGEX"; then
    if stamp_is_fresh "$QMD_STAMP_PATH" "$QMD_REFRESH_TTL_SECONDS"; then
      debug "[token-reduce-search] using fresh qmd stamp (ttl=${QMD_REFRESH_TTL_SECONDS}s)"
      return 0
    fi
  fi

  current_fingerprint="$(collection_fingerprint)"
  existing_fingerprint=""
  if [[ -f "$QMD_STAMP_PATH" ]]; then
    existing_fingerprint="$(<"$QMD_STAMP_PATH")"
  fi

  if qmd collection list 2>/dev/null | grep -q "$QMD_COLLECTION_EXISTS_REGEX" && [[ "$current_fingerprint" == "$existing_fingerprint" ]]; then
    return 0
  fi

  if qmd collection list 2>/dev/null | grep -q "$QMD_COLLECTION_EXISTS_REGEX"; then
    debug "[token-reduce-search] refreshing qmd collection ${COLLECTION_NAME}"
    qmd collection remove "$COLLECTION_NAME" >/dev/null 2>&1 || true
  else
    debug "[token-reduce-search] indexing repo docs and source files for qmd collection ${COLLECTION_NAME}"
  fi

  if ! qmd collection add "$REPO_ROOT" --name "$COLLECTION_NAME" --mask "$QMD_MASK" >/dev/null 2>&1; then
    if qmd collection list 2>/dev/null | grep -q "$QMD_COLLECTION_EXISTS_REGEX"; then
      printf '%s' "$current_fingerprint" >"$QMD_STAMP_PATH"
      return 0
    fi
    return 1
  fi

  printf '%s' "$current_fingerprint" >"$QMD_STAMP_PATH"
  return 0
}

filter_candidates() {
  if [[ "$PREFER_SCRIPT_CONTENT" -eq 1 ]]; then
    cat
    return 0
  fi

  rg -v '(^|/)(scripts/benchmark-[^/]+\.py|references/benchmarks/|artifacts/token-reduction/)(:|$)' || true
}

ranked_content_paths() {
  awk -F: '{count[$1]++} END {for (f in count) print count[f] "\t" f}' | sort -rn | cut -f2- | head -20
}

filter_hook_candidates() {
  if [[ "$NEEDS_HOOK_FOCUS" -eq 1 ]]; then
    rg -v '(^|/)(measure_token_reduction|benchmark-token-reduction-workflow|benchmark-token-reduction-agents|baseline-measurement|summarize_token_reduction|install-token-reduction-cron|token-reduce-(paths|search|snippet)|remind-token-reduce)\.(py|sh)(:|$)' || true
  else
    cat
  fi
}

path_hits() {
  local pattern
  pattern="$(path_pattern)"
  if [[ -n "$GLOB" ]]; then
    rg --files "${DEFAULT_EXCLUDES[@]}" -g "$GLOB" . 2>/dev/null | rg -i -e "$pattern" | filter_candidates | head -20 || true
  else
    rg --files "${DEFAULT_EXCLUDES[@]}" . 2>/dev/null | rg -i -e "$pattern" | filter_candidates | head -20 || true
  fi
}

content_hits() {
  local pattern="$QUERY"
  if [[ "$NEEDS_PATH_HINT" -eq 1 || "$PREFER_SCRIPT_CONTENT" -eq 1 ]]; then
    pattern="$(content_pattern)"
  fi
  if [[ -n "$GLOB" ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" -g "$GLOB" . | filter_candidates | filter_hook_candidates | ranked_content_paths || true
  elif [[ "$PREFER_SKILL_SCRIPTS" -eq 1 ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" scripts | filter_candidates | filter_hook_candidates | ranked_content_paths || true
  elif [[ "$NEEDS_PATH_HINT" -eq 1 ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" -g '*.py' -g '*.sh' . | filter_candidates | filter_hook_candidates | ranked_content_paths || true
  else
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" . | filter_candidates | filter_hook_candidates | ranked_content_paths || true
  fi
}

snippet_hits() {
  local pattern="$QUERY"
  if [[ "$NEEDS_PATH_HINT" -eq 1 || "$PREFER_SCRIPT_CONTENT" -eq 1 ]]; then
    pattern="$(content_pattern)"
  fi
  if [[ -n "$GLOB" ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" -g "$GLOB" . | filter_candidates | head -40 || true
  elif [[ "$PREFER_SKILL_SCRIPTS" -eq 1 ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" scripts | filter_candidates | head -40 || true
  elif [[ "$NEEDS_PATH_HINT" -eq 1 ]]; then
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" -g '*.py' -g '*.sh' . | filter_candidates | head -40 || true
  else
    rg -n -i -e "$pattern" "${DEFAULT_EXCLUDES[@]}" . | filter_candidates | head -40 || true
  fi
}

fallback_paths() {
  local paths contents
  paths="$(path_hits)"
  contents="$(content_hits)"

  if [[ -n "$paths" ]]; then
    printf '%s\n' "$paths"
    return 0
  fi

  if [[ -n "$contents" ]]; then
    printf '%s\n' "$contents"
    return 0
  fi

  echo "No results found."
}

fallback_snippets() {
  local paths snippets
  paths="$(path_hits)"
  snippets="$(snippet_hits)"

  if [[ -n "$paths" ]]; then
    printf '%s\n' "$paths"
  fi

  if [[ -n "$snippets" ]]; then
    [[ -n "$paths" ]] && echo
    printf '%s\n' "$snippets"
    return 0
  fi

  if [[ -z "$paths" ]]; then
    echo "No results found."
  fi
}

PATH_HINTS=""
CONTENT_HINTS=""
if [[ "$NEEDS_PATH_HINT" -eq 1 ]]; then
  if [[ "$PREFER_SKILL_SCRIPTS" -eq 0 ]]; then
    PATH_HINTS="$(path_hits)"
  fi
  if [[ -z "$PATH_HINTS" ]]; then
    CONTENT_HINTS="$(content_hits)"
  fi
elif [[ "$PREFER_SKILL_SCRIPTS" -eq 1 && "$PREFER_SCRIPT_CONTENT" -eq 1 ]]; then
  CONTENT_HINTS="$(content_hits)"
fi

if command -v qmd >/dev/null 2>&1; then
  if [[ "$NEEDS_PATH_HINT" -eq 1 && -n "$PATH_HINTS" ]]; then
    debug "[token-reduce-search] rg path hits"
    printf '%s\n' "$PATH_HINTS"

    if [[ "$MODE" == "snippets" ]]; then
      echo
      fallback_snippets
    fi
    exit 0
  fi

  if [[ "$NEEDS_PATH_HINT" -eq 1 && -n "$CONTENT_HINTS" ]]; then
    debug "[token-reduce-search] rg content hits"
    printf '%s\n' "$CONTENT_HINTS"

    if [[ "$MODE" == "snippets" ]]; then
      echo
      fallback_snippets
    fi
    exit 0
  fi

  if [[ "$PREFER_SKILL_SCRIPTS" -eq 1 && "$PREFER_SCRIPT_CONTENT" -eq 1 && -n "$CONTENT_HINTS" ]]; then
    debug "[token-reduce-search] rg content hits"
    printf '%s\n' "$CONTENT_HINTS"

    if [[ "$MODE" == "snippets" ]]; then
      echo
      fallback_snippets
    fi
    exit 0
  fi

  if ! ensure_qmd_collection; then
    warn "[token-reduce-search] qmd collection add failed; falling back to rg"
    cd "$REPO_ROOT"
    if [[ "$MODE" == "snippets" ]]; then
      fallback_snippets
    else
      fallback_paths
    fi
    exit 0
  fi

  debug "[token-reduce-search] qmd search --files (${COLLECTION_NAME})"
  QMD_FILES_OUTPUT="$(sanitize_qmd_files_output "$(qmd search "$QUERY" -n 20 --files -c "$COLLECTION_NAME" || true)")"

  if [[ -n "$QMD_FILES_OUTPUT" && "$QMD_FILES_OUTPUT" != "No results found." ]]; then
    printf '%s\n' "$QMD_FILES_OUTPUT"
    if [[ "$NEEDS_PATH_HINT" -eq 1 ]]; then
      if [[ -n "$PATH_HINTS" ]]; then
        echo
        debug "[token-reduce-search] rg path hits"
        printf '%s\n' "$PATH_HINTS"
      fi
    fi

    if [[ "$MODE" == "snippets" ]]; then
      echo
      debug "[token-reduce-search] qmd search snippet (${COLLECTION_NAME})"
      qmd search "$QUERY" -n 1 -c "$COLLECTION_NAME" || true
    fi
    exit 0
  fi

  warn "[token-reduce-search] qmd had no hits, falling back to rg"
  if [[ "$MODE" == "snippets" ]]; then
    echo
    fallback_snippets
  elif [[ "$NEEDS_PATH_HINT" -eq 1 ]]; then
    echo
    fallback_snippets
  else
    fallback_paths
  fi
  exit 0
fi

warn "[token-reduce-search] qmd unavailable, falling back to scoped rg"
cd "$REPO_ROOT"
if [[ "$MODE" == "snippets" ]]; then
  fallback_snippets
else
  fallback_paths
fi
