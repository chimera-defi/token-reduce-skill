# Headroom Evaluation - 2026-06-10

## Verdict

Headroom is a promising optional proxy/MCP companion for large tool-result and long-session compression, but it should not replace token-reduce's default helper-first routing.

Recommended status: conditional pilot under token-reduce.

## Integration Decision

Headroom helps in a narrow but real band: large tool-result payloads, long sessions where old tool output keeps recurring in context, and agent hosts that already support a reversible compression proxy/MCP path. The local smoke test showed real savings on tool-shaped payloads: about 24% for OpenAI-style tool output and about 33% for Anthropic `tool_result` blocks. Ordinary user-message JSON did not compress.

Token-reduce remains the master router:

1. Start with token-reduce path/snippet/adaptive/structural helpers.
2. Keep RTK for command-output compression.
3. Add Headroom only when a verified local proxy/MCP is available or when the task is dominated by large tool results.
4. Keep Headroom telemetry off.
5. Do not enable Headroom `--learn` until its memory writes are reviewed against `MEMORY.md`, daily memory, and gbrain policy.

## Source

- Repo: https://github.com/chopratejas/headroom
- Package: `headroom-ai`
- License: Apache-2.0
- Checked version: `0.24.0`
- Claimed support: library, proxy, MCP, Claude Code, Codex, Cursor, OpenClaw.

## Useful Surface

- `headroom proxy` can sit in front of Anthropic/OpenAI-compatible traffic.
- `headroom wrap claude` and `headroom wrap codex` exist for selected agent sessions.
- `headroom wrap openclaw` exists but currently needs care because plugin metadata can lag OpenClaw config validation.
- Compression can be reversible through local context retrieval.
- Proxy exposes useful modes: `--mode token`, `--mode cache`, `--memory`, `--learn`, `--no-telemetry`.

## Local Install Findings

- Avoid unpinned/default Python installs on this host: Python 3.14 hit PyO3 compatibility issues.
- `headroom-ai[proxy]==0.24.0` with Python 3.12 worked.
- Base `headroom-ai` missed proxy dependencies such as `fastapi`.
- `headroom-ai[all]` worked but pulled a very large stack including Torch/CUDA/OCR/eval dependencies.

Recommended install shape:

```bash
uvx --python /usr/bin/python3.12 --from 'headroom-ai[proxy]==0.24.0' headroom --help
```

## Smoke Test

Offline library test against synthetic repeated JSON tool-result payloads:

| Shape | Approx input tokens | Headroom before | Headroom after | Saved | Library latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| OpenAI `role=tool` result | 12,160 | 10,908 | 8,304 | 2,604 / 23.9% | 169.0 ms |
| Anthropic `tool_result` block | 12,169 | 12,351 | 8,342 | 4,009 / 32.5% | 23.5 ms |

Notes:

- Ordinary user-message JSON was not compressed.
- Tool-result shape matters.
- The smoke test did not reproduce the project's 60-95% claims, but it did show real savings.
- Representative production proxy tests are still needed because proxy mode may have better request-shape access than direct library calls.

## Fit With token-reduce

Keep token-reduce's default path:

1. path-first helper routing
2. scoped reads
3. RTK for command output compression
4. structural helpers for exact symbol/impact tasks

Headroom is most useful after those steps for:

- long live agent sessions where old tool results inflate every turn
- raw tool results that bypass RTK/token-reduce helpers
- OpenClaw/Codex provider routing compression across tool calls
- cache-mode experiments for prefix-cache behavior

## Risks

- It sits in the live API path when used as a proxy.
- The install surface is heavier than token-reduce/RTK.
- Retrieval fidelity needs task-level validation.
- OpenClaw plugin metadata can lag current OpenClaw validation; if obsolete keys such as `startupTimeoutMs` or `gatewayProviderIds` appear, keep a manually verified config and avoid rerunning `headroom install apply --providers all`.

## Pilot Plan

1. Install only `headroom-ai[proxy]==0.24.0` with Python 3.12.
2. Prefer selected `headroom wrap codex` or `headroom wrap claude` sessions before global routing.
3. Run with `--no-telemetry`.
4. Avoid `--learn` until memory-write behavior is reviewed against `MEMORY.md` and gbrain policies.
5. Verify with `headroom install status`, `/readyz`, MCP `headroom_compress`/`headroom_retrieve`, and gbrain retrieval.
6. Compare against token-reduce/RTK on exact symbol lookup, broad topic discovery, impact analysis, output-heavy test/build failures, and long OpenClaw session history.

Keep only if real agent turns show savings beyond RTK/token-reduce alone, no material answer-quality regression, predictable local retrieval behavior, acceptable latency, and clean rollback.
