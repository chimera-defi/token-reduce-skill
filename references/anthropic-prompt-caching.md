# Anthropic Prompt Caching

This is an optional companion workflow for developers who call the Anthropic API directly.

It does **not** change Codex behavior.
It does **not** change Claude Code's built-in session caching.

Use it only when you own the Anthropic request payload and want help placing `cache_control` breakpoints.

## CLI

```bash
node scripts/anthropic-cache-plan.mjs --input payload.json
```

Or:

```bash
cat payload.json | node scripts/anthropic-cache-plan.mjs
```

Expected input shape:

```json
{
  "system": "Long system prompt",
  "tools": [{ "name": "search_docs", "input_schema": { "type": "object" } }],
  "messages": [{ "role": "user", "content": "Large stable document chunk..." }],
  "minTokensToCache": 1024,
  "repeatedCalls": 3
}
```

The planner returns:

- `optimizedSystem`
- `optimizedTools`
- `optimizedMessages`
- `analysis`
- `breakpointsAdded`
- `estimatedSavings`

## Heuristics

- Cache the system prompt when the stable prefix crosses the threshold.
- Cache the last tool definition when system + tools form a cacheable prefix.
- Cache large user payloads when a single user message is over the threshold.
- Leave everything else alone.

The token estimate is approximate. It is meant for breakpoint planning, not billing-grade accounting.
