#!/usr/bin/env bash
# Install token-reduce hook + PATH wrappers on the live host. Manual; idempotent.
# Usage: deploy.sh [--dry-run|--apply]. Does not edit settings.json or crontab.
set -eu
mode="${1:---dry-run}"
case "$mode" in --dry-run|--apply) ;; *) echo "usage: $0 [--dry-run|--apply]" >&2; exit 2 ;; esac
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="${SKILL_ROOT:-$(readlink -f "$HOME/.claude/skills/token-reduce")}"
bak="$HOME/backups/token-reduce-$(date +%Y%m%d-%H%M%S)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
targets=("$here/symlink-find-hint.py:$HOME/.claude/hooks/token-reduce/symlink-find-hint.py")
for n in paths snippet adaptive; do
  printf '#!/usr/bin/env bash\nexec "%s/scripts/token-reduce-%s.sh" "$@"\n' "$skill" "$n" > "$tmp/w-$n"
  targets+=("$tmp/w-$n:$HOME/.local/bin/token-reduce-$n")
done
for n in manage settings setup structural telemetry-sync updates; do
  printf '#!/usr/bin/env bash\necho "token-reduce-%s was removed (2026-11-08 shrink); use token-reduce-paths <words>" >&2\nexit 2\n' "$n" > "$tmp/w-$n"
  targets+=("$tmp/w-$n:$HOME/.local/bin/token-reduce-$n")
done
for t in "${targets[@]}"; do
  src="${t%%:*}"; dst="${t#*:}"
  if [[ -f $dst ]] && cmp -s "$src" "$dst"; then continue; fi
  if [[ $mode == --dry-run ]]; then
    echo "== $dst"; diff -u "$([[ -f $dst ]] && echo "$dst" || echo /dev/null)" "$src" || true; continue
  fi
  if [[ -e $dst ]]; then mkdir -p "$bak"; cp -p "$dst" "$bak/$(basename "$dst")"; fi
  mkdir -p "$(dirname "$dst")"; rm -f "$dst"; cp "$src" "$dst"; chmod +x "$dst"; echo "installed $dst"
done
