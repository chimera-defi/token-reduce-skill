# Codex New-Context Handoff

Use this when you want to continue work in a new Codex conversation without losing token-reduce setup discipline.

## Copy-paste prompt

```text
Continue this task in a fresh Codex context.

Run exactly:
set -euo pipefail
if [ -d "/absolute/path/to/token-reduce-skill/.git" ]; then
  cd "/absolute/path/to/token-reduce-skill"
elif [ -d "tools/token-reduce-skill/.git" ]; then
  cd tools/token-reduce-skill
elif [ -d "tools/token-reduce-skill" ]; then
  cd tools/token-reduce-skill
else
  git clone https://github.com/chimera-defi/token-reduce-skill tools/token-reduce-skill
  cd tools/token-reduce-skill
fi

./scripts/setup.sh

# Optional (only if needed for output-heavy / large-repo structural tasks):
# TOKEN_REDUCE_INSTALL_EXTENDED_STACK=1 ./scripts/setup.sh

validate_status=0
./scripts/token-reduce-manage.sh validate || validate_status=$?
echo "validate_exit_code=${validate_status}"

token-reduce-paths token reduce | head -5

Then report:
1) bootstrap result
2) validate result (exit code + key stderr if non-zero)
3) blockers with exact failing command + stderr
```

## One-command generator

From this repo root:

```bash
./scripts/token-reduce-manage.sh handoff-codex
```

That prints the same handoff block with your current absolute repo path filled in.
