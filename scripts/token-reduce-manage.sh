#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
usage: ./scripts/token-reduce-manage.sh <command>

commands:
  benchmark   Run the local output-size benchmark
  composite   Generate composite telemetry (token-reduce + RTK + wiring)
  benchmark-composite  Run the composite stack benchmark
  deps-check  Check underlying companion/dependency freshness
  deps-update  Apply companion/dependency updates when possible
  measure     Measure repo-local adoption and write artifacts
  measure-global  Measure global adoption across local session logs
  review      Generate the telemetry-driven self-review
  review-global   Generate the telemetry-driven self-review for global scope
  validate    Validate the skill package shape
  doctor      Run a compact health pass (validate + deps + updates + settings)
  telemetry   Summarize recent helper/hook telemetry
  settings    Show/set/reset local config (telemetry and updates)
  telemetry-sync  Run opt-in telemetry snapshot and optional upload
  rolling-baseline  Generate rolling pre/post trend report from telemetry snapshots
  updates     Check for updates and print status
  auto-update Safely fast-forward update when eligible (optionally sync workspace by config)
  workspace-auto-update  Fast-forward + force-relink workspace + version/commit drift audit
  self-improve  Run benchmark + telemetry + review + update check
  workspace-audit  Audit skill install and doc adoption across sibling repos
  workspace-install  Install skill links and token-reduce routing guidance across sibling repos
EOF
}

cmd="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi
case "$cmd" in
  benchmark)
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-token-reduce.py"
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
  benchmark-composite)
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-composite-stack.py"
    ;;
  deps-check)
    exec uv run "$SCRIPT_DIR/token-reduce-dependency-health.py"
    ;;
  deps-update)
    exec uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" --apply
    ;;
  measure)
    exec "$SCRIPT_DIR/baseline-measurement.sh" --scope repo
    ;;
  measure-global)
    exec "$SCRIPT_DIR/baseline-measurement.sh" --scope global
    ;;
  review)
    exec uv run "$SCRIPT_DIR/review_token_reduction.py" --scope repo
    ;;
  review-global)
    exec uv run "$SCRIPT_DIR/review_token_reduction.py" --scope global
    ;;
  validate)
    uv run "$SCRIPT_DIR/validate_skill_package.py"
    exec uv run "$SCRIPT_DIR/validate-benchmark-artifacts.py"
    ;;
  doctor)
    exec uv run "$SCRIPT_DIR/token-reduce-doctor.py" "$@"
    ;;
  telemetry)
    exec uv run "$SCRIPT_DIR/token_reduce_telemetry.py" summary --days 14
    ;;
  settings)
    if [[ $# -eq 0 ]]; then
      set -- show
    fi
    exec uv run "$SCRIPT_DIR/token-reduce-settings.py" "$@"
    ;;
  telemetry-sync)
    exec uv run "$SCRIPT_DIR/token-reduce-telemetry-sync.py" "$@"
    ;;
  rolling-baseline)
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
    OUT_DIR="$ROOT/artifacts/token-reduction"
    DATE_STAMP="$(date +%Y-%m-%d)"
    mkdir -p "$OUT_DIR"
    exec uv run "$SCRIPT_DIR/rolling_baseline_report.py" \
      --output-json "$OUT_DIR/rolling-baseline-$DATE_STAMP.json" \
      --output-md "$OUT_DIR/rolling-baseline-$DATE_STAMP.md" \
      "$@"
    ;;
  updates)
    exec uv run "$SCRIPT_DIR/token-reduce-update-check.py" --notify "$@"
    ;;
  auto-update)
    exec uv run "$SCRIPT_DIR/token-reduce-update-check.py" --notify --auto-update "$@"
    ;;
  workspace-auto-update)
    exec uv run "$SCRIPT_DIR/token-reduce-update-check.py" --notify --auto-update --workspace-sync "$@"
    ;;
  self-improve)
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
    OUT_DIR="$ROOT/artifacts/token-reduction"
    DATE_STAMP="$(date +%Y-%m-%d)"
    WORKSPACE_AUDIT="$OUT_DIR/workspace-audit-$DATE_STAMP.json"
    mkdir -p "$OUT_DIR"

    env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-composite-stack.py"
    uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" || true
    "$SCRIPT_DIR/baseline-measurement.sh" --scope global
    uv run "$SCRIPT_DIR/review_token_reduction.py" --scope global
    uv run "$SCRIPT_DIR/audit_workspace_skills.py" --days 30 --output "$WORKSPACE_AUDIT" >/dev/null
    uv run "$SCRIPT_DIR/token-reduce-telemetry-sync.py" || true
    uv run "$SCRIPT_DIR/rolling_baseline_report.py" \
      --output-json "$OUT_DIR/rolling-baseline-$DATE_STAMP.json" \
      --output-md "$OUT_DIR/rolling-baseline-$DATE_STAMP.md" >/dev/null
    uv run "$SCRIPT_DIR/token-reduce-update-check.py" --notify
    echo "workspace audit snapshot: $WORKSPACE_AUDIT"
    ;;
  workspace-audit)
    exec uv run "$SCRIPT_DIR/audit_workspace_skills.py" "$@"
    ;;
  workspace-install)
    exec uv run "$SCRIPT_DIR/install_workspace_skill.py" "$@"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
