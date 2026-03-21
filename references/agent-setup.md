# Agent Setup

Use this file for host-specific setup and wiring.
The main `README.md` is intentionally user-facing and non-technical.

## Claude Code

### Plugin Install

```text
/plugin marketplace add https://github.com/chimera-defi/token-reduce-skill
/plugin install token-reduce@chimera-defi
```

### Repo-Level Hook Wiring

If you want stronger enforcement inside a project repo, wire the hooks shown in `references/workspace-integration.md`.

## Codex

```bash
git clone https://github.com/chimera-defi/token-reduce-skill "$CODEX_HOME/skills/token-reduce"
```

Then point repo instructions at:

- `./tools/token-reduce-skill/scripts/token-reduce-paths.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-snippet.sh`

For deeper setup guidance, use `references/workspace-integration.md`.

## MCP

```json
{
  "mcpServers": {
    "token-reduce-mcp": {
      "command": "node",
      "args": ["/absolute/path/to/token-reduce-skill/mcp/server.mjs"]
    }
  }
}
```

## Read Next

- `references/architecture.md`
- `references/workspace-integration.md`
- `references/token-reduction-guide.md`
