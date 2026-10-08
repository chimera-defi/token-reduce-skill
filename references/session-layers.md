# Session layers

Defaults: every layer is `auto`, preserving existing behavior. No setup, installs,
memory writes, proxy restart, or MCP/settings edits occur. `off` and `on` are
explicit task policy. Environment overrides beat the existing JSON config.

```json
{"layers":{"rtk":"on","search_qmd":"off","memory":"off","headroom_compress":"on","headroom_retrieve":"off","mcp_trim":"on","context_audit":"on"}}
```

Use a task-local file via `TOKEN_REDUCE_CONFIG_PATH=/path/config.json`, or use
`TOKEN_REDUCE_LAYER_<NAME>=auto|on|off` (uppercase, e.g. `SEARCH_QMD`).
Existing `settings set layers.search_qmd off` persists a choice only when called
explicitly. Session environment choices are never saved.

| Layer | Controlled scope |
|---|---|
| search_qmd | Helper QMD backend; off uses existing rg fallback |
| memory | Semantic memory suggestions in paths/snippet/adaptive helpers |
| rtk | `manage.sh run -- <argv>` rewrites supported commands only when on |
| headroom_compress | Agent permission to use headroom_compress; existing proxy remains external |
| headroom_retrieve | Agent permission to use headroom_retrieve; auto inherits existing use |
| mcp_trim | Recommend project server disabling/deferred loading for operator approval |
| context_audit | Opt-in report on skill load; auto preserves no automatic report |

Before a Headroom action, read `manage.sh layer-action headroom_compress` or
`headroom_retrieve`; do not invoke the MCP action when `allowed` is false. These
are agent policy controls, not a transport firewall. The wrapper cannot turn off
already installed global RTK hooks or an existing Headroom proxy. Starting a
session outside that proxy or changing hook/server settings requires the operator.
No global integration is silently changed by this skill.

`manage.sh status [--events-file /path/events.jsonl]` reports policy, source,
control scope, RTK gain, and live loopback Headroom stats. Unknown saving is null.
RTK uses token estimates; Headroom counters are reported by its proxy. Both are
host/process totals, not skill-attributed causal savings. Do not sum overlapping
layers. Helper events prove invocation, not avoided tokens. An unavailable proxy
is unmeasured, not zero saving.
