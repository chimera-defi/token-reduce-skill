#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
usage: ./scripts/token-reduce-manage.sh <command>

commands:
  benchmark   Run the local output-size benchmark
  composite   Generate composite telemetry (token-reduce + RTK + wiring)
  measure     Measure repo-local adoption and write artifacts
  review      Generate the telemetry-driven self-review
  validate    Validate the skill package shape
  telemetry   Summarize recent helper/hook telemetry
EOF
}

cmd="${1:-}"
case "$cmd" in
  benchmark)
    exec uv run --with tiktoken "$SCRIPT_DIR/benchmark-token-reduce.py"
    ;;
  composite)
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
    OUT_DIR="$ROOT/artifacts/token-reduction"
    DATE_STAMP="$(date +%Y-%m-%d)"
    OUTPUT="$OUT_DIR/composite-repo-$DATE_STAMP.json"
    OUTPUT_MD="$OUT_DIR/composite-repo-$DATE_STAMP.md"
    mkdir -p "$OUT_DIR"
    exec uv run "$SCRIPT_DIR/composite_token_telemetry.py" \
      --scope repo \
      --repo-root "$ROOT" \
      --output "$OUTPUT" \
      --output-md "$OUTPUT_MD"
    ;;
  measure)
    exec "$SCRIPT_DIR/baseline-measurement.sh" --scope repo
    ;;
  review)
    exec uv run "$SCRIPT_DIR/review_token_reduction.py" --scope repo
    ;;
  validate)
    exec uv run "$SCRIPT_DIR/validate_skill_package.py"
    ;;
  telemetry)
    exec uv run "$SCRIPT_DIR/token_reduce_telemetry.py" summary --days 14
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
