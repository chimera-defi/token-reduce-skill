# token-savior Evaluation

This note records whether `Mibayy/token-savior` should be integrated into token-reduce.

## Verdict

Integrate it as an optional structural accelerator, not as a replacement for token-reduce.

## Verification

- Source reviewed: `https://github.com/Mibayy/token-savior`
- Upstream tests run locally:
  - `cd /tmp/token-savior-bench && uv run --with pytest --with mcp pytest -q`
  - result: `416 passed`
- Local benchmark run (historical — `scripts/benchmark-companion-tools.py` was a
  one-shot harness removed 2026-09-12 as orphaned dead code; to re-benchmark,
  use `npm run bench` / `scripts/benchmark-composite-stack.py`, the maintained
  suite):
  - `uv run --with tiktoken scripts/benchmark-companion-tools.py --repo-root . --token-savior-repo /tmp/token-savior-bench`

## Why

- It is materially better for exact symbol lookup and structural impact questions.
- It is not better as a general first-move discovery system for broad topic or fuzzy repo navigation.
- token-reduce still owns:
  - repo-agnostic kickoff discipline
  - hook enforcement
  - broad-topic search fallback
  - no-extra-dependency default workflow

## Measured Results

Benchmarked in this repo on four representative tasks:

| Task | token-reduce | token-savior | Outcome |
|------|--------------|--------------|---------|
| exact symbol lookup (`discovery_hint`) | `234` tokens / `1398.56 ms` | `56` tokens / `196.31 ms` | token-savior clearly wins |
| constant lookup (`STATE_TTL_SECONDS`) | `35` tokens / `573.36 ms` | `231` tokens / `195.68 ms` | token-reduce stays cheaper |
| impact analysis (`prompt_requires_helper`) | `25` tokens / `570.61 ms` | `82` tokens / `191.76 ms` | token-savior adds meaningful structure; keep as optional |
| broad topic search (`hook enforcement system`) | `1230` tokens / `286.48 ms` | `106` tokens / `250.77 ms` | token-savior output was cheaper but low-relevance |

Interpretation:

- `token-savior` is the better backend when the symbol is already known and the user needs exact structure or dependency answers.
- `token-savior` should not replace `token-reduce-paths.sh` for ambiguous repo exploration, because its broad text search can surface benchmark/eval noise instead of the canonical implementation files.
- For some simple constant lookups, `token-reduce` remains the cheapest path because the existing helper returns only a path hint or tiny fallback.

## Recommended Consumption Model

Use `scripts/token-reduce-structural.py` only when:
- the exact symbol/class/function name is already known
- the user asks "what depends on X" or "what breaks if I change X"

Do not use it as the default kickoff for vague prompts like "find the auth flow" or "explore the hook system".

## Integration Plan

1. Keep `token-reduce-paths.sh` and `token-reduce-snippet.sh` as the default discovery workflow.
2. Route exact symbol and dependency questions through `scripts/token-reduce-structural.py`.
3. Treat `token-savior` as an optional install, not a required dependency.
4. Reuse the benchmark harness before adopting future companion tools.

## MCP registration decision — 2026-10-25

**Decided: (b), keep token-savior opt-in and remove the dead settings entry.**
Do not register it at user scope or add it to the default plugin manifest.
Keep the structural Python helper for exact symbol/dependency questions; it
imports the backend directly and requires no MCP registration.

The installed binary resolves to
`~/.local/share/uv/tools/token-savior-recall/bin/token-savior`
(`token-savior-recall 4.24.0`, MCP SDK `2.3.0`). Validation used a temporary
project/cwd with `WORKSPACE_ROOTS`, `TOKEN_SAVIOR_DATA_DIR`, and
`XDG_CACHE_HOME` confined to `/tmp`; no host Claude configuration was changed.
An interactive NDJSON probe sent `initialize` with protocol `2024-11-05`
and waited for its response before sending `notifications/initialized` and
`tools/list`. It timed out without an initialize response. A separate pipelined
probe sent all three messages and reached the logged `server.run` loop, but
returned no stdout before its 12-second timeout (exit `124`). **Startup is
observed; a working stdio handshake is not verified.** Repair/revalidate that
before opting into MCP on this installed version.

To measure schema cost despite the transport failure, the installed server's
`list_tools` handler was invoked directly with the default `full` profile and
profile overrides unset. It returned **72 tools**. A compact JSON-RPC
`tools/list` response constructed from its `ListToolsResult` is **53,617 UTF-8
bytes / 53,607 characters**, approximately **13,402 tokens** using characters
divided by four; the tool array alone is 53,505 characters, approximately
13,376 tokens. These are handler-derived estimates, **not a captured stdio
response, provider-tokenizer count, or observed Claude context occupancy**.
Clients with deferred tool loading may pay schema cost only as tools load.
See [the measurement record](token-savior-mcp-intake-2026-10-25.json).

The earlier four-task benchmark remains the decision basis: exact-symbol
lookup saved 178 output tokens (`234 → 56`), constant lookup cost 196 more
(`35 → 231`), impact analysis cost 57 more (`25 → 82`) for added structure,
and broad search was low-relevance. Those specialized wins do not justify
exposing a roughly 13.4k-token default tool inventory to every session. No
current end-to-end evidence establishes that a global registration pays its
cost. This preserves the no-extra-global-dependency posture and the existing
optional accelerator verdict; it does not claim a new performance benchmark.

### Config provenance

Searches for `token-savior`, `token_savior`, `settings.json`, and `mcpServers`
in setup/install/manage scripts, Markdown guidance, Claude config, and the
plugin manifest found **no repo writer or recommendation for a token-savior
entry in `settings.json`**. Relevant available Git history also contains no
such writer. Its host-level origin is therefore unattributed.
`scripts/setup.sh` patches `~/.claude/settings.json` for hooks and preserves
other keys; it installs a structural-helper wrapper but no token-savior MCP
entry. The plugin registers only `token-reduce-mcp`.

The README and agent setup guide previously showed a generic `mcpServers`
object without naming its destination. They now use an explicit project
registration command. Per the [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp#mcp-installation-scopes),
`claude mcp add -s project` writes `.mcp.json`; `-s user` writes
`~/.claude.json`. Plugin manifests are another supported mechanism.
`~/.claude/settings.json` is not an MCP registration location. No installer
change or automatic host migration is needed; the narrow cleanup below is
deliberately manual.

### Apply on host

**Commands documented only; not run during this evaluation.** Remove just the
dead token-savior entry, preserving hooks, other settings, and other server
entries. The backup uses exclusive creation so an earlier backup cannot be
overwritten. A second run is a no-op once the entry is absent.

```bash
uv run --no-project python - <<'PY'
import json
from pathlib import Path

path = Path.home() / ".claude" / "settings.json"
original = path.read_text()
settings = json.loads(original)
servers = settings.get("mcpServers", {})
if "token-savior" in servers:
    backup = path.with_name("settings.json.before-token-savior-2026-10-25.bak")
    import os
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as saved:
        saved.write(original)
    del servers["token-savior"]
    if not servers:
        settings.pop("mcpServers")
    path.write_text(json.dumps(settings, indent=2) + "\n")
PY
claude mcp list
```

**No `claude mcp add -s user` command is part of applying this decision.**
The structural helper remains available without registering a server.
After independently verifying a successful handshake, an operator who needs
MCP can explicitly opt a consuming project in (run from that project):

```bash
claude mcp add -s project --transport stdio token-savior --env "WORKSPACE_ROOTS=$PWD" -- "$HOME/.local/bin/token-savior"
claude mcp get token-savior
```

This writes that project's `.mcp.json` and needs Claude's project approval.
To undo that optional project registration, run from the same project:

```bash
claude mcp remove -s project token-savior
```

### Repo validation

`UV_CACHE_DIR=/tmp/tr-mcp-uv-cache python3 -m pytest scripts/tests -q`:
363 passed, one pre-existing failure in
`test_setup_and_update_keep_qmd_held_and_use_only_pinned_rtk` (excluded from
this decision as requested). No executable repo scripts changed.
`token-reduce-manage.sh validate` passed package-shape validation but exited
`1` because the existing local/composite benchmark artifacts are 51.3 days
old against a 14-day limit; they were not relabeled or refreshed for a docs
change. `measure`, `review`, and `improve-adoption` completed; the review
reports weak helper adoption, further favoring improving the existing
workflow before adding a global dependency. This is a documented freshness
exception, not a passing package-wide validation claim.
