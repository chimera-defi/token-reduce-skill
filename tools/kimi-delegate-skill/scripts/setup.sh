#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR" "$HOME/.agents/skills" "$HOME/.openclaw/skills" "${CODEX_HOME:-$HOME/.codex}/skills"

ln -sfn "$SKILL_ROOT" "$HOME/.agents/skills/kimi-delegate"
ln -sfn "$HOME/.agents/skills/kimi-delegate" "$HOME/.openclaw/skills/kimi-delegate"
ln -sfn "$SKILL_ROOT" "${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"

cat > "$BIN_DIR/kimi-delegate" <<WRAP
#!/usr/bin/env bash
exec "$SKILL_ROOT/scripts/delegate.py" "\$@"
WRAP
chmod +x "$BIN_DIR/kimi-delegate"

echo "kimi-delegate installed"
echo "  agents:  $HOME/.agents/skills/kimi-delegate"
echo "  openclaw:$HOME/.openclaw/skills/kimi-delegate"
echo "  codex:   ${CODEX_HOME:-$HOME/.codex}/skills/kimi-delegate"
echo "  bin:     $BIN_DIR/kimi-delegate"
