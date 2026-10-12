# Read-only context audit

`manage.sh context-audit --transcript /path/session.jsonl --output /path/report.json`
measures provider input usage (input + cache creation + cache read, response IDs
deduplicated) and available transcript artifacts. `--budget 300000` is explicitly
an operator assumption, never a model limit inferred from a name. No budget is
guessed when omitted.

Counts: `prompt_snapshot.systemPrompt`; latest skill catalog; observed invoked
skill bodies and instruction/memory files; deferred-tool description deltas;
actual `deferred_tools_record.entries` schemas grouped by `mcp__<server>__<tool>`.
Schema inventory includes `defer_loading`: a 100k-token deferred inventory does
not establish 100k resident prompt tokens. Per-server calls are observed within
the selected transcript only. Zero calls is a review candidate, not proof that a
server is useless.

Available text is measured in bytes and local `cl100k_base` tokens. Those token
counts are not Anthropic's tokenizer or billing. Missing snapshots stay unknown.
Category inventories may overlap and precede compaction or branch changes; they
are not summed, subtracted from usage, or represented as current occupancy.
The first 64 MiB are scanned by default (`--max-bytes` overrides); truncation and
malformed records are visible. Raw prompt, rule, skill and schema text never appears
in output. Reports contain counts, source paths/names, and recommendations only.

## On skill load

Set `TOKEN_REDUCE_LAYER_CONTEXT_AUDIT=on` for the session, then run the command
above against the current transcript when the skill loads. If the harness provides
no transcript, run `manage.sh context-audit` and report categories as unobserved.
`auto` preserves legacy behavior (no automatic audit); `off` suppresses on-load use.

For operator-managed Claude SessionStart integration, the opt-in hook command is:

```bash
uv run --no-project --with tiktoken /path/to/skill/scripts/context_audit.py --hook
```

It consumes `transcript_path` from hook stdin, emits a short `additionalContext`
report only with `context_audit=on`, and fails open without dumping private errors.
This PR does not install the hook or edit `~/.claude` or MCP configuration.

Recommendations require operator approval: disable unused MCP servers per project,
retain deferred loading, review eager schema descriptions, and shorten duplicate
rules/skill bodies. Potential savings remain unknown until the same request is
measured before and after an approved change.
