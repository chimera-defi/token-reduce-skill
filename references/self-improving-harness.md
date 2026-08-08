# Self-Improving Harness

token-reduce can operate as a managed harness with:

- local telemetry review loops
- optional remote summary upload (opt-in)
- update checks and safe fast-forward updates

## Config

Config file path:

- default: `~/.config/token-reduce/config.json`
- override for testing: `TOKEN_REDUCE_CONFIG_PATH=/tmp/token-reduce-config.json`

Default config:

```json
{
  "version": 1,
  "telemetry": {
    "enabled": false,
    "endpoint": "",
    "api_key": "",
    "signing_secret": "",
    "workspace_root": "/home/agents/workspace",
    "workspace_days": 14,
    "workspace_include_source_repo": false,
    "upload_timeout_seconds": 10,
    "self_improve_sync_timeout_seconds": 45
  },
  "benchmark": {
    "max_age_days": 14
  },
  "updates": {
    "auto_update": false,
    "workspace_auto_update": true,
    "workspace_force_relink": true,
    "check_on_manage": true
  },
  "routing": {
    "profile": "balanced",
    "adaptive_hint": true,
    "behavior_days": 3,
    "rapid_repeat_snippet_threshold": 0.35,
    "enable_structural": true,
    "enable_context_mode_recommendations": true,
    "enable_headroom_recommendations": true,
    "enable_code_review_graph_recommendations": true
  },
  "companions": {
    "caliper": {
      "enabled": true,
      "url": "http://127.0.0.1:49123",
      "self_improve": true
    }
  },
  "budgets": {
    "enabled": false,
    "daily_warning_usd": 20,
    "session_warning_usd": 5,
    "repo_warning_usd": 50,
    "actions": [
      "warn",
      "recommend_headroom",
      "recommend_delegate",
      "recommend_downshift"
    ]
  }
}
```

Manage config:

```bash
./scripts/token-reduce-manage.sh settings show
./scripts/token-reduce-manage.sh settings onboard
./scripts/token-reduce-manage.sh settings set telemetry.enabled true
./scripts/token-reduce-manage.sh settings set telemetry.endpoint https://your-endpoint.example/ingest
./scripts/token-reduce-manage.sh settings set updates.auto_update true
./scripts/token-reduce-manage.sh settings set updates.workspace_auto_update true
./scripts/token-reduce-manage.sh settings profile list
./scripts/token-reduce-manage.sh settings profile apply max-savings
```

`settings show` redacts secrets by default; use `./scripts/token-reduce-manage.sh settings show --raw` only when you explicitly need full values.

## Telemetry Sync

`telemetry-sync` behavior:

1. aggregate `measure --scope global`
2. aggregate workspace adoption summary
3. write local snapshots under `artifacts/token-reduction/`
4. if telemetry is enabled and endpoint is configured, POST anonymized summary payload

Command:

```bash
./scripts/token-reduce-manage.sh telemetry-sync
./scripts/token-reduce-manage.sh rolling-baseline
./scripts/token-reduce-manage.sh improve-adoption --workspace-root /home/agents/workspace --days 7
```

Local receiver example:

```bash
uv run scripts/token-reduce-telemetry-receiver.py --host 0.0.0.0 --port 8787 --path /ingest
./scripts/token-reduce-manage.sh settings set telemetry.endpoint http://127.0.0.1:8787/ingest
```

## Update Checks

`updates` checks branch/upstream state and reports behind/ahead counts.

`auto-update` performs `git pull --ff-only` only when:

- upstream exists
- worktree is clean
- branch is not ahead
- behind count is positive

Commands:

```bash
./scripts/token-reduce-manage.sh updates
./scripts/token-reduce-manage.sh auto-update
./scripts/token-reduce-manage.sh workspace-auto-update
./scripts/token-reduce-manage.sh deps-check
./scripts/token-reduce-manage.sh deps-update
./scripts/token-reduce-manage.sh deps-check-conditional
./scripts/token-reduce-manage.sh deps-update-conditional
./scripts/token-reduce-manage.sh release-gate
./scripts/token-reduce-manage.sh sync-benchmarks
./scripts/token-reduce-manage.sh checkpoint
```

`workspace-auto-update` runs safe repo fast-forward, force-relinks sibling repos to the canonical token-reduce root, and writes a workspace audit with version/commit drift fields.

`deps-check` / `deps-update` are core-only by default (`qmd` + `rtk`).
Use `deps-check-conditional` / `deps-update-conditional` for optional companions.

`release-gate` is intended for large change sets: it refreshes composite/adaptive/profile benchmarks, syncs README benchmark token rows from artifacts, and emits a keep/drop verdict.
Adaptive benchmark runs with `--behavior-days 0` to keep gate results stable across historical telemetry noise.
Adaptive gate uses a bounded default tolerance (`-2.0%`) to absorb benchmark noise while still requiring quality pass.

`checkpoint` is the full consistency harness: release-gate/validate/tests + local/global measure/review + workspace audit + dry-run telemetry sync with timestamped artifacts.

## One-Shot Maintenance

`self-improve` runs a compact maintenance pass:

- composite benchmark (tagged as `benchmark` context; excluded from runtime telemetry summaries)
- dependency freshness check
- global measure + review refresh
- optional Caliper spend snapshot + Caliper-backed global review when the local Control Tower API is reachable
- Databricks cost playbook scorecard in review output
- workspace audit snapshot (`artifacts/token-reduction/workspace-audit-YYYY-MM-DD.json`)
- adoption improvement report (`artifacts/token-reduction/adoption-improvement-YYYY-MM-DD.{json,md}`)
- bounded telemetry sync (`telemetry.self_improve_sync_timeout_seconds`, default 45s)
- rolling baseline trend report (`artifacts/token-reduction/rolling-baseline-YYYY-MM-DD.{json,md}`)
- update check

```bash
./scripts/token-reduce-manage.sh self-improve
```

Caliper artifacts, when available:

- `artifacts/token-reduction/caliper-summary-YYYY-MM-DD.json`
- `artifacts/token-reduction/caliper-summary-YYYY-MM-DD.md`

If Caliper is not running, the command prints a nonblocking skip message and continues without spend telemetry.

## Adoption Improvement

`improve-adoption` is the focused continuous-improvement command for weak helper usage:

```bash
./scripts/token-reduce-manage.sh improve-adoption --workspace-root /home/agents/workspace --days 7
```

It runs a workspace audit unless `--audit-json` is supplied, then emits:

- active-repo helper usage SLO status
- workspace helper usage SLO status
- likely cause counts
- prioritized repo interventions

Default warning-only targets are 90% active-repo helper usage and 25% workspace helper usage. The command does not mutate repos; pair it with `workspace-install` only when the report shows install/docs/root/version drift. When install/docs are already clean, treat `active_no_helper` repos as agent behavior gaps and improve first-move nudges, hook coverage, or host instructions.
