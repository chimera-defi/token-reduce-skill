# Cost Caliper Evaluation (2026-07-03)

## Source

- Upstream: <https://github.com/Cost-Caliper/caliper>
- Verified commit: `029bc40b924bea6dece6e16087033e40b1044266`
- License: MIT
- Plugin version: `0.28.0`
- Package runtime: Node.js `>=20`

## What It Does

Cost Caliper reads local Claude Code transcripts under `~/.claude/projects` and exposes spend/session analytics through its local Control Tower dashboard/API.

Relevant surfaces:

- `/caliper`: launches the local Control Tower UI/API
- `/optimize-spend`: reviews Caliper metrics and proposes spend reductions
- `GET /v1/health`: local dashboard/API health
- `GET /v1/aggregate`: aggregate spend/session/model/cache metrics
- `GET /v1/sessions/all`: session drilldown
- `GET /v1/observed`: observed workflow/tool-call data

The upstream plugin manifest does not register an MCP server. That makes it lower risk than companions that mutate Claude MCP configuration during install.

## Local Verification

Clone:

```bash
git clone --depth 1 https://github.com/Cost-Caliper/caliper /tmp/caliper-intake
```

Tests:

```bash
cd /tmp/caliper-intake/packages/workflow-lens && npm install && npm test
cd /tmp/caliper-intake/packages/control-tower && npm install && npm test
```

Results:

- `workflow-lens`: 160 tests passed
- `control-tower`: 241 tests passed, 12 skipped
- `npm install`: 0 vulnerabilities reported in both package workspaces

API smoke:

```bash
node scripts/demo-data.mjs
WFLENS_PROJECTS_ROOT=/tmp/caliper-demo/projects PORT=49123 node packages/control-tower/server.mjs
curl -fsS http://127.0.0.1:49123/v1/health
curl -fsS http://127.0.0.1:49123/v1/aggregate
```

The health endpoint returned `ok`, and aggregate output included sessions, folders, estimated cost, token buckets, fallback data, day/repo/tier breakdowns, and model-tier spend.

## Decision

Integrate Caliper as an optional telemetry companion for periodic token-reduce meta-review.

Do not make it part of default discovery, default setup, validation, or release gating. Token-reduce remains the master router for helper-first discovery, scoped reads, Headroom recommendations, and delegate batching.

## Token-Reduce Integration

Shipped integration:

- `scripts/caliper_summary.py`: reads a running local Control Tower API and emits normalized JSON/Markdown
- `./scripts/token-reduce-manage.sh caliper-summary`: command wrapper for the summarizer
- `./scripts/token-reduce-manage.sh review --with-caliper`: adds spend-aware findings to self-review

Primary use:

```bash
./scripts/token-reduce-manage.sh caliper-summary --url http://127.0.0.1:49123
./scripts/token-reduce-manage.sh review --with-caliper --caliper-url http://127.0.0.1:49123
```

If Caliper is not running, `review --with-caliper` reports a setup finding and continues with normal token-reduce telemetry.

## How It Improves Token-Reduce

Caliper adds telemetry token-reduce does not currently own:

- estimated cost by repo/session/day
- model-tier mix
- cache write/read economics
- expensive-session hotspots
- fallback/refusal patterns

Token-reduce can combine this with its own helper/compliance data:

- high spend + broad-scan violations: tighten first-move enforcement and repo guidance
- high spend + low Headroom use: run Headroom on large tool-result/long-session pressure
- high spend + low delegate use: batch side reviews through delegate wrappers
- high cache writes + low cache reads: reduce churn in always-loaded guidance and repeated payloads
- expensive Claude sessions but clean Codex compliance: focus Claude guidance rather than token-reduce helper mechanics

## Risks And Guardrails

- Claude-specific: Caliper reads Claude Code transcript layout; it does not provide Codex-native spend data.
- Estimated costs only: treat numbers as directional, not invoice records.
- Young project: no releases observed during intake and low public adoption.
- Local dashboard dependency: requires Node.js and a running Control Tower server.
- Privacy: it reads local transcripts. Keep analysis local and do not upload transcript-derived details without explicit consent.
- Persistence: do not auto-write Caliper's personalized cost-discipline skill without explicit user consent.

## Verdict

Keep Caliper optional, explicit, and review-only.

It is useful for spend-aware meta-work and for making Headroom/delegate recommendations more evidence-driven. It should not replace token-reduce's default helper-first workflow or become a required dependency.
