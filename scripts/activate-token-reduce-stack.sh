#!/usr/bin/env bash
# One-command activation for the measured token-reduce stack.
# Core-only by default (qmd + rtk + hooks). Optional companions can be enabled explicitly.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ACTIVATE_EXTENDED="${TOKEN_REDUCE_ACTIVATE_EXTENDED_STACK:-0}"

echo "[token-reduce] activating measured stack..."
if [[ "$ACTIVATE_EXTENDED" == "1" ]]; then
  TOKEN_REDUCE_INSTALL_EXTENDED_STACK=1 "$SCRIPT_DIR/setup.sh"
  echo "[token-reduce] extended companion install enabled"
else
  "$SCRIPT_DIR/setup.sh"
  echo "[token-reduce] core-only activation enabled (set TOKEN_REDUCE_ACTIVATE_EXTENDED_STACK=1 for optional companions)"
fi

echo "[token-reduce] validating package..."
"$SCRIPT_DIR/token-reduce-manage.sh" validate

echo "[token-reduce] stack activation complete."
echo "next:"
echo "  ./scripts/token-reduce-manage.sh deps-check"
echo "  ./scripts/token-reduce-manage.sh deps-check-conditional"
echo "  ./scripts/token-reduce-manage.sh benchmark-composite"
