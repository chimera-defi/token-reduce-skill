# token-reduce

Canonical usage is in `SKILL.md`. In Codex there is no subagent API: if the candidate set stays broad after two discovery passes, ask the user to narrow the scope.

If the path is unknown, start discovery with `./scripts/token-reduce-paths.sh topic words` (or `token-reduce-snippet.sh` for one ranked excerpt), then use scoped `rg` and targeted reads. Do not start with `rg --files`, repo-wide `rg -n`, `find .`, `ls -R` or `grep -R`. This applies when editing this repo too.

Before merging, run `bash tests/test_e2e.sh`.
