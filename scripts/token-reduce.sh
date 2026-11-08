#!/usr/bin/env bash
# token-reduce: path finder. Verbs: paths, snippet. Deps: bash, rg, coreutils, git.
set -u
usage() { echo "usage: token-reduce-paths <words...> | token-reduce-snippet <words...>
Lists up to 20 candidate files, 10 plus file:line hits for snippet (./rel in a repo; absolute at \$HOME or ~/workspace)."; }
name="$(basename "$0")"
case "${1:-}" in
  paths|snippet) verb="$1"; shift ;;
  *) case "$name" in
       *snippet*) verb=snippet ;;
       *paths*|*adaptive*) verb=paths ;;
       *) echo "token-reduce: '$name' was removed; use token-reduce-paths <words>" >&2; exit 2 ;;
     esac ;;
esac
case "${1:-}" in -h|--help) usage; exit 0 ;; esac
[[ $# -gt 0 ]] || { usage >&2; exit 2; }
query="$*"
top=20; [[ $verb == snippet ]] && top=10

stop=" find path paths repo this that only return the and for with use using script scripts file files where how "
words=()
while IFS= read -r w; do
  [[ ${#w} -ge 3 && $stop != *" $w "* ]] && words+=("$w")
done < <(printf '%s' "${query,,}" | tr -cs 'a-z0-9_.-' '\n' | awk '!s[$0]++')
words=("${words[@]:0:6}")
pat=()
if [[ ${#words[@]} -eq 0 ]]; then pat=(-e "$query"); else for w in "${words[@]}"; do pat+=(-e "$w"); done; fi

root="${TOKEN_REDUCE_REPO_ROOT:-}"
[[ -n $root ]] || root="$(git rev-parse --show-toplevel 2>/dev/null)" || root="$PWD"
root="$(cd "$root" 2>/dev/null && pwd -P)" || root="$PWD"
home="$(cd "$HOME" 2>/dev/null && pwd -P)" || home="$HOME"

private_dirs=(agent-memory secrets .ssh .gnupg .codex .claude .config .local .cache state private node_modules .git venv .venv venvs .venvs env .env virtualenv .virtualenv)
private() {
  local d
  [[ ${1,,} != *holdout* ]] || return 0
  for d in "${private_dirs[@]}"; do [[ /$1/ == */$d/* ]] && return 0; done
  return 1
}

aggregate() {
  local scan="$home" depth=3 ws f size name inputs=() ex=()
  echo "token-reduce: aggregate root '$root': bounded search, private dirs excluded; cd into a repo (or set TOKEN_REDUCE_REPO_ROOT) to narrow" >&2
  if [[ -d $home/workspace ]]; then
    ws="$(cd "$home/workspace" && pwd -P)" || return 0
    if [[ $ws != "$home" ]] && ! private "$ws"; then scan="$ws"; inputs+=("$scan"); fi
  fi
  if [[ $root == "$home" ]]; then
    for f in "$home"/*.md; do
      [[ -f $f && ! -L $f ]] || continue
      private "$f" && continue
      size="$(stat -c %s -- "$f" 2>/dev/null)" || continue
      [[ $size =~ ^[0-9]+$ && $size -le 1048576 ]] || continue
      inputs+=("$f")
    done
  fi
  [[ ${#inputs[@]} -gt 0 ]] || return 0
  [[ $scan != "$home" ]] || depth=1
  for name in "${private_dirs[@]}"; do ex+=(--iglob "!$name"); done
  (
    cd "$scan" || exit 0
    timeout 20 rg --no-config --no-ignore --hidden --no-follow -l -i -F --max-depth "$depth" --max-filesize 1M \
      -g '*.md' -g '*.toml' -g '*.json' -g '*.sh' -g '*.py' "${ex[@]}" --iglob '!*holdout*' --color never \
      "${pat[@]}" -- "${inputs[@]}" | head -n 20
  )
}

if [[ $root == "$home" || $root == "$home/workspace" ]]; then
  out="$(aggregate)"
  [[ -n $out ]] && printf '%s\n' "$out" || echo "No results found."
  exit 0
fi

cd "$root" || exit 1
# content search skips big and data files so logs cannot outrank code on raw hit count
cx=(--max-filesize 1M -g '!artifacts/token-reduction/**' -g '!*.{jsonl,ndjson,log,csv,tsv}')
list="$(
  {
    timeout 20 rg --files -g '!artifacts/token-reduction/**' 2>/dev/null \
      | TR_Q="${query,,}" awk -v ws="${words[*]}" 'BEGIN{n=split(ws,w," "); if(!n){w[1]=ENVIRON["TR_Q"];n=1}}
          {p=tolower($0); s=0; for(i=1;i<=n;i++) if(index(p,w[i])) s++; if(s) printf "P\t%d\t%s\n", s, $0}'
    timeout 20 rg -c -i -F --no-messages "${cx[@]}" "${pat[@]}" 2>/dev/null </dev/null \
      | sed 's/^\(.*\):\([0-9][0-9]*\)$/C\t\2\t\1/'
  } | sort -s -t$'\t' -k1,1r -k2,2nr \
    | awk -F'\t' '!seen[$3]++ {print "./" $3}' | head -n "$top"
)"
[[ -n $list ]] || { echo "No results found."; exit 0; }
printf '%s\n' "$list"
if [[ $verb == snippet ]]; then
  echo
  timeout 20 rg -n -i -F --no-messages --max-columns 200 "${cx[@]}" "${pat[@]}" 2>/dev/null </dev/null | head -n 40
fi
exit 0
