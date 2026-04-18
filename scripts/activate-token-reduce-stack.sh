#!/usr/bin/env bash
# One-command activation for the measured token-reduce stack.
# Enables optional companions, installs/wires hooks, and runs package validation.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

echo "[token-reduce] activating measured stack..."
TOKEN_REDUCE_INSTALL_EXTENDED_STACK=1 "$SCRIPT_DIR/setup.sh"

echo "[token-reduce] validating package..."
"$SCRIPT_DIR/token-reduce-manage.sh" validate

echo "[token-reduce] stack activation complete."
echo "next:"
echo "  ./scripts/token-reduce-manage.sh deps-check"
echo "  ./scripts/token-reduce-manage.sh benchmark-composite"
