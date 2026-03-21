#!/usr/bin/env bash
# token-reduce full setup — installs QMD, RTK, and wires both sets of hooks.
# Run once per machine. Safe to re-run.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}✔${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }

# ── QMD (BM25 search backend) ─────────────────────────────────────────────────
if command -v qmd >/dev/null 2>&1; then
  ok "qmd already installed ($(qmd --version 2>/dev/null || echo 'unknown version'))"
else
  if command -v bun >/dev/null 2>&1; then
    bun install -g https://github.com/tobi/qmd
    ok "qmd installed"
  else
    warn "bun not found — skipping qmd install. Install bun first: https://bun.sh then re-run this script."
  fi
fi

# ── RTK (command output compressor) ──────────────────────────────────────────
if command -v rtk >/dev/null 2>&1; then
  ok "rtk already installed ($(rtk --version 2>/dev/null | head -1))"
else
  if command -v brew >/dev/null 2>&1; then
    brew install rtk
  else
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
    # Add to PATH for this session if installed to ~/.local/bin
    export PATH="$HOME/.local/bin:$PATH"
  fi
  ok "rtk installed"
fi

# ── Wire RTK hook into Claude Code (global, graceful if rtk missing) ─────────
if command -v rtk >/dev/null 2>&1; then
  rtk init --global --auto-patch >/dev/null 2>&1 && ok "rtk hook wired (global ~/.claude/settings.json)" \
    || warn "rtk init failed — run 'rtk init -g' manually"
else
  warn "rtk not in PATH after install — run 'rtk init -g' manually after adding rtk to PATH"
fi

# ── Index this repo in QMD ────────────────────────────────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
COLLECTION="repo-$(printf '%s' "$REPO_ROOT" | sha1sum | cut -c1-12)"
if command -v qmd >/dev/null 2>&1; then
  qmd collection add "$REPO_ROOT" --name "$COLLECTION" --mask '**/*.md' >/dev/null 2>&1 \
    && ok "qmd collection indexed ($COLLECTION)" \
    || warn "qmd collection add failed — run manually: qmd collection add . --name $COLLECTION --mask '**/*.md'"
fi

echo ""
echo "Setup complete. What each layer does:"
echo "  token-reduce hooks  →  block wasteful discovery before it happens"
echo "  RTK hook            →  compress output of commands that do run"
echo "  QMD                 →  BM25 search backend for path helpers"
echo ""
echo "Restart Claude Code for hook changes to take effect."
