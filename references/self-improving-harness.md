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
    "workspace_root": "/root/.openclaw/workspace/dev",
    "workspace_days": 14,
    "workspace_include_source_repo": false,
    "upload_timeout_seconds": 10
  },
  "benchmark": {
    "max_age_days": 14
  },
  "updates": {
    "auto_update": false,
    "workspace_auto_update": true,
    "workspace_force_relink": true,
    "check_on_manage": true
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
```

`workspace-auto-update` runs safe repo fast-forward, force-relinks sibling repos to the canonical token-reduce root, and writes a workspace audit with version/commit drift fields.

## One-Shot Maintenance

`self-improve` runs a compact maintenance pass:

- composite benchmark (tagged as `benchmark` context; excluded from runtime telemetry summaries)
- dependency freshness check
- global measure + review refresh
- workspace audit snapshot (`artifacts/token-reduction/workspace-audit-YYYY-MM-DD.json`)
- telemetry sync
- rolling baseline trend report (`artifacts/token-reduction/rolling-baseline-YYYY-MM-DD.{json,md}`)
- update check

```bash
./scripts/token-reduce-manage.sh self-improve
```
