# Graphify Orchestration Tracking

## Goal

Trial a removable top-level orchestration layer that can use `graphify` when it is explicitly enabled and likely helpful, while preserving token-reduce defaults.

## Scope Added

- New wrapper: `scripts/token-reduce-orchestrate.sh`
- No required dependency added.
- Default behavior remains token-reduce helper fallback.

## How It Works

`token-reduce-orchestrate.sh` routes by policy:

1. Try `graphify` only when all conditions are true:
   - `TOKEN_REDUCE_ENABLE_GRAPHIFY=1`
   - `graphify` binary exists, or `TOKEN_REDUCE_GRAPHIFY_UV_DIR` points at a repo where `uv run --directory <dir> graphify` works
   - graph file exists (`TOKEN_REDUCE_GRAPH_PATH`, default `graphify-out/graph.json`)
   - query looks symbol-like (camelCase / underscore / `::` single token)
2. If graphify has no match or errors, fall back to token-reduce helper.
3. Fallback mode is configurable:
   - `TOKEN_REDUCE_ORCH_FALLBACK=paths` (default)
   - `TOKEN_REDUCE_ORCH_FALLBACK=snippet`
4. Wrapper logs telemetry as `tool=token_reduce_orchestrate` with backend/fallback metadata.

## Enable / Disable

Enable trial:

```bash
export TOKEN_REDUCE_ENABLE_GRAPHIFY=1
export TOKEN_REDUCE_GRAPH_PATH=/abs/path/to/graphify-out/graph.json
export TOKEN_REDUCE_GRAPHIFY_UV_DIR=/tmp/graphify-bench
./scripts/token-reduce-orchestrate.sh ExactSymbolName
```

Disable trial (full fallback behavior):

```bash
unset TOKEN_REDUCE_ENABLE_GRAPHIFY
./scripts/token-reduce-orchestrate.sh ExactSymbolName
```

## Removal Plan

If this layer underperforms, remove with:

1. Delete `scripts/token-reduce-orchestrate.sh`
2. Remove this tracking note (`references/graphify-orchestration-tracking.md`)
3. Keep existing token-reduce helpers as-is (`token-reduce-paths.sh`, `token-reduce-snippet.sh`)

No migration or data transformation is required.

## Trial Metrics To Watch

- `token_reduce_orchestrate` helper events in telemetry
- graphify hit rate vs fallback rate
- token and latency deltas vs plain token-reduce helper path
- quality misses (no match or irrelevant cluster)

## Initial Smoke Results

- Graphify-hit case (`buildGuidedSpecMetadata`, `specforge`) returned graph structure via orchestrator.
- Graphify-miss case (`DEFAULT_GUIDED_SPEC_INPUT`, `specforge`) cleanly fell back to token-reduce path helper.
- 1-day telemetry sample in `specforge` after smoke run:
  - `token_reduce_orchestrate` count: `3`
  - orchestrator avg latency: `711.7 ms` (p95 `1055 ms`)
  - `token_reduce_paths` avg latency: `1432.9 ms`
  - `token_reduce_snippet` avg latency: `1745.6 ms`

Sample size is small; keep this layer experimental until broader quality checks pass.

## 2026-04-12 Loop Update

- `graphify` remains optional and disabled by default (`TOKEN_REDUCE_ENABLE_GRAPHIFY` unset).
- Harness now tags benchmark runs as telemetry context `benchmark`, so dependency evaluation loops do not pollute runtime overhead metrics.
- Runtime reviews can now separate real helper behavior from synthetic benchmark loops before deciding whether to keep or remove this layer.

Current keep/remove gate for this layer:

1. Keep only if graphify-hit quality is stable on exact-symbol tasks.
2. Keep only if runtime telemetry shows net latency/token wins vs helper fallback.
3. Remove immediately if fallback rate or quality misses rise without measurable runtime benefit.

## 2026-04-13 Workspace Version Alignment Update

- Added `--force-relink` to `scripts/install_workspace_skill.py` so sibling repos with embedded `skills/token-reduce` directories can be safely backed up and relinked to the canonical workspace skill root.
- Updated `scripts/audit_workspace_skills.py` to emit explicit install mode and drift fields:
  - `skill_install_mode`, `skill_source_path`, `skill_version`, `skill_commit`
  - `skill_version_match`, `skill_commit_match`
  - aggregate summary metrics for version/commit drift and symlink alignment
- Ran forced relink across workspace; two repos converted from embedded copies to canonical symlink installs:
  - `etc-orbit-pilot-apps`
  - `ethglobal-cannes-2026-intelligence-exchange`
- Re-ran workspace audit and confirmed no drift against expected skill metadata:
  - `expected_skill.version: 0.1.0`
  - `expected_skill.commit: 113b509`
  - `repos_with_skill_version_drift: 0`
  - `repos_with_skill_commit_drift: 0`
  - `repos_symlinked_to_expected_skill_root: 14/14`

Result: all local sibling repos are now aligned to the same token-reduce skill root/version/commit. Remaining gap is usage signal depth in low-activity repos, not install/version drift.

## 2026-04-13 Workspace Auto-Update Policy Update

- Added workspace-aware update flow to `scripts/token-reduce-update-check.py`.
- `auto-update` can now also run sibling-repo sync/audit when workspace auto-update policy is enabled.
- New manage command: `./scripts/token-reduce-manage.sh workspace-auto-update`
  - safe ff-only repo update
  - workspace force-relink propagation
  - workspace audit output including version/commit drift
- Added explicit config keys:
  - `updates.workspace_auto_update` (default `true`)
  - `updates.workspace_force_relink` (default `true`)

Latest run result:

- `repos_changed`: `0`
- `repos_with_skill_version_drift`: `0`
- `repos_with_skill_commit_drift`: `0`
- `repos_symlinked_to_expected_skill_root`: `14/14`

This keeps “all local repos on current token-reduce” as an operational default, not an ad-hoc manual check.
