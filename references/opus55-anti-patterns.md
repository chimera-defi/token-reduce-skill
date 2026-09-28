# Opus 5.5 Guidance — Anti-Patterns and Enforcement Posture

Current models decide how much to read/think for themselves; token-reduce should not force
ritual pre-steps onto them. This note names the concrete anti-patterns enforcement actually
targets, and the posture that keeps enforcement from blocking ordinary work.

## Named anti-patterns

These are the wasteful patterns enforcement exists to catch — call them out by name instead of
a vague "reduce tokens" nag:

- Dumping a whole large file when a line range or a targeted `Grep` would do.
- `cat` / `head` / `tail` over a transcript, JSONL log, or other high-volume dump.
- Recursive `ls -R` / `find /` (or any unscoped root) with no depth limit.
- Re-reading a file you (or this turn) just edited — the harness already reflects the edit.
- An orchestrator doing multi-file discovery/audits itself instead of delegating to a subagent
  and reading its summary.

## Enforcement posture

- A hook must not block ordinary targeted work: reading a known file, a specific grep against
  an exact path, `git`/`gh` commands, running tests. `scripts/enforce-token-reduce-first.py`
  applies a targeted-vs-exploratory classification to Glob/Grep/Bash on every call — a specific
  `Grep(path=..., ...)` or `Glob("exact/name.py")` is never gated just because a prior prompt
  looked discovery-shaped. (There used to be a separate "pending" first-move discovery marker
  that applied a stricter variant of this classification; it was removed 2026-09-28 as dead code
  once nothing set the marker — see `references/worktree-deploy-sync.md`. `Read` is never gated
  by this hook at all.)
- Blocking is reserved for the named anti-patterns above, and even then a first-attempt broad
  Bash scan warns-and-allows once per session before a repeat attempt hard-blocks (see B3 in
  `scripts/enforce-token-reduce-first.py`); genuinely catastrophic patterns (`find /`, `rg
  --files .` at repo root) still hard-block immediately.
- `TOKEN_REDUCE_ENFORCE_MODE=warn` downgrades every would-be block to a telemetry-only warning
  — use it if enforcement is over-blocking in a way this doc doesn't already cover, and file
  that gap rather than routing around the hook silently.

## Subagent-first for broad discovery

For broad discovery, audits, or "sweep many files" work, the token saver is delegation, not a
bigger manual scan: spawn `Agent(subagent_type="Explore", ...)` for read-only search, or
`subagent_type="builder"` / `model="sonnet"` for implementation and deep-research fan-out, and
have it return conclusions + evidence instead of pulling every candidate file into the parent's
context. The `PreToolUse` block messages name this option directly — not just the CLI helper.
(There is no separate `UserPromptSubmit` reminder anymore; it was retired 2026-09-28 — see
`references/worktree-deploy-sync.md`.) See
`references/subagent-and-brain-integration.md` for the adaptive router's own subagent-emission
logic (`SUBAGENT_CANDIDATE_THRESHOLD`, `BROAD_SCOPE_TERMS`) once you've run it.

### Prefer config-backed advisory discovery when block compliance is poor
`enforcement: "advisory"` now does what the setup wizard advertises: ordinary broad
Bash/Glob/Grep discovery is recorded as a warning and allowed, while catastrophic scans
and symlink-root guards remain hard blocks. This is preferable to the legacy
`TOKEN_REDUCE_ENFORCE_MODE=warn` escape hatch when you want exploration freedom without
disabling the hard guards. If block telemetry shows agents mostly abandoning or rerouting
rather than using the suggested helper, advisory discovery avoids spending model turns on
policy-induced replanning.
