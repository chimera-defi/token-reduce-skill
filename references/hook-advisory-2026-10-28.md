# Nonblocking hook follow-up, 2026-10-28

Scope: source changes in `tr/enhance-1028b`. No settings, installed hooks,
other worktrees, or global executables changed. The setup generator was tested
by evaluating its command assignment in isolation; setup itself was not run.

## Decisions and evidence

- Advisory decisions now emit `hook_warn`, status `warn`. Explicit legacy
  test-mode blocks retain `hook_block`, status `blocked`. Summary counts also
  interpret historical `hook_block`/`warn` records as warnings without editing
  the append-only log.
- Only the symlink-root correctness hint emits model context. Other discovery
  warnings remain telemetry-only. Its JSON contains only `hookSpecificOutput`
  with `hookEventName: PreToolUse` and `additionalContext`; it does not request
  a permission decision. Duplicate invocations replay the same context without
  another telemetry event. Advisory mode cannot replay a cached legacy block.
- Installed `claude --version` reports **2.1.308**. Inspection of
  `/home/agents/.npm-global/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`
  found `additionalContext` in the `PreToolUse` output schema and its consumer
  (`case"PreToolUse"`, `Dr(e,"additionalContext",n.additionalContext)`). This
  verifies the installed implementation, rather than relying on remembered
  hook documentation. Actual model-turn injection was not exercised.
- The setup generator now resolves an absolute system Python interpreter for
  the standard-library-only hook instead of running uv on each tool call. It
  forces advisory mode, forwards the hint, suppresses spawn errors, keeps the
  five-second timeout, and always exits zero. Missing scripts, crashes, timeout,
  and an inherited legacy block opt-in are covered by subprocess tests.
- Advisory `Read` calls return before repository/state lookup. The prior path
  ran repository discovery despite having no Read policy.

## Telemetry and classifier limits

At the initial inspection, `artifacts/token-reduction/events.jsonl` contained
one helper invocation from this session and **zero hook events**. No runtime
frequency ranking or false-positive rate can be inferred from that sample.
Later repository tests wrote synthetic records; those are not operator usage
evidence. Other worktrees' event logs were not inspected.

The supplied examples were reproduced as synthetic classifier inputs:

| Input | Before | After |
| --- | --- | --- |
| `cd ~; du -sh paths` | No scan flags | No scan flags; repeated-call regression added |
| `find /tmp -name x -maxdepth 6` | Catastrophic and broad | Broad only |
| `find /tmp -maxdepth 1` | Catastrophic and broad | No scan flags |
| `find / -name x` | Catastrophic and broad | Catastrophic and broad |

A depth bound on a named directory removes the catastrophic classification.
Depth six still merits broad advice because depth does not bound output count.
There is no new exemption for arbitrary bounded scans or disk-summary commands.
These examples establish regression behavior, not a population precision score.

## Startup measurement

25 interleaved observations per variant/tool after one warmup; identical
Python **3.12.3**; temporary state; synthetic targeted inputs. The before source
was extracted from commit `5116aa5` with `git show`, without another worktree.
Both uv variants used `--offline --no-project --python /usr/bin/python3`.
Commands were passed as hook input and were not executed as filesystem scans.
The measurement covers process invocation through hook exit, excluding Claude's
own hook scheduling. It uses payloads without `tool_use_id`.

| Tool | Before via uv median / p95 ms | After via uv median / p95 ms | After direct Python median / p95 ms |
| --- | --- | --- | --- |
| Read | 71.67 / 88.91 | 68.72 / 89.95 | 61.66 / 75.49 |
| Bash | 73.42 / 84.78 | 74.17 / 77.59 | 66.60 / 73.20 |
| Glob | 80.86 / 88.44 | 79.08 / 87.04 | 72.16 / 77.56 |
| Grep | 72.62 / 79.34 | 73.05 / 83.09 | 64.88 / 72.13 |

The combined source/launcher changes save **6.82–10.01 ms** median per
call (about **9–14%**) in this sample. Small source-only differences should
not be treated as significant beyond this sample. Full aggregate results are
local at `artifacts/token-reduction/hook-startup-comparison.json`.

## Verification and unperformed work

- Repository tests: `uv run --offline --no-project --python /usr/bin/python3
  python -m pytest -q scripts/tests`. System pytest was used because the
  default uv interpreter lacked pytest and dependency download was unavailable.
  Final output tail: **358 passed in 39.35s**. `git diff --check` and
  `bash -n scripts/setup.sh` also pass.
- Repo-scoped `token-reduce-manage.sh measure` and `review` completed. The review
  reflects this session's sparse telemetry, not host-wide adoption evidence.
- `token-reduce-manage.sh validate`: skill package validation passes; benchmark
  validation exits 1 because the existing local and composite benchmark artifacts
  are 55 days old, exceeding the 14-day limit. They were not rewritten or skipped.
- Cross-workspace `improve-adoption` was not run because this task restricts work
  to this directory. A release gate was not run for this bounded hook fix.
- Commit not created: staging failed because the sandbox cannot create
  `index.lock` in the worktree's Git metadata directory (read-only filesystem).
  Source edits and new files remain in this worktree, unstaged. No merge or push
  was attempted.

Proposed, not performed: activate the tested launcher in settings in a separate
authorized task; obtain a sanitized runtime hook-event sample before further
classifier tuning; refresh the unrelated stale benchmark artifacts separately.
Existing settings still invoke uv and discard stdout, so activation is required
to realize the startup savings and advisory context in configured Claude sessions.
