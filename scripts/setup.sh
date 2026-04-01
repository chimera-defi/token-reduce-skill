#!/usr/bin/env bash
# token-reduce full setup — installs QMD, RTK, and wires both sets of hooks.
# Run once per machine. Safe to re-run.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}✔${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BIN_DIR="${HOME}/.local/bin"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_SKILL_DIR="${CODEX_HOME_DIR}/skills/token-reduce"

mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

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

# ── Install token-reduce enforcement hooks globally ───────────────────────────
HOOK_INSTALL_DIR="$HOME/.claude/hooks/token-reduce"
mkdir -p "$HOOK_INSTALL_DIR"

for f in token_reduce_state.py token_reduce_telemetry.py remind-token-reduce.py enforce-token-reduce-first.py; do
  cp "$REPO_ROOT/scripts/$f" "$HOOK_INSTALL_DIR/$f"
done
ok "token-reduce hook scripts installed to $HOOK_INSTALL_DIR"

python3 - <<'PYEOF'
import json, pathlib

settings_path = pathlib.Path.home() / ".claude" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

hook_dir = str(pathlib.Path.home() / ".claude" / "hooks" / "token-reduce")
remind_cmd = f"uv run {hook_dir}/remind-token-reduce.py"
enforce_cmd = f"uv run {hook_dir}/enforce-token-reduce-first.py"

hooks = settings.setdefault("hooks", {})

ups = hooks.setdefault("UserPromptSubmit", [])
remind_entry = {"hooks": [{"type": "command", "command": remind_cmd}]}
if not any(h.get("hooks", [{}])[0].get("command") == remind_cmd for h in ups if h.get("hooks")):
    ups.append(remind_entry)

ptu = hooks.setdefault("PreToolUse", [])
for matcher in ("Bash", "Glob", "Grep", "Read"):
    enforce_entry = {"matcher": matcher, "hooks": [{"type": "command", "command": enforce_cmd}]}
    if not any(
        h.get("matcher") == matcher and any(hh.get("command") == enforce_cmd for hh in h.get("hooks", []))
        for h in ptu
    ):
        ptu.append(enforce_entry)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print("patched ~/.claude/settings.json with token-reduce global hooks")
PYEOF
ok "global Claude Code hooks patched"

# ── Global helper wrappers for any repo ───────────────────────────────────────
write_wrapper() {
  local target_name="$1"
  local target_path="$2"
  rm -f "$BIN_DIR/$target_name"
  cat >"$BIN_DIR/$target_name" <<EOF
#!/usr/bin/env bash
exec "$target_path" "\$@"
EOF
  chmod +x "$BIN_DIR/$target_name"
}

write_wrapper "token-reduce-paths" "$REPO_ROOT/scripts/token-reduce-paths.sh"
write_wrapper "token-reduce-snippet" "$REPO_ROOT/scripts/token-reduce-snippet.sh"
write_wrapper "token-reduce-manage" "$REPO_ROOT/scripts/token-reduce-manage.sh"
write_wrapper "token-reduce-setup" "$REPO_ROOT/scripts/setup.sh"
write_wrapper "token-reduce-structural" "$REPO_ROOT/scripts/token-reduce-structural.py"
ok "global helper wrappers linked in $BIN_DIR"

# ── Codex global skill install ────────────────────────────────────────────────
mkdir -p "${CODEX_HOME_DIR}/skills"
if [[ -L "$CODEX_SKILL_DIR" || ! -e "$CODEX_SKILL_DIR" ]]; then
  ln -sfn "$REPO_ROOT" "$CODEX_SKILL_DIR"
  ok "Codex skill linked at $CODEX_SKILL_DIR"
else
  EXISTING_REALPATH="$(cd "$CODEX_SKILL_DIR" && pwd)"
  REPO_REALPATH="$(cd "$REPO_ROOT" && pwd)"
  if [[ "$EXISTING_REALPATH" == "$REPO_REALPATH" ]]; then
    ok "Codex skill already installed at $CODEX_SKILL_DIR"
  else
    warn "Codex skill path already exists at $CODEX_SKILL_DIR and points elsewhere; inspect manually"
  fi
fi

# ── Index this repo in QMD ────────────────────────────────────────────────────
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
echo "  global wrappers     →  token-reduce-paths / token-reduce-snippet from any repo"
echo "  Codex skill link    →  $CODEX_SKILL_DIR"
echo ""
echo "Restart Claude Code for hook changes to take effect."
