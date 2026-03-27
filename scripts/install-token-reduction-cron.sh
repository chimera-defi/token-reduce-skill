#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
MEASURE_CMD="cd $ROOT && ./scripts/baseline-measurement.sh --scope repo >> ./artifacts/token-reduction/cron.log 2>&1"
SUMMARY_CMD="cd $ROOT && uv run ./scripts/summarize_token_reduction.py >> ./artifacts/token-reduction/cron.log 2>&1"

mkdir -p "$ROOT/artifacts/token-reduction"
touch "$ROOT/artifacts/token-reduction/cron.log"

CURRENT="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "$CURRENT" | sed '/# token-reduction-etc-mono-repo/d;/baseline-measurement.sh --scope repo/d;/summarize_token_reduction.py/d')"

{
  printf '%s\n' "$FILTERED"
  echo "# token-reduction-etc-mono-repo"
  echo "15 9 * * * $MEASURE_CMD"
  echo "30 9 * * 1 $SUMMARY_CMD"
} | crontab -

echo "Installed cron entries:"
crontab -l | rg 'token-reduction-etc-mono-repo|scripts/baseline-measurement.sh --scope repo|scripts/summarize_token_reduction.py'
