# Dependency intake — 2026-10-09

Host unchanged. Updated repo installation targets: Headroom 0.40.0 and RTK 0.51.0.
Headroom freshness now queries PyPI instead of calling the old 0.24.0 pin “latest”.
Explicit updates stop when an upstream candidate is newer than the qualified pin.
RTK installs from a versioned tag with Cargo.lock, replacing an unpinned curl-to-shell
installer. QMD 2.8.3 is held from automatic install/update after intake below.

| Dependency | Host | Latest observed | Evidence / decision |
|---|---|---|---|
| Headroom | 0.39.1 | 0.40.0 | Isolated wheel/CLI plus 27 upstream schema tests pass; repo pin updated |
| RTK | 0.50.0 | 0.51.0 | Upstream units/integration run; Git 2.43 error-wording fixture adapted to compare actual stderr; repo pin updated |
| QMD | 2.6.3 | 2.8.3 | 83 focused upstream tests pass; npm audit 9 findings (5 critical/3 high/1 moderate); automatic candidate intake held |
| gh-axi | 0.1.35 | 0.1.35 | Current; no change |
| chrome-devtools-axi | 0.1.36 | 0.1.39 | Candidate only; browser qualification not run; no host upgrade |
| context-mode | executable says missing | 1.0.169 | Local version unknown; optional, no install |
| code-review-graph | 2.3.9 | 2.3.9 | Current; no change |

Headroom [0.40.0 release](https://github.com/headroomlabs-ai/headroom/releases/tag/v0.40.0)
documents breaking license/reporting behavior and removal of the CrewAI extra.
This intake qualifies schema compaction/CLI, not a live proxy deployment; no restart
or configuration migration was performed. Beacon/telemetry stayed off in isolated tests.

RTK [0.51.0 release](https://github.com/rtk-ai/rtk/releases/tag/v0.51.0) requires Rust
1.91; tested here with 1.99. Rewrite returns 0 allow, 1 passthrough, 2 deny,
3 host approval. Tests initially failed because the host's `dd` alias resolves to
Devin's delegate wrapper. A clean test PATH fixes this without changing the host.
A separate upstream test hardcodes Git 2.51's “not an integer”; Git 2.43 reports
“not a non-negative integer”. Artifact-local fixture compares exact raw Git stderr;
original failures and the one-line adaptation are retained in the report evidence.

QMD [2.8.3 changelog](https://github.com/tobi/qmd/blob/v2.8.3/CHANGELOG.md) changes local
config trust and MCP HTTP protocol behavior. Its CLI BM25/config interfaces passed
focused tests; neural search/native bindings/full suite were not qualified. The
audit includes production simple-git/node-llama-cpp and development Vitest chains.
No `npm audit fix --force`, major downgrades, or trust bypass was applied. Keep the
installed version until upstream/advisory review resolves qualification; this is
not a claim that the older installed version is secure.

## Additional tool proposal: slim-mcp 0.3.1 — do not adopt

Read [README](https://github.com/Joncik91/slim-mcp) and
[compression source](https://github.com/Joncik91/slim-mcp/blob/main/src/compress.ts).
Artifact-only npm install with scripts disabled; tests: 186 pass, four filesystem
proxy integration failures. Aggressive mode deduplicates properties to type only;
extreme/maximum modes replace input schemas with description signatures. This
changes validation/discovery semantics. Its token counter uses JSON chars / 4,
an estimate, not measured model tokens. No live API benchmark or host install.
Existing deferred loading and Headroom schema compaction are the qualified starting
point. No new companion improves the default workflow with sufficient evidence.

Evidence logs and original upstream checkouts:
`~/research-artifacts/token-reduce-audit-20261009/`. Live runtime upgrade and browser
qualification remain distinct from repo source changes and passing unit tests.
