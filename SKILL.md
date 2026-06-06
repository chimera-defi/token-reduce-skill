---
name: token-reduce
license: MIT
description: "Reduce repo context cost with QMD/helper discovery, scoped rg, targeted reads, concise summaries, and AI-delegate call batching."
metadata:
  author: "GPT-5 Codex"
  category: "productivity"
  version: "5.6.0"
  argument_hint: "[file-or-directory]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Token Reduction Skill

## Description

Use targeted retrieval and short summaries when paths are unknown, the repo is large, or the task spans multiple files. Skip exact-path tiny edits.

## Triggers

- The user asks to review, explore, search for context, or find where something lives.
- The user asks to validate, check, verify, improve, fix, or update a skill, hook, script, or file.
- The user's request implies the skill is not being used correctly or needs to work better.
- You do not know the exact file path yet.
- The task spans several files or areas of the repo.
- Broad scans or full-file reads would likely waste context.
- When maintaining this skill itself, the same narrow-discovery rules apply.

## First Move

- If file location is unknown, start with one standalone discovery command:
  - `scripts/token-reduce-paths.sh topic words`
  - `scripts/token-reduce-snippet.sh topic words`
- If the exact symbol is already known and `token-savior` is installed, you may use:
  - `uv run python scripts/token-reduce-structural.py --project-root . find-symbol ExactSymbol`
  - `uv run python scripts/token-reduce-structural.py --project-root . change-impact ExactSymbol`
- Prefer `scripts/token-reduce-paths.sh` for the initial path-only kickoff.
- Prefer the structural helper only for exact symbol or dependency questions; do not use it as the default for vague repo discovery.
- Use `scripts/token-reduce-snippet.sh` only when the path list is not enough.
- Do not treat raw `qmd search` or raw `rg` as the first compliant move when the helper is available; those belong inside the helper workflow or as a narrow follow-up after helper output.
- Do not chain discovery commands with `||`, `&&`, `find`, `ls`, or extra fallback shell logic.
- Do not treat `rg --files .` as compliant discovery.
- Do not start with `find .`, `ls -R`, `grep -R`, or broad `Glob` patterns such as `**/*`.
- After two failed discovery attempts or once the candidate set exceeds 5 files, stop expanding and ask the user to narrow the scope.

## Heuristics

| Strategy | Measured Savings | When |
|----------|-----------------|------|
| Concise responses | 89% | Always |
| QMD BM25 search | 71–83% vs broad file listing (local/composite benchmarks); much higher vs reading file contents naively | Finding which files to read |
| Targeted reads | 33% | Large files |
| Parallel calls | 20% | Independent lookups |
| Caveman-style output profile (optional companion) | 20–65% output token reduction in upstream caveman benchmarks | When the user explicitly asks for extra brevity |
| AXI companion tools (optional) | Fewer turns in upstream AXI studies for GitHub/browser tasks | When work is primarily GitHub or browser automation |
| AI delegate companions (`devin-delegate`, `kimi-delegate`) | Offload bounded side work while parent agent keeps critical-path orchestration and verification | Devin for research/writing/implementation/debug/browser; Kimi for cheap exploration and independent review |
| Adaptive tier router | Auto-promotes/demotes helper tier from behavior and query intent | Default first move when path is unknown (`token-reduce-adaptive`) |
| Context Mode companion (optional) | Up to ~98% reduction in output-heavy fixture comparisons | When tasks are dominated by huge tool payloads (logs, test output, API dumps) |
| code-review-graph companion (optional) | 6x–10x token wins on larger-repo token-efficiency samples; can lose on tiny single-file diffs | Large monorepo review, dependency blast-radius, architecture impact tasks |

## Process

1. Check QMD once per session:
   ```bash
   command -v qmd >/dev/null 2>&1 && qmd collection list 2>/dev/null | head -1
   ```
   If unavailable, use scoped `rg`.
2. If you know the file or keyword, use a scoped grep first, then read only the needed lines.
3. If you need an auto-routed kickoff, use `scripts/token-reduce-adaptive.sh topic words`.
4. If you need a low-token path-only kickoff, use `scripts/token-reduce-paths.sh topic words`.
5. If you need one ranked excerpt after the kickoff, use `scripts/token-reduce-snippet.sh topic words`.
6. If a file is large, read only the relevant section.
7. If the search space stays broad, stop expanding and ask the user to narrow it.
8. For GitHub/browser-heavy execution, prefer `gh-axi` or `chrome-devtools-axi` over higher-overhead interfaces when available.
9. When routing behavior should be formally constrained, apply a profile (`minimal-load`, `balanced`, `max-savings`) via `token-reduce-manage.sh settings profile apply <name>`.

## Output Brevity Profile (Companion)

When the user asks for tighter responses, apply a caveman-inspired **lite** profile:

- remove pleasantries, hedging, and filler
- keep technical terms exact
- keep code blocks, commands, and error text exact
- prefer short, direct statements over narrative framing

Do not force this style when clarity or safety would degrade. This is optional, not the default for every user.

## Success Criteria

- Discovery starts with QMD BM25 or scoped `rg`, not recursive shell scans.
- `scripts/token-reduce-search.sh` uses repo-scoped QMD first, then scoped `rg`.
- `rg --files .` and similar broad inventory commands are treated as violations.
- Reads stay targeted.
- Final summaries cite only the minimum files needed.
- Repo-level instructions and hooks point at the same first-move workflow.
- Owned-workspace changes that are more than trivial end on a feature branch with a PR for review and backup.

## QMD

```bash
scripts/token-reduce-paths.sh topic words
scripts/token-reduce-snippet.sh topic words
scripts/token-reduce-adaptive.sh topic words
```

If helpers are unavailable, use `qmd search "topic" -n 5 --files` or narrowly scoped `rg -n -g '<glob>' '<pattern>'`.

Semantic QMD is optional, not the default token-reduce path. For cheap discovery, stay on BM25 (`qmd search`) unless the user explicitly asks for QMD semantic setup or BM25 misses conceptual matches. When semantic QMD is requested, run `qmd embed` for the relevant collection, verify with `qmd status`, then smoke-test `qmd vsearch`/`qmd query`. QMD embeddings are local GGUF models via `node-llama-cpp` (QMD reports the active model, e.g. `embeddinggemma-300M`), not Ollama; GBrain's Ollama embeddings are a separate vector store. On CPU-only hosts, embedding can be slow, so prefer scoped batches such as `qmd embed -c <collection> --max-docs-per-batch 32 --max-batch-mb 8` and report progress. If QMD reports `Session expired`, Bun segfaults, or a command times out, it may still commit partial vectors; rerun with smaller batches and verify with `qmd status` plus a `qmd vsearch`/`qmd query` smoke test before claiming coverage.

Use GBrain for durable project memory and cross-session decisions; use QMD/token-reduce for current-repo discovery. Do not assume the two systems share vectors: GBrain may use Ollama embeddings, while QMD uses its own local GGUF embedding index.

Never start discovery with `find .`, `ls -R`, `grep -R`, `rg --files .`, broad `Glob`, or chained fallback shell logic.

## Flow

1. Check QMD once: `command -v qmd >/dev/null 2>&1 && qmd collection list 2>/dev/null | head -1`.
2. Known keyword/path: scoped search, then read only needed ranges.
3. Need an auto-routed kickoff: `scripts/token-reduce-adaptive.sh topic words`.
4. Unknown path: `scripts/token-reduce-paths.sh topic words`.
5. Need one excerpt: `scripts/token-reduce-snippet.sh topic words`.
6. Exact symbol impact: `uv run python scripts/token-reduce-structural.py --project-root . find-symbol ExactSymbol`.
7. More than five likely files or two failed searches: stop expanding and ask for narrower scope.
8. Final response: cite only the files needed to explain the result.

## Success

- Discovery starts with helper/QMD/scoped `rg`.
- Large files are read in slices.
- Output is concise unless the user asks for depth.
- Optional companions (`gh-axi`, `chrome-devtools-axi`, graph/review tools) are used only when installed and clearly cheaper.

See `references/feature-matrix.md` for full command/config details.

## AI Delegate Call Reduction (kimi-delegate / devin-delegate)

For owned workspace projects, default to the PR-backed delegation workflow:

1. Keep the parent agent as orchestrator, integrator, and final verifier.
2. Use `devin-delegate` wrappers for bounded research, writing, implementation, debugging, browser checks, and output drafting. Include workspace path, scope, constraints, acceptance checks, and expected output.
3. Use `kimi-delegate` wrappers for cheap parallel exploration and independent review. Prefer batched questions and file references over pasted code.
4. Do not call raw `devin`, raw `pi --provider kimi-coding`, or backgrounded delegate commands; wrappers preserve telemetry, fallback, and guardrails.
5. For non-trivial owned-repo changes, stage only relevant files, run the repo's validation, push a feature branch, and open a PR so the work is backed up off the server.

Orchestrator-to-subagent calls have fixed overhead (envelope, fallback wiring, telemetry). Reduce by:

### 1. Batch — 5 questions per call, not 1

```bash
# BAD: 5 calls × overhead
kimi-delegate --task "Check zero-value guard in submit()"
kimi-delegate --task "Check oracle replay protection"
...

# GOOD: 1 call, 5 questions, ~70% token savings
kimi-delegate --task "Answer CLEAN or FINDING+file:line for each:
Q1. StakingRouter.submit(): zero-value ETH guard?
Q2. reportModuleBeaconBalance: replay protection?
Q3-Q5. ..."
```

### 2. Reference, don't quote

```bash
# BAD (pastes 50 lines into prompt)
kimi-delegate --task "Review this: [code block]"

# GOOD (Kimi reads it itself — 30-70% cheaper)
kimi-delegate --task "Read OracleAdapter.sol:120-135. Does _validateSlashGuard
enforce a floor? CLEAN or FINDING."
```

### 3. Constrain output format

Append to every task: `"Answer CLEAN or FINDING+file:line. No preamble."` — cuts response tokens 40-60%.

### 4. Pre-compress context before delegating

```bash
./scripts/token-reduce-paths.sh "staking contracts" > /tmp/ctx.txt
kimi-delegate --task "..." --context-file /tmp/ctx.txt
```

### 5. Never background with `&` — use Agent tool for parallelism

`kimi-delegate ... 2>&1 &` writes to terminal FD, not the task output file.
Use `Agent(description=..., prompt="Use kimi-delegate ...")` instead.

### 6. Use plan_prompt.py envelope to reduce in-model planning

```bash
./skills/kimi-delegate/scripts/plan_prompt.py --task "audit X" > /tmp/envelope.txt
kimi-delegate --context-file /tmp/envelope.txt --task "execute the plan above"
```

Details: `references/meta-learnings-2026-05-31.md`
---
Read `references/token-reduction-guide.md` for benchmark notes and integration details.
Read `references/companion-tools.md` for how to evaluate future companion backends.
Read `references/graphify-evaluation.md` for the graphify companion verdict.
Read `references/caveman-evaluation.md` for the caveman companion verdict.
Read `references/axi-evaluation.md` for the AXI companion verdict.
Read `references/prompt-stack-intake-2026-04-18.md` for the 10-dependency prompt-stack intake verdict and evidence.
Read `references/feature-matrix.md` for the complete feature/command/config/telemetry map.
Read `references/meta-learnings-2026-04-18.md` for validated integration lessons and guardrails.
Read `references/meta-learnings-2026-04-19.md` for QMD indexing/routing synchronization lessons and latency/adoption follow-ups.
Read `references/meta-learnings-2026-04-25.md` for telemetry-window interpretation and diagnostics normalization lessons.
Read `references/meta-learnings-2026-05-06.md` for telemetry-driven instrumentation and propagation workflow lessons.
Read `references/meta-learnings-2026-05-20.md` for docs fast-path routing and weekly maintenance automation lessons.
Read `references/tier-value-profile.md` for keep/conditional/excluded dependency-tier decisions.
