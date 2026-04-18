#!/usr/bin/env bash
# Print a ready-to-paste Codex handoff block for a fresh context.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"

cat <<EOF
# Codex New-Context Handoff (token-reduce)

Copy this entire block into a new Codex context:

\`\`\`text
Continue work in token-reduce with a fresh context on this machine.
Bootstrap the stack first, then report status.

Run exactly:
set -euo pipefail
if [ -d "$REPO_ROOT/.git" ]; then
  cd "$REPO_ROOT"
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
./scripts/token-reduce-manage.sh validate || validate_status=\$?
echo "validate_exit_code=\${validate_status}"

token-reduce-paths token reduce | head -5

Then report:
1) bootstrap result
2) validate result (exit code + key stderr if non-zero)
3) blockers with exact failing command + stderr
\`\`\`
EOF
