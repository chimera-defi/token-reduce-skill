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
    "workspace_root": "/root/.openclaw/workspace/dev",
    "upload_timeout_seconds": 10
  },
  "updates": {
    "auto_update": false,
    "check_on_manage": true
  }
}
```

Manage config:

```bash
./scripts/token-reduce-manage.sh settings show
./scripts/token-reduce-manage.sh settings set telemetry.enabled true
./scripts/token-reduce-manage.sh settings set telemetry.endpoint https://your-endpoint.example/ingest
./scripts/token-reduce-manage.sh settings set updates.auto_update true
```

## Telemetry Sync

`telemetry-sync` behavior:

1. aggregate `measure --scope global`
2. aggregate workspace adoption summary
3. write local snapshots under `artifacts/token-reduction/`
4. if telemetry is enabled and endpoint is configured, POST anonymized summary payload

Command:

```bash
./scripts/token-reduce-manage.sh telemetry-sync
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
```

## One-Shot Maintenance

`self-improve` runs a compact maintenance pass:

- composite benchmark
- global measure + review refresh
- telemetry sync
- update check

```bash
./scripts/token-reduce-manage.sh self-improve
```
