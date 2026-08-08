#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Update-check preamble (check_on_manage) ──────────────────────────────────
# Reads check_on_manage from config (default: true). Uses --no-fetch so it's
# instant (relies on git state from the SessionStart hook fetch). Silent when
# up to date; prints a one-line notification when behind.
_maybe_update_check() {
  local cfg=""
  local enabled="true"
  if command -v uv >/dev/null 2>&1; then
    cfg="$(uv run "$SCRIPT_DIR/token_reduce_config.py" --path 2>/dev/null || true)"
  fi
  if [[ -n "$cfg" && -f "$cfg" ]] && command -v uv >/dev/null 2>&1; then
    enabled=$(uv run python -c "
import json, sys
try:
    c = json.load(open('$cfg'))
    print('true' if c.get('updates', {}).get('check_on_manage', True) else 'false')
except Exception:
    print('true')
" 2>/dev/null || echo "true")
  fi
  if [[ "$enabled" == "true" ]]; then
    uv run "$SCRIPT_DIR/token-reduce-update-check.py" \
      --notify --quiet-if-current --no-fetch >/dev/null || true
  fi
}
# Skip preamble for meta/setup commands where it would be redundant or noisy
case "${1:-}" in
  updates|auto-update|workspace-auto-update|activate-stack|handoff-codex|''|-h|--help|help)
    ;;
  *)
    _maybe_update_check
    ;;
esac

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
  caliper-summary  Summarize a running Cost Caliper Control Tower API
  cost-playbook  Compare current controls against the Databricks AI coding cost playbook
  release-gate  Run benchmark suite + keep/drop verdict for major change sets
  checkpoint  Run the full checkpoint suite and write audit artifacts
  test-adaptive  Run unit tests for adaptive tier routing decisions
  composite   Generate composite telemetry (token-reduce + RTK + wiring)
  benchmark-composite  Run the composite stack benchmark
  deps-check  Check core dependency freshness (qmd + rtk)
  deps-check-conditional  Check conditional companion freshness (AXI/context-mode/headroom/code-review-graph)
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
  improve-adoption  Build workspace helper-usage SLO report and prioritized interventions
  workspace-install  Install skill links and token-reduce routing guidance across sibling repos
  setup         Interactive setup wizard (auto-detect delegates/companions, save config)
  delegate-health  Check installed/missing status for each configured delegate and companion
  tools         List all available tools with enabled/disabled status from config
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
  caliper-summary)
    exec uv run "$SCRIPT_DIR/caliper_summary.py" "$@"
    ;;
  cost-playbook)
    exec uv run "$SCRIPT_DIR/cost_playbook.py" "$@"
    ;;
  release-gate)
    exec "$SCRIPT_DIR/release-gate.sh" "$@"
    ;;
  checkpoint)
    exec uv run "$SCRIPT_DIR/checkpoint_gate.py" --repo-root "$SCRIPT_DIR/.."
    ;;
  test-adaptive)
    exec uv run --with pytest pytest -q "$SCRIPT_DIR/tests"
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
    exec uv run "$SCRIPT_DIR/review_token_reduction.py" --scope repo "$@"
    ;;
  review-global)
    exec uv run "$SCRIPT_DIR/review_token_reduction.py" --scope global "$@"
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
    ADOPTION_REPORT_JSON="$OUT_DIR/adoption-improvement-$DATE_STAMP.json"
    ADOPTION_REPORT_MD="$OUT_DIR/adoption-improvement-$DATE_STAMP.md"
    CALIPER_JSON="$OUT_DIR/caliper-summary-$DATE_STAMP.json"
    CALIPER_MD="$OUT_DIR/caliper-summary-$DATE_STAMP.md"
    mkdir -p "$OUT_DIR"
    CFG_PATH="$(uv run "$SCRIPT_DIR/token_reduce_config.py" --path 2>/dev/null || true)"
    WORKSPACE_ROOT="/home/agents/workspace"
    WORKSPACE_DAYS="30"
    TELEMETRY_SYNC_TIMEOUT="45"
    CALIPER_ENABLED="true"
    CALIPER_SELF_IMPROVE="true"
    CALIPER_URL="${CALIPER_URL:-http://127.0.0.1:49123}"
    if [[ -n "$CFG_PATH" && -f "$CFG_PATH" ]]; then
      WORKSPACE_ROOT="$(uv run python -c "import json; c=json.load(open('$CFG_PATH')); print(c.get('telemetry', {}).get('workspace_root') or '/home/agents/workspace')" 2>/dev/null || echo "$WORKSPACE_ROOT")"
      WORKSPACE_DAYS="$(uv run python -c "import json; c=json.load(open('$CFG_PATH')); print(c.get('telemetry', {}).get('workspace_days') or 30)" 2>/dev/null || echo "$WORKSPACE_DAYS")"
      TELEMETRY_SYNC_TIMEOUT="$(uv run python -c "import json; c=json.load(open('$CFG_PATH')); print(c.get('telemetry', {}).get('self_improve_sync_timeout_seconds') or 45)" 2>/dev/null || echo "$TELEMETRY_SYNC_TIMEOUT")"
      CALIPER_ENABLED="$(uv run python -c "import json; c=json.load(open('$CFG_PATH')); print('true' if c.get('companions', {}).get('caliper', {}).get('enabled', True) else 'false')" 2>/dev/null || echo "$CALIPER_ENABLED")"
      CALIPER_SELF_IMPROVE="$(uv run python -c "import json; c=json.load(open('$CFG_PATH')); print('true' if c.get('companions', {}).get('caliper', {}).get('self_improve', True) else 'false')" 2>/dev/null || echo "$CALIPER_SELF_IMPROVE")"
      CALIPER_URL="$(uv run python -c "import json, os; c=json.load(open('$CFG_PATH')); print(os.environ.get('CALIPER_URL') or c.get('companions', {}).get('caliper', {}).get('url') or 'http://127.0.0.1:49123')" 2>/dev/null || echo "$CALIPER_URL")"
    fi
    if [[ ! -d "$WORKSPACE_ROOT" ]]; then
      WORKSPACE_ROOT="/home/agents/workspace"
    fi

    env TOKEN_REDUCE_TELEMETRY_CONTEXT=benchmark uv run --with tiktoken "$SCRIPT_DIR/benchmark-composite-stack.py"
    uv run "$SCRIPT_DIR/token-reduce-dependency-health.py" || true
    "$SCRIPT_DIR/baseline-measurement.sh" --scope global
    CALIPER_REVIEW_ARGS=()
    if [[ "$CALIPER_ENABLED" == "true" && "$CALIPER_SELF_IMPROVE" == "true" ]]; then
      if uv run "$SCRIPT_DIR/caliper_summary.py" \
        --url "$CALIPER_URL" \
        --output-json "$CALIPER_JSON" \
        --output-md "$CALIPER_MD" >/dev/null; then
        CALIPER_REVIEW_ARGS=(--caliper-summary-json "$CALIPER_JSON")
        echo "caliper summary snapshot: $CALIPER_JSON"
      else
        echo "caliper summary unavailable at $CALIPER_URL; continuing without spend telemetry" >&2
      fi
    fi
    uv run "$SCRIPT_DIR/review_token_reduction.py" --scope global "${CALIPER_REVIEW_ARGS[@]}"
    uv run "$SCRIPT_DIR/audit_workspace_skills.py" \
      --workspace-root "$WORKSPACE_ROOT" \
      --days "$WORKSPACE_DAYS" \
      --output "$WORKSPACE_AUDIT" >/dev/null
    uv run "$SCRIPT_DIR/adoption_report.py" \
      --audit-json "$WORKSPACE_AUDIT" \
      --output-json "$ADOPTION_REPORT_JSON" \
      --output-md "$ADOPTION_REPORT_MD" >/dev/null
    if ! timeout "${TELEMETRY_SYNC_TIMEOUT}s" uv run "$SCRIPT_DIR/token-reduce-telemetry-sync.py"; then
      echo "telemetry sync skipped or timed out after ${TELEMETRY_SYNC_TIMEOUT}s; continuing" >&2
    fi
    uv run "$SCRIPT_DIR/rolling_baseline_report.py" \
      --output-json "$OUT_DIR/rolling-baseline-$DATE_STAMP.json" \
      --output-md "$OUT_DIR/rolling-baseline-$DATE_STAMP.md" >/dev/null
    uv run "$SCRIPT_DIR/token-reduce-update-check.py" --notify
    echo "workspace audit snapshot: $WORKSPACE_AUDIT"
    echo "adoption improvement report: $ADOPTION_REPORT_MD"
    ;;
  workspace-audit)
    exec uv run "$SCRIPT_DIR/audit_workspace_skills.py" "$@"
    ;;
  improve-adoption)
    ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
    OUT_DIR="$ROOT/artifacts/token-reduction"
    DATE_STAMP="$(date +%Y-%m-%d)"
    mkdir -p "$OUT_DIR"
    OUTPUT_JSON="$OUT_DIR/adoption-improvement-$DATE_STAMP.json"
    OUTPUT_MD="$OUT_DIR/adoption-improvement-$DATE_STAMP.md"
    exec uv run "$SCRIPT_DIR/adoption_report.py" \
      --output-json "$OUTPUT_JSON" \
      --output-md "$OUTPUT_MD" \
      "$@"
    ;;
  workspace-install)
    exec uv run "$SCRIPT_DIR/install_workspace_skill.py" "$@"
    ;;
  setup)
    exec uv run python3 "$SCRIPT_DIR/token_reduce_setup_wizard.py" "$@"
    ;;
  delegate-health)
    # O2: check installed/missing for each configured delegate and companion
    printf 'Delegates:\n'
    for _delegate in devin kimi grok spark; do
      _cmd="${_delegate}-delegate"
      if command -v "$_cmd" >/dev/null 2>&1; then
        _status="installed"
      else
        _status="not found"
      fi
      printf '  %-12s  %s\n' "$_cmd" "$_status"
    done
    printf 'Companions:\n'
    for _tool in headroom qmd gbrain caveman; do
      if command -v "$_tool" >/dev/null 2>&1; then
        _status="installed"
      else
        _status="not found"
      fi
      printf '  %-12s  %s\n' "$_tool" "$_status"
    done
    ;;
  tools)
    # O5: list all tools with enabled/disabled status from config
    exec uv run python3 "$SCRIPT_DIR/token_reduce_config.py" --list-tools
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
