#!/usr/bin/env bash
# Integrate standalone kimi-delegate-skill as a token-reduce companion.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}✔${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }

KIMI_DELEGATE_REPO="${KIMI_DELEGATE_REPO:-/root/.openclaw/workspace/dev/kimi-delegate-skill}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"

if [[ ! -d "$KIMI_DELEGATE_REPO" ]]; then
  warn "standalone repo not found: $KIMI_DELEGATE_REPO"
  warn "clone it first: git clone https://github.com/chimera-defi/kimi-delegate-skill \"$KIMI_DELEGATE_REPO\""
  exit 2
fi

mkdir -p "$HOME/.agents/skills" "$HOME/.openclaw/skills" "$CODEX_HOME_DIR/skills"

ln -sfn "$KIMI_DELEGATE_REPO" "$HOME/.agents/skills/kimi-delegate"
ln -sfn "$HOME/.agents/skills/kimi-delegate" "$HOME/.openclaw/skills/kimi-delegate"
ln -sfn "$KIMI_DELEGATE_REPO" "$CODEX_HOME_DIR/skills/kimi-delegate"

ok "linked standalone companion skill into .agents/.openclaw/.codex"

if [[ "${KIMI_DELEGATE_WORKSPACE_INSTALL:-1}" == "1" ]]; then
  if [[ -x "$KIMI_DELEGATE_REPO/scripts/install_workspace_skill.py" ]]; then
    "$KIMI_DELEGATE_REPO/scripts/install_workspace_skill.py" --force-relink >/dev/null || warn "workspace relink reported issues"
    ok "workspace relink executed from standalone repo"
  else
    warn "workspace installer missing at $KIMI_DELEGATE_REPO/scripts/install_workspace_skill.py"
  fi
fi

ok "kimi-delegate companion integration complete"
