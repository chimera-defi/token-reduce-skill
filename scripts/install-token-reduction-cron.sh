#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
SELF_IMPROVE_CMD="cd $ROOT && ./scripts/token-reduce-manage.sh self-improve >> ./artifacts/token-reduction/cron-weekly.log 2>&1"
TELEMETRY_SYNC_CMD="cd $ROOT && ./scripts/token-reduce-manage.sh telemetry-sync >> ./artifacts/token-reduction/cron-weekly.log 2>&1"

mkdir -p "$ROOT/artifacts/token-reduction"
touch "$ROOT/artifacts/token-reduction/cron-weekly.log"

CURRENT="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "$CURRENT" | sed '/# token-reduction-etc-mono-repo/d;/# token-reduction-weekly-maintenance/d;/baseline-measurement.sh --scope repo/d;/summarize_token_reduction.py/d;/token-reduce-manage.sh self-improve/d;/token-reduce-manage.sh telemetry-sync/d')"

{
  printf '%s\n' "$FILTERED"
  echo "# token-reduction-weekly-maintenance"
  echo "15 9 * * 1 $SELF_IMPROVE_CMD"
  echo "45 9 * * 1 $TELEMETRY_SYNC_CMD"
} | crontab -

echo "Installed cron entries:"
crontab -l | rg 'token-reduction-weekly-maintenance|token-reduce-manage.sh self-improve|token-reduce-manage.sh telemetry-sync'
