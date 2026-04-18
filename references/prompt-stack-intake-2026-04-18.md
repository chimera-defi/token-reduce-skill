# Prompt Stack Intake (2026-04-18, URL-corrected pass)

This note records the second intake pass using the corrected 10-repo URL set.

## Verdict Summary

- Keep token-reduce first-move defaults unchanged.
- Keep `rtk`, `token-savior`, `caveman`, and AXI in the current optional stack.
- Add `context-mode` and `code-review-graph` as **evaluated optional companions** (task-scoped, not first-move defaults).
- Keep `token-optimizer-mcp` out of default discovery routing (local regression in token-reduce discovery tasks).
- Keep `claude-context` as conditional external option only (infra-coupled and no local token-reduce benchmark completed).
- Do not integrate `token-optimizer` (`alexgreensh`) into token-reduce defaults (license mismatch + overlap + no reproducible benchmark on token-reduce tasks in this intake).

## Source Verification (Provided URLs)

All provided URLs were reachable via `git ls-remote` and GitHub API.

| Prompt dependency | URL | Reachable |
|---|---|---|
| RTK (Rust Token Killer) | `https://github.com/rtk-ai/rtk` | yes |
| Context Mode | `https://github.com/mksglu/context-mode` | yes |
| code-review-graph | `https://github.com/tirth8205/code-review-graph` | yes |
| Token Savior | `https://github.com/Mibayy/token-savior` | yes |
| Caveman Claude | `https://github.com/JuliusBrussee/caveman` | yes |
| claude-token-efficient | `https://github.com/drona23/claude-token-efficient` | yes |
| token-optimizer-mcp | `https://github.com/ooples/token-optimizer-mcp` | yes |
| claude-token-optimizer | `https://github.com/nadimtuhin/claude-token-optimizer` | yes |
| token-optimizer | `https://github.com/alexgreensh/token-optimizer` | yes |
| claude-context | `https://github.com/zilliztech/claude-context` | yes |

## Upstream Validation Executed

### Passed

- `rtk-ai/rtk`
  - `cargo test -q`
  - result: `1590 passed`, `6 ignored`

- `mksglu/context-mode`
  - `pnpm install --no-frozen-lockfile`
  - `pnpm build`
  - `pnpm test`
  - result: `46` files passed, `1532` tests passed (`23` skipped)
  - note: running `pnpm test` before `pnpm build` failed because generated build artifacts were missing.

- `tirth8205/code-review-graph`
  - `uv run --with pytest --with pytest-asyncio pytest -q`
  - result: `788 passed`, `1 skipped`, `2 xpassed`

- `Mibayy/token-savior`
  - `uv run --with pytest --with mcp pytest -q`
  - result: `1318 passed`

- `JuliusBrussee/caveman`
  - `uv run --with tiktoken caveman-compress/scripts/benchmark.py`
  - result samples: `49.1%`, `32.1%`, `23.0%`, `40.9%`, `26.4%` savings on benchmark files

- `ooples/token-optimizer-mcp`
  - `npm ci`
  - `npm test`
  - `npm run build`
  - result: `25` suites passed, `562` tests passed (`1` skipped), build passed

- `alexgreensh/token-optimizer` (OpenClaw package surface)
  - `npm install` (in `openclaw/`)
  - `npm run build`
  - `npm run validate`
  - result: build/validate commands succeed (reported `INSUFFICIENT_DATA` for telemetry-backed validation)

### Partial / blocked for local token-reduce benchmarking

- `zilliztech/claude-context`
  - previous pass status retained:
    - `pnpm install --frozen-lockfile` passed
    - `pnpm build` passed
    - `pnpm lint` failed in this environment
    - `pnpm typecheck` failed in this environment
  - full token-effect validation remains infra-coupled (requires OpenAI + Milvus/Zilliz setup).

### Prompt-template repos (no runtime tooling surface)

- `drona23/claude-token-efficient` (`CLAUDE.md` template)
- `nadimtuhin/claude-token-optimizer` (setup-prompt/template structure)

These overlap with token-reduce + caveman-style guidance and were not integrated as runtime dependencies.

## Measured Benchmark Evidence

### token-reduce baselines (current repo)

- `./scripts/token-reduce-manage.sh benchmark`
  - `broad_inventory`: `565` tokens
  - `guidance_scoped_rg`: `197` tokens (`65.1%` saved)
  - `token_reduce_paths_warm`: `328` tokens (`41.9%` saved)

- `./scripts/token-reduce-manage.sh benchmark-composite`
  - `broad_shell`: `1154` tokens (`ok`)
  - `token_savior_only`: `621` tokens (`ok`)
  - `rtk_only`: `627` tokens (`ok`)
  - `composite_stack`: `367` tokens (`68.2%` saved vs broad, `ok`)

### context-mode benchmark

Runner:
- `cd /tmp/token-reduce-intake/context-mode`
- `pnpm test:compare`
Artifact: `references/benchmarks/context-mode-intake.json`

Output highlights from fixture-based comparison:
- total payload: `195.0KB -> 4339B` (`98%` reduction)
- estimated context impact: `49,911 -> 1,085` tokens
- estimated multiplier: `46x` more files before equivalent context usage

### code-review-graph benchmark

Runner:
- `cd /tmp/token-reduce-intake/code-review-graph`
- `uv run code-review-graph eval --benchmark token_efficiency --repo express --output-dir /tmp/token-reduce-intake/code-review-graph-eval`
- `uv run code-review-graph eval --benchmark token_efficiency --repo fastapi --output-dir /tmp/token-reduce-intake/code-review-graph-eval`
Artifact: `references/benchmarks/code-review-graph-intake.json`

Results:
- `express` sample commits (small/single-file changes): graph overhead can lose (`0.7x`)
- `fastapi` sample commits: graph wins strongly (`9.9x`, `6.2x`)

Interpretation: it is high-value for larger dependency-rich repos; not guaranteed positive on trivial/single-file diffs.

### token-savior companion check

- `uv run --with tiktoken scripts/benchmark-companion-tools.py --repo-root . --token-savior-repo /tmp/token-reduce-intake/token-savior`
- exact symbol lookup:
  - token-reduce flow: `363` tokens
  - token-savior flow: `53` tokens

### token-optimizer-mcp intake benchmark

Artifact: `references/benchmarks/token-optimizer-mcp-intake.json`  
Runner: `TOKEN_OPTIMIZER_REPO=/tmp/token-reduce-intake/token-optimizer-mcp ./scripts/token-reduce-manage.sh benchmark-token-optimizer-intake`

Key outcomes:
- inventory task:
  - raw `rg --files`: `660` tokens
  - `smart_glob`: `142` tokens but quality failed (under-retrieved representative files)
- scoped grep task:
  - raw scoped `rg`: `197` tokens
  - `smart_grep` (matches): `1230` tokens (regression)
  - `smart_grep` (files only): `416` tokens (regression)

Decision: do not route token-reduce default discovery through token-optimizer-mcp.

## Final Integration Decision Matrix

| Candidate | Decision | Why |
|---|---|---|
| `rtk-ai/rtk` | keep integrated | validated + complementary output compression |
| `mksglu/context-mode` | optional companion (task-scoped) | very strong reduction on output-heavy tool payloads; not a first-move path locator |
| `tirth8205/code-review-graph` | optional companion (task-scoped) | strong gains on larger repos; can lose on tiny/single-file diffs |
| `Mibayy/token-savior` | keep optional structural helper | strong exact-symbol efficiency |
| `JuliusBrussee/caveman` | keep optional style/input companion | validated output/memory compression profile |
| `drona23/claude-token-efficient` | no runtime integration | prompt-template overlap with existing style controls |
| `ooples/token-optimizer-mcp` | reject as default discovery backend | local token-reduce discovery benchmark regressed |
| `nadimtuhin/claude-token-optimizer` | no runtime integration | setup-template overlap; no unique runtime backend |
| `alexgreensh/token-optimizer` | reject for default integration | restrictive license + overlap + no reproducible token-reduce task win in this pass |
| `zilliztech/claude-context` | conditional hold | external infra coupling and no local token-reduce benchmark completed |
