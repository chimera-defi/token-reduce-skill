#!/usr/bin/env bash
# Run benchmark suite for major change sets and emit a keep/drop gate verdict.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

echo "[token-reduce] running release benchmark gate..."
env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken \
  "$SCRIPT_DIR/benchmark-composite-stack.py"
env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken \
  "$SCRIPT_DIR/benchmark-adaptive-tiering.py"
env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken \
  "$SCRIPT_DIR/benchmark-profile-presets.py"

echo "[token-reduce] evaluating keep/drop gate..."
uv run "$SCRIPT_DIR/release-change-gate.py" "$@"
