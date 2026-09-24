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
  applies the same targeted-vs-exploratory classification to Glob/Grep/Read/Bash whether or not
  a discovery prompt has set the session's "pending" marker — a specific `Grep(path=..., ...)`
  or `Glob("exact/name.py")` is never gated just because the prompt looked discovery-shaped.
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
context. Both the `UserPromptSubmit` reminder and the `PreToolUse` block messages name this
option directly — they no longer only point at the CLI helper. See
`references/subagent-and-brain-integration.md` for the adaptive router's own subagent-emission
logic (`SUBAGENT_CANDIDATE_THRESHOLD`, `BROAD_SCOPE_TERMS`) once you've run it.
