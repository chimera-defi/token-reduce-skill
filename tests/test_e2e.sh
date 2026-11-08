#!/usr/bin/env bash
# e2e: real rg, real hook stdin, temp repo + temp HOME. Run: bash tests/test_e2e.sh
set -u
S="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
T="$(cd "$T" && pwd -P)"; fails=0
ok() { echo "PASS $1"; }; bad() { echo "FAIL $1 ${2:-}"; fails=$((fails+1)); }
chk() { local n="$1"; shift; if "$@"; then ok "$n"; else bad "$n"; fi; }

H="$T/home"; R="$H/workspace/proj"; mkdir -p "$R/src" "$R/docs" "$H/workspace/agent-memory" "$H/workspace/secrets" "$H/workspace/x-holdout" "$H/real"
echo 'def send_message(): pass' > "$R/src/session_send.py"; echo 'session timers' > "$R/docs/timers.md"
echo 'readme: the quokka marker' > "$R/README.md"; echo 'send timers' > "$R/docs/send_timers_notes.md"
for d in agent-memory secrets x-holdout; do echo 'send_message timers quokka' > "$H/workspace/$d/n.md"; done
echo 'send_message timers' > "$H/workspace/proj/top.md"
git -C "$R" init -q && git -C "$R" add -A
ln -s "$H/real" "$H/linkdir"; ln -s "$H/real" "$H/workspace/linkdir"
B="$T/bin"; mkdir "$B"; for n in paths snippet adaptive; do ln -s "$S/token-reduce.sh" "$B/token-reduce-$n.sh"; done
ln -s "$S/token-reduce.sh" "$B/mystery"
run() { (cd "$R" && HOME="$H" "$@"); }

out="$(run "$B/token-reduce-paths.sh" send timers)"
[[ "$(sed -n 1p <<<"$out")" == ./docs/send_timers_notes.md ]] && ok "ranks 2-word path first" || bad "ranking" "$out"
chk "path hit found" grep -q './src/session_send.py' <<<"$out"
chk "content-only hit" grep -q './README.md' <<<"$(run "$B/token-reduce-paths.sh" quokka)"
out="$(run "$B/token-reduce-paths.sh" zzzqqq; echo "rc=$?")"
[[ $out == *"No results found."*"rc=0" ]] && ok "no results rc0" || bad "no results" "$out"
run "$B/token-reduce-paths.sh" --help >/dev/null; chk "--help rc0" test $? -eq 0
chk "snippet file:line" grep -q '^src/session_send.py:1:def send_message' <<<"$(run "$B/token-reduce-snippet.sh" send_message)"
chk "adaptive alias" grep -q './README.md' <<<"$(run "$B/token-reduce-adaptive.sh" quokka)"
chk "verb arg" grep -q './README.md' <<<"$(run "$S/token-reduce.sh" paths quokka)"
run "$B/mystery" x 2>/dev/null; chk "unknown basename rc2" test $? -eq 2
for r in "$H/workspace" "$H"; do
  out="$(cd "$r" && HOME="$H" "$B/token-reduce-paths.sh" send_message timers quokka 2>/dev/null)"
  chk "aggregate abs paths ($r)" grep -q "^$H/workspace/proj/" <<<"$out"
  chk "aggregate no private ($r)" bash -c '! grep -Eqi "agent-memory|secrets|holdout" <<<"$1"' _ "$out"
done

hook() { HOME="$H" python3 "$S/symlink-find-hint.py"; }
bash_in() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$1" | hook; }
chk "hook non-Bash silent" test -z "$(echo '{"tool_name":"Read","tool_input":{"command":"find '"$H"'/linkdir"}}' | hook)"
chk "hook ls silent" test -z "$(bash_in 'ls -la')"
out="$(bash_in "find $H/linkdir -name x")"
chk "hook symlink hint" python3 -c 'import json,sys; assert "additionalContext" in json.loads(sys.argv[1])["hookSpecificOutput"]' "$out"
chk "hook trailing slash silent" test -z "$(bash_in "find $H/linkdir/ -name x")"
chk "hook -L silent" test -z "$(bash_in "find -L $H/linkdir")"
chk "hook real dir silent" test -z "$(bash_in "find $H/real -name x")"
chk "hook ~ expands" grep -q additionalContext <<<"$(bash_in 'find ~/linkdir -name x')"
chk "hook \$HOME + rtk + chain" grep -q additionalContext <<<"$(bash_in 'cd /tmp && rtk find $HOME/linkdir -type f | head')"
chk "hook bash -c nested" grep -q additionalContext <<<"$(bash_in "bash -c 'ls \$(find $H/linkdir -maxdepth 2)'")"
echo 'garbage{' | hook >"$T/g.out"; chk "hook garbage rc0 silent" test $? -eq 0 -a ! -s "$T/g.out"

D="$T/dhome"; mkdir -p "$D/skill/scripts"
SKILL_ROOT="$D/skill" HOME="$D" bash "$S/deploy.sh" --apply >/dev/null
for f in .local/bin/token-reduce-paths .local/bin/token-reduce-adaptive .local/bin/token-reduce-manage .claude/hooks/token-reduce/symlink-find-hint.py; do
  chk "deploy installed $f" test -x "$D/$f"
done
chk "deploy wrapper content" grep -q "$D/skill/scripts/token-reduce-paths.sh" "$D/.local/bin/token-reduce-paths"
chk "deploy 2nd dry-run no diff" test -z "$(SKILL_ROOT="$D/skill" HOME="$D" bash "$S/deploy.sh" --dry-run)"
echo "# changed" >> "$D/.local/bin/token-reduce-paths"
SKILL_ROOT="$D/skill" HOME="$D" bash "$S/deploy.sh" --apply >/dev/null
chk "deploy backs up overwritten" test -f "$D"/backups/token-reduce-*/token-reduce-paths
[[ $fails -eq 0 ]] && echo "ALL PASS" || echo "$fails FAILED"; exit $((fails>0))
