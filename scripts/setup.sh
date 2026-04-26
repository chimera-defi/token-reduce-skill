#!/usr/bin/env bash
# token-reduce full setup — installs QMD, RTK, AXI companions, and wires hooks.
# Optional extended companions can be enabled with TOKEN_REDUCE_INSTALL_EXTENDED_STACK=1.
# Run once per machine. Safe to re-run.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}✔${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!${NC} %s\n" "$*"; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BIN_DIR="${HOME}/.local/bin"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_SKILLS_DIR="${CODEX_HOME_DIR}/skills"
CODEX_SKILL_DIR="${CODEX_SKILLS_DIR}/token-reduce"
AGENTS_SKILLS_DIR="${HOME}/.agents/skills"
TOKEN_SAVIOR_PY="${HOME}/.local/share/token-savior/.venv/bin/python"
EXTENDED_STACK="${TOKEN_REDUCE_INSTALL_EXTENDED_STACK:-0}"
QMD_EXTENSION_FILE="${REPO_ROOT}/scripts/qmd-file-extensions.txt"
QMD_EXTENSIONS_DEFAULT="md,txt,rst,py,sh,bash,zsh,js,jsx,ts,tsx,mjs,cjs,json,yml,yaml,toml,ini,cfg,go,rs,java,rb,php"
if [[ -f "$QMD_EXTENSION_FILE" ]]; then
  QMD_EXTENSIONS_DEFAULT="$(tr -d '[:space:]' <"$QMD_EXTENSION_FILE")"
fi
QMD_EXTENSIONS="${TOKEN_REDUCE_QMD_EXTENSIONS:-$QMD_EXTENSIONS_DEFAULT}"
QMD_MASK_DEFAULT="**/*.{${QMD_EXTENSIONS}}"
QMD_MASK="${TOKEN_REDUCE_QMD_MASK:-$QMD_MASK_DEFAULT}"

mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

# ── QMD (BM25 search backend) ─────────────────────────────────────────────────
if command -v qmd >/dev/null 2>&1; then
  qmd_version="$(qmd --version 2>/dev/null | head -1 || true)"
  if [[ -z "$qmd_version" || "$qmd_version" == Usage:* ]]; then
    qmd_version="installed"
  fi
  ok "qmd already installed ($qmd_version)"
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

# ── AXI companion CLIs (agent-native GitHub/browser interfaces) ──────────────
if command -v gh-axi >/dev/null 2>&1 && command -v chrome-devtools-axi >/dev/null 2>&1; then
  ok "AXI companions already installed (gh-axi/chrome-devtools-axi)"
else
  if command -v npm >/dev/null 2>&1; then
    if npm install -g gh-axi chrome-devtools-axi >/dev/null 2>&1; then
      ok "AXI companions installed (gh-axi/chrome-devtools-axi)"
    else
      warn "AXI companion install failed — run 'npm install -g gh-axi chrome-devtools-axi' manually"
    fi
  else
    warn "npm not found — skipping AXI companion install (needs gh-axi/chrome-devtools-axi)"
  fi
fi

# ── Optional extended companions (context-mode + code-review-graph) ───────────
if [[ "$EXTENDED_STACK" == "1" ]]; then
  if command -v context-mode >/dev/null 2>&1; then
    ok "context-mode already installed ($(context-mode --version 2>/dev/null | head -1 || echo installed))"
  else
    if command -v npm >/dev/null 2>&1; then
      if npm install -g context-mode >/dev/null 2>&1; then
        ok "context-mode installed"
      else
        warn "context-mode install failed — run 'npm install -g context-mode' manually"
      fi
    else
      warn "npm not found — skipping context-mode install"
    fi
  fi

  if command -v code-review-graph >/dev/null 2>&1; then
    ok "code-review-graph already installed ($(code-review-graph --version 2>/dev/null | head -1 || echo installed))"
  else
    if command -v uv >/dev/null 2>&1; then
      if uv tool install code-review-graph >/dev/null 2>&1 || uv tool install --upgrade code-review-graph >/dev/null 2>&1; then
        ok "code-review-graph installed"
      else
        warn "code-review-graph install failed — run 'uv tool install code-review-graph' manually"
      fi
    elif command -v pipx >/dev/null 2>&1; then
      if pipx install code-review-graph >/dev/null 2>&1 || pipx upgrade code-review-graph >/dev/null 2>&1; then
        ok "code-review-graph installed"
      else
        warn "code-review-graph install failed — run 'pipx install code-review-graph' manually"
      fi
    else
      warn "uv/pipx not found — skipping code-review-graph install"
    fi
  fi
fi

# ── Install token-reduce enforcement hooks globally ───────────────────────────
HOOK_INSTALL_DIR="$HOME/.claude/hooks/token-reduce"
mkdir -p "$HOOK_INSTALL_DIR"

for f in token_reduce_state.py token_reduce_telemetry.py remind-token-reduce.py enforce-token-reduce-first.py; do
  cp "$REPO_ROOT/scripts/$f" "$HOOK_INSTALL_DIR/$f"
done
ok "token-reduce hook scripts installed to $HOOK_INSTALL_DIR"

# Write a self-contained update-check wrapper with REPO_ROOT baked in at install time.
# SessionStart hooks cannot resolve PATH reliably, so we use the absolute repo path.
cat > "$HOOK_INSTALL_DIR/token-reduce-update-check.sh" << SHEOF
#!/usr/bin/env bash
# Auto-generated by token-reduce setup.sh — do not edit manually.
# Checks for token-reduce updates and prints a notification if behind.
exec uv run "$REPO_ROOT/scripts/token-reduce-update-check.py" --notify "\$@"
SHEOF
chmod +x "$HOOK_INSTALL_DIR/token-reduce-update-check.sh"
ok "update-check hook written to $HOOK_INSTALL_DIR/token-reduce-update-check.sh"

UPDATE_CHECK_CMD="$HOOK_INSTALL_DIR/token-reduce-update-check.sh"

uv run python - <<PYEOF
import json, pathlib

settings_path = pathlib.Path.home() / ".claude" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

hook_dir = str(pathlib.Path.home() / ".claude" / "hooks" / "token-reduce")
remind_cmd = f"uv run {hook_dir}/remind-token-reduce.py"
enforce_cmd = f"uv run {hook_dir}/enforce-token-reduce-first.py"
update_cmd = "${UPDATE_CHECK_CMD}"

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

ss = hooks.setdefault("SessionStart", [])
if not any(
    any(hh.get("command") == update_cmd for hh in entry.get("hooks", []))
    for entry in ss
):
    ss.append({"hooks": [{"type": "command", "command": update_cmd}]})

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print("patched ~/.claude/settings.json with token-reduce global hooks")
PYEOF
ok "global Claude Code hooks patched (UserPromptSubmit + PreToolUse + SessionStart)"

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
write_wrapper "token-reduce-adaptive" "$REPO_ROOT/scripts/token-reduce-adaptive.sh"
write_wrapper "token-reduce-manage" "$REPO_ROOT/scripts/token-reduce-manage.sh"
write_wrapper "token-reduce-setup" "$REPO_ROOT/scripts/setup.sh"
write_wrapper "token-reduce-settings" "$REPO_ROOT/scripts/token-reduce-settings.py"
write_wrapper "token-reduce-telemetry-sync" "$REPO_ROOT/scripts/token-reduce-telemetry-sync.py"
write_wrapper "token-reduce-updates" "$REPO_ROOT/scripts/token-reduce-update-check.py"
if [[ -x "$TOKEN_SAVIOR_PY" ]]; then
  rm -f "$BIN_DIR/token-reduce-structural"
  cat >"$BIN_DIR/token-reduce-structural" <<EOF
#!/usr/bin/env bash
exec "$TOKEN_SAVIOR_PY" "$REPO_ROOT/scripts/token-reduce-structural.py" "\$@"
EOF
  chmod +x "$BIN_DIR/token-reduce-structural"
  ok "token-reduce-structural wrapper bound to token-savior venv ($TOKEN_SAVIOR_PY)"
else
  write_wrapper "token-reduce-structural" "$REPO_ROOT/scripts/token-reduce-structural.py"
  warn "token-savior venv not found at $TOKEN_SAVIOR_PY (structural helper may require manual install)"
fi
ok "global helper wrappers linked in $BIN_DIR"

# ── Codex global skill install ────────────────────────────────────────────────
mkdir -p "$CODEX_SKILLS_DIR"
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

ensure_codex_companion_link() {
  local skill_name="$1"
  local source_dir="$2"
  local target_dir="${CODEX_SKILLS_DIR}/${skill_name}"
  if [[ ! -d "$source_dir" ]]; then
    warn "Companion skill not found locally: $source_dir"
    return
  fi

  if [[ -L "$target_dir" || ! -e "$target_dir" ]]; then
    ln -sfn "$source_dir" "$target_dir"
    ok "Codex companion skill linked: $skill_name"
    return
  fi

  if [[ -f "$target_dir/SKILL.md" ]]; then
    ok "Codex companion skill already installed: $skill_name"
    return
  fi

  local existing_realpath
  local source_realpath
  existing_realpath="$(cd "$target_dir" && pwd)"
  source_realpath="$(cd "$source_dir" && pwd)"
  if [[ "$existing_realpath" == "$source_realpath" ]]; then
    ok "Codex companion skill already linked: $skill_name"
  else
    warn "Codex companion skill path exists and points elsewhere: $target_dir"
  fi
}

for companion_skill in axi caveman caveman-cn caveman-es compress; do
  ensure_codex_companion_link "$companion_skill" "$AGENTS_SKILLS_DIR/$companion_skill"
done

# ── Index this repo in QMD ────────────────────────────────────────────────────
COLLECTION="repo-$(printf '%s' "$REPO_ROOT" | sha1sum | cut -c1-12)"
if command -v qmd >/dev/null 2>&1; then
  index_started="$(date +%s)"
  if qmd collection add "$REPO_ROOT" --name "$COLLECTION" --mask "$QMD_MASK" >/dev/null 2>&1; then
    index_elapsed="$(( $(date +%s) - index_started ))"
    ok "qmd collection indexed ($COLLECTION) with docs+code mask in ${index_elapsed}s"
  elif qmd collection list 2>/dev/null | grep -qE "^${COLLECTION}[[:space:]]"; then
    ok "qmd collection already indexed ($COLLECTION)"
  else
    warn "qmd collection add failed — run manually: qmd collection add . --name $COLLECTION --mask \"$QMD_MASK\""
  fi
fi

# ── Telemetry opt-in onboarding (gstack-style prompt) ────────────────────────
if [[ "${TOKEN_REDUCE_SETUP_TELEMETRY_PROMPT:-1}" != "0" ]]; then
  if [[ -t 0 ]]; then
    onboard_args=(onboard)
    if [[ -n "${TOKEN_REDUCE_TELEMETRY_ENDPOINT:-}" ]]; then
      onboard_args+=(--endpoint "$TOKEN_REDUCE_TELEMETRY_ENDPOINT")
    fi
    uv run "$REPO_ROOT/scripts/token-reduce-settings.py" "${onboard_args[@]}" \
      || warn "telemetry onboarding prompt failed"
  elif [[ -n "${TOKEN_REDUCE_TELEMETRY_OPT_IN:-}" || -n "${TOKEN_REDUCE_TELEMETRY_ENDPOINT:-}" ]]; then
    onboard_args=(onboard --non-interactive)
    case "${TOKEN_REDUCE_TELEMETRY_OPT_IN,,}" in
      1|true|yes|y) onboard_args+=(--yes) ;;
      0|false|no|n) onboard_args+=(--no) ;;
    esac
    if [[ -n "${TOKEN_REDUCE_TELEMETRY_ENDPOINT:-}" ]]; then
      onboard_args+=(--endpoint "$TOKEN_REDUCE_TELEMETRY_ENDPOINT")
    fi
    uv run "$REPO_ROOT/scripts/token-reduce-settings.py" "${onboard_args[@]}" \
      || warn "non-interactive telemetry onboarding failed"
  fi
fi

echo ""
echo "Setup complete. What each layer does:"
echo "  token-reduce hooks  →  block wasteful discovery before it happens"
echo "  RTK hook            →  compress output of commands that do run"
echo "  QMD                 →  BM25 search backend for path helpers"
echo "  AXI companions      →  gh-axi / chrome-devtools-axi for lower-turn tool usage"
if [[ "$EXTENDED_STACK" == "1" ]]; then
  echo "  extended companions →  context-mode + code-review-graph install attempt enabled"
fi
echo "  global wrappers     →  token-reduce-adaptive / token-reduce-paths / token-reduce-snippet from any repo"
echo "  Codex skill link    →  $CODEX_SKILL_DIR"
echo "  companion links     →  axi / caveman / compress under $CODEX_SKILLS_DIR"
echo "  opt-in telemetry    →  prompted now or run token-reduce-settings onboard"
echo "  receive metrics     →  uv run scripts/token-reduce-telemetry-receiver.py --host 0.0.0.0 --port 8787"
echo "  dependency checks   →  token-reduce-manage deps-check / token-reduce-manage deps-update"
echo "  update checks       →  token-reduce-manage updates / token-reduce-manage auto-update"
echo ""
echo "Restart Claude Code for hook changes to take effect."
