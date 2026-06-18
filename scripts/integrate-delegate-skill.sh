#!/usr/bin/env bash
# Integrate the delegate-skill router (devin / kimi / grok / spark) for token-reduce.
# delegate-skill is the single entry point: its setup.sh installs and links all four
# delegate wrappers and injects the global routing block. token-reduce no longer wires
# individual delegate skills directly.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }

# Resolve the delegate-skill repo. Override with DELEGATE_SKILL_REPO.
DELEGATE_SKILL_REPO="${DELEGATE_SKILL_REPO:-}"
if [[ -z "$DELEGATE_SKILL_REPO" ]]; then
  for candidate in \
    "$HOME/.claude/skills/delegate-skill" \
    "$HOME/.agents/skills/delegate-skill" \
    "${WORKSPACE:-$HOME/workspace}/delegate-skill"; do
    if [[ -f "$candidate/setup.sh" ]]; then
      DELEGATE_SKILL_REPO="$candidate"
      break
    fi
  done
fi

if [[ -z "$DELEGATE_SKILL_REPO" || ! -f "$DELEGATE_SKILL_REPO/setup.sh" ]]; then
  warn "delegate-skill repo not found (set DELEGATE_SKILL_REPO or clone it)"
  warn "  git clone https://github.com/chimera-defi/delegate-skill \"\$HOME/.claude/skills/delegate-skill\""
  exit 2
fi

ok "delegate-skill repo: $DELEGATE_SKILL_REPO"
bash "$DELEGATE_SKILL_REPO/setup.sh"
ok "delegate-skill router integrated (devin / kimi / grok / spark)"
