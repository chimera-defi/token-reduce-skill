# AXI Evaluation

This note records whether `kunchenguid/axi` should be integrated into token-reduce.

## Verdict

Integrate AXI as an **optional interface companion** for GitHub and browser automation workflows.
Do **not** treat AXI as a replacement for token-reduce discovery helpers.

## Verification

- Source reviewed: `https://github.com/kunchenguid/axi`
- Local clone + checkout validation:
  - `git clone --depth 1 https://github.com/kunchenguid/axi /tmp/axi-bench`
  - `git -C /tmp/axi-bench checkout -- .`
- Upstream repo validation surface:
  - `npm --prefix /tmp/axi-bench ci`
  - `npm --prefix /tmp/axi-bench run lint`
- CLI runtime validation:
  - `gh-axi --version` → `0.1.11`
  - `chrome-devtools-axi --version` → `0.1.12`
  - both CLIs respond cleanly to `--help`

## Why

- AXI focuses on reducing turn count and retry overhead for execution-heavy interfaces.
- token-reduce focuses on reducing context waste during discovery and reading.
- These are complementary layers, not competing defaults.

## Recommended Consumption Model

Use AXI only where it is naturally dominant:

- `gh-axi` for GitHub issue/PR/repo operations
- `chrome-devtools-axi` for browser automation and page interaction tasks

Keep token-reduce routing unchanged:

- first move for unknown file location remains `./scripts/token-reduce-paths.sh topic words`
- helper-first discovery policy still applies before broad scans

## Integration Plan

1. Keep AXI attribution explicit in `README.md`.
2. Install AXI CLIs during `scripts/setup.sh` when `npm` is available.
3. Track AXI usage in telemetry (`axi_tool_sessions`, `gh_axi_sessions`, `chrome_devtools_axi_sessions`).
4. Keep AXI optional and task-scoped in `SKILL.md` and companion intake rules.
