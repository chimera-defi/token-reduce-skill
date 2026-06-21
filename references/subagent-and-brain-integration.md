# Subagent, gstack, and Brain-First Hint Integration

## Subagent + gstack Integration

When the helper returns more than five candidate files, or the query has broad-scope cues (`across`, `workspace`, `everywhere`, `all files`), the adaptive router emits `subagent_recommended: true` and a ready-to-copy `Agent(subagent_type="Explore", ...)` snippet. Delegating discovery to a subagent keeps the raw candidate set out of the main context — only the ranked summary returns. Use the emitted snippet directly instead of reading every candidate yourself.

When the query also names sibling repos or workspaces and the `gstack-session-spawn` skill is available, the router additionally emits a `/create-session` suggestion so each sibling repo gets its own dispatch.

If the query intent matches another skill (`review the PR` → `/review`, `fix the bug` → `/investigate`, `brainstorm` → `/brainstorm`), the router surfaces the matching skill in its rationale. Treat that as a routing hint, not an override.

## Brain-First Hint

When `qmd` or `gbrain` is on `PATH`, the helpers emit (to stderr, after the main output):

```
token-reduce: also try `qmd search "<query>" -n 5 --files` for semantic memory hits
```

Check semantic memory before a filesystem walk. If the brain returns relevant hits, you can skip the helper entirely.

The canonical implementation lives in `scripts/brain_hint.py` (kept dependency-light to avoid a 50-150ms cold-start tax on shell helpers); the adaptive router's `brain_hint_line` mirrors the same logic for in-Python callers.
