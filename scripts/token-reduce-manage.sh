#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
usage: ./scripts/token-reduce-manage.sh <command>

commands:
  activate-stack  One-command activation (setup + extended companions + validate)
  handoff-codex  Print a ready-to-paste Codex fresh-context handoff block
  benchmark   Run the local output-size benchmark
  benchmark-adaptive  Benchmark adaptive tier routing vs baseline paths helper
  benchmark-profiles  Benchmark minimal-load/balanced/max-savings routing presets
  sync-benchmarks  Sync README benchmark token rows from benchmark artifacts
  benchmark-context-mode-intake  Validate and benchmark context-mode companion intake
  benchmark-code-review-graph-intake  Validate and benchmark code-review-graph companion intake
  benchmark-token-optimizer-intake  Benchmark token-optimizer-mcp wrapper against token-reduce discovery tasks
  release-gate  Run benchmark suite + keep/drop verdict for major change sets
  checkpoint  Run the full checkpoint suite and write audit artifacts
  test-adaptive  Run unit tests for adaptive tier routing decisions
  composite   Generate composite telemetry (token-reduce + RTK + wiring)
  benchmark-composite  Run the composite stack benchmark
  deps-check  Check core dependency freshness (qmd + rtk)
  deps-check-conditional  Check conditional companion freshness (AXI/context-mode/code-review-graph)
  deps-update  Update core dependencies when possible
  deps-update-conditional  Update conditional companions when possible
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
  activate-stack)
    exec "$SCRIPT_DIR/activate-token-reduce-stack.sh"
    ;;
  handoff-codex)
    exec "$SCRIPT_DIR/codex-handoff.sh"
    ;;
  benchmark)
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-token-reduce.py"
    ;;
  benchmark-adaptive)
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-adaptive-tiering.py"
    ;;
  benchmark-profiles)
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-profile-presets.py"
    ;;
  sync-benchmarks)
    exec uv run "$SCRIPT_DIR/sync-benchmark-readme.py" --repo-root "$SCRIPT_DIR/.."
    ;;
  benchmark-context-mode-intake)
    if [[ -z "${CONTEXT_MODE_REPO:-}" ]]; then
      echo "set CONTEXT_MODE_REPO to a local context-mode clone path" >&2
      exit 2
    fi
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run "$SCRIPT_DIR/benchmark-context-mode-intake.py" --context-mode-repo "$CONTEXT_MODE_REPO"
    ;;
  benchmark-code-review-graph-intake)
    if [[ -z "${CODE_REVIEW_GRAPH_REPO:-}" ]]; then
      echo "set CODE_REVIEW_GRAPH_REPO to a local code-review-graph clone path" >&2
      exit 2
    fi
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run "$SCRIPT_DIR/benchmark-code-review-graph-intake.py" --code-review-graph-repo "$CODE_REVIEW_GRAPH_REPO"
    ;;
  benchmark-token-optimizer-intake)
    if [[ -z "${TOKEN_OPTIMIZER_REPO:-}" ]]; then
      echo "set TOKEN_OPTIMIZER_REPO to a local token-optimizer-mcp clone path" >&2
      exit 2
    fi
    exec env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-token-optimizer-intake.py" --repo-root "$PWD" --token-optimizer-repo "$TOKEN_OPTIMIZER_REPO"
    ;;
  release-gate)
    exec "$SCRIPT_DIR/release-gate.sh" "$@"
    ;;
  checkpoint)
    exec uv run "$SCRIPT_DIR/checkpoint_gate.py" --repo-root "$SCRIPT_DIR/.."
    ;;
  test-adaptive)
    exec uv run --with pytest pytest -q "$SCRIPT_DIR/tests/test_token_reduce_adaptive.py"
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
  deps-check-conditional)
    exec uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" --include-conditional
    ;;
  deps-update)
    exec uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" --apply
    ;;
  deps-update-conditional)
    exec uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" --include-conditional --apply
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
