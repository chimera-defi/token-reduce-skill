# Telemetry Design Review — 2026-09-12

Scope: `scripts/token_reduce_telemetry.py`, `scripts/composite_token_telemetry.py`,
`scripts/session_metrics_cache.py`, `scripts/adoption_report.py`, plus the files they
depend on (`scripts/enforce-token-reduce-first.py`, `scripts/token_reduce_state.py`,
`scripts/command_rewrites.py`, `scripts/measure_token_reduction.py`) read for context.
Read-only review — no code was changed as part of this task.

Bottom line: the biggest problem is **(a)**, and it is not merely a counting artifact —
it also corrupts the enforcement policy's own internal state, which was reproduced live,
in this session, against real hook output (see Appendix). **(b)** is confirmed by code
and is live-corroborated by a second concurrent process writing the same shared file
during this review. **(c)** is a real design gap but is currently latent (no consumer
sums it yet). **(d)** — the cache added in `b219c77` — is correctly designed; no defect
found.

## (a) Double hook registration → double-counted events AND a broken warn/block threshold

**Confirmed, not hypothetical.** Both settings files register the same hook script for
the same tool matchers, in this exact repo, right now:

- Global: `/home/agents/.claude/settings.json:39,43` (Bash), `:48,52` (Glob), `:57,61`
  (Grep), `:66,70` (Read) — all four invoke
  `/home/agents/.claude/hooks/token-reduce/enforce-token-reduce-first.py`.
- Repo: `.claude/settings.json:13-53` — all four matchers invoke
  `${CLAUDE_PROJECT_DIR}/scripts/enforce-token-reduce-first.py`.
- The two script files are **byte-identical** (`diff` returns nothing).

Claude Code runs every matching `PreToolUse` hook entry for a tool call and blocks if
*any* of them returns a block decision. With both settings files registered, every
Bash/Glob/Grep/Read call in this repo is evaluated by **two independent subprocesses**
against the same stdin payload.

Consequences, both confirmed:

1. **Telemetry double-counting.** `record_event()` (`scripts/token_reduce_telemetry.py:34-60`)
   is a bare JSONL append with no idempotency key (no event id, no dedup on
   timestamp+tool+command). `block()` (`scripts/enforce-token-reduce-first.py:88-124`)
   and `warn_and_allow()` (`:127-158`) each call `record_event()` once per hook
   invocation, so a single logical tool call that gets blocked or warned produces
   **two** `hook_block`/`hook_warn` lines. The same doubling applies to
   `post_block_compliance` / `post_block_escape` / `post_block_abandon`, recorded at
   `:436-494`.

2. **State corruption, not just logging.** The warn-once/block-on-repeat policy
   (`:566-592`) reads `broad_attempt_count(repo, sk)`, then writes
   `record_broad_attempt(repo, sk)` — a plain read-modify-write against a JSON file on
   disk (`scripts/token_reduce_state.py:167-190`), with no lock. Because both hook
   invocations run this same read-modify-write against the same counter for the same
   tool call, the counter advances by **2 per tool call** instead of 1. The exact
   invocation that flips block-vs-warn is race-dependent (order of the two subprocesses
   isn't guaranteed), so the defensible claim is: **the warn-once/block-on-repeat
   threshold is effectively reached in about half the intended number of attempts**,
   not that a specific call number always blocks.

Everything downstream inherits this: `measure_token_reduction.py:539-540` builds its
`"telemetry"` key from `summarize_events(load_events(...))` over the same doubled
`events.jsonl`, which feeds `composite_token_telemetry.py`'s
`realized_outcomes_summary()` (`:249-377`, via `helper_error_rate_pct`,
`failure_overhead_pct`, `logging_quality_score`) and `dependency_overhead_summary()`
(`:380-436`, via `helper_error_calls`, `rapid_repeat_calls`, `hook_error_count`,
`pending_leak_count`). The composite's `confidence_score` (`:322-328`, scaled off raw
`telemetry_events` count) is also inflated by the doubling, so the pipeline reports
*more* confidence in a *less* accurate number.

**Fix (not applied — out of scope for this review):** deregister one of the two
`PreToolUse` entries (repo-only is sufficient since the script is per-repo state
anyway), or make `record_event`/`record_broad_attempt`/`record_block` idempotent per
tool-call (e.g., key on `(session_key, tool_name, command_hash, timestamp_bucket)` and
skip if already seen within a short window).

## (b) `last_block.json` is per-repo, not per-session — confirmed by code and live-corroborated

`scripts/token_reduce_state.py:210-211`:

```python
def block_state_path(repo: Path) -> Path:
    return state_dir(repo) / "last_block.json"
```

No session key anywhere in the path. `record_block()` (`:214-223`) always writes this
one file; `consume_block()` (`:226-244`) always reads-and-deletes this one file,
regardless of which session's tool call triggered the read. Contrast with
`broad_attempt_*.json` (`:162-165`) and the pending-discovery state (`:105-159`), both
of which *are* correctly keyed by `session_key`. The block state is the one piece of
state that was not given the same treatment.

Effect: if two sessions are active in the same repo/worktree close enough in time that
session A's block hasn't aged out (`BLOCK_TTL_SECONDS = 300`, `:57`), session B's *next*
tool call — whatever it is — walks into `main()`'s post-block-compliance check
(`:436-494`) and gets attributed a `post_block_compliance`/`post_block_escape`/
`post_block_abandon` event for a block it never triggered.

This is not a paper risk: during this review, `.claude/token-reduce-state/` and
`artifacts/token-reduction/events.jsonl` in this exact worktree were being written
concurrently by session key `c1f181f0-953e-4aad-8362-fea138a18922` (this review) *and*
by at least one other process using synthetic session keys (`diag-fake-0912`,
`diag-fresh-cold-0912`, `diag-fresh-cold-0912b` — see Appendix), almost certainly the
other builder exercising the hook directly. Both were writing into the same singleton
`last_block.json` in the same repo. Any overlap between a real session's block and a
concurrent test/session's next call is misattributed under the current design.

**Estimated distortion:** proportional to how often two sessions/processes touch the
same repo within a 5-minute window of each other. In a single-session-at-a-time repo
this defect is dormant; in this worktree, right now, with two active processes, it is
live. Cannot give a precise historical percentage without a concurrent-session
timeline, but the mechanism is unambiguous and the collision window (5 minutes) is wide
relative to typical tool-call cadence.

## (c) `estimated_output_tokens` — unvalidated, and currently latent (not actively inflating anything)

`scripts/command_rewrites.py:135-161`, `estimate_output_tokens()`: fixed constants keyed
purely on command-pattern matching, no run-time measurement, ever:

```python
if is_catastrophic(cmd):
    return 50_000
if _FIND_NAME_RE.search(cmd):
    return 5_000
if re.search(r"\bgrep\s+-[a-zA-Z]*R", cmd):
    return 8_000
if re.search(r"\brg\s+--files\b", cmd):
    return 4_000
if re.search(r"\bls\s+-[a-zA-Z]*R", cmd):
    return 3_000
```

No code path anywhere in the repo captures a blocked/warned command's *actual* output
size and compares it to this estimate. The number is written into event `meta` at
`scripts/enforce-token-reduce-first.py:112` (block) and `:153` (warn) and then never
read again — a repo-wide grep for `estimated_output_tokens` outside
`enforce-token-reduce-first.py` returns nothing. `token_reduce_telemetry.summarize_events()`
does not sum it; `composite_token_telemetry.py` does not sum it; `adoption_report.py`
does not reference it.

So: **today, this is a design gap, not an active distortion** — there is no "tokens
saved" headline metric being computed from it, so it cannot currently be overclaiming
savings. The risk is **latent**: the moment someone wires up a "total tokens saved"
rollup by summing this field (a natural thing to build, and exactly the kind of number
this project's own composite report already gestures at with
`potential_savings_pct`/`realized_savings_estimate_pct`), it will count every blocked
attempt as a full save — including the `post_block_escape` cases
(`enforce-token-reduce-first.py:479`) where the agent immediately ran an equivalent
broad command anyway and got the real output tokens regardless. The escape/compliance
split already exists in the event stream; a future savings rollup needs to gate on
`post_block_compliance` (or at minimum exclude `post_block_escape`) before treating a
block's `estimated_output_tokens` as realized savings, and even then the number is a
heuristic ceiling, not a measurement.

## (d) `session_metrics_cache.py` (from `b219c77`) — correctly designed, no defect found

Reviewed `scripts/session_metrics_cache.py` in full plus its call sites in
`scripts/measure_token_reduction.py:86-91, 409-453`.

- Cache key is content-based: `fingerprint_files()` (`session_metrics_cache.py:65-80`)
  stat's every constituent file and records `(path, mtime_ns, size)`, sorted. `get()`
  (`:104-112`) only returns a hit when the *current* fingerprint matches exactly what
  was cached — any change to mtime or size on any constituent file is a miss.
- The file set per cache entry is re-globbed fresh on every call, not stored:
  `session_related_files()` (`measure_token_reduction.py:86-91`) re-globs
  `<session>/subagents/*.jsonl` each time it's called, so a subagent transcript that
  appears *after* the parent session file was last cached correctly changes the
  fingerprint (different file list → different fingerprint → miss → recompute), even
  though the parent file's own mtime/size didn't change.
- No TTL is used, which is the right call here — session transcripts are immutable once
  a session ends, so content-based invalidation (not time-based) is the correct model,
  and the docstring (`:29-32`) says so explicitly.
- Incremental flush every `cache_flush_every` (default 20) files (`measure_token_reduction.py:441-449`)
  bounds lost work on a killed run without needing a lock; `prune_stale()`
  (`session_metrics_cache.py:118-136`) drops entries whose primary file was deleted.
- `events.jsonl` (the file affected by the (a)/(b) defects above) is **not** part of
  this cache at all — `token_reduce_telemetry.summarize_events(load_events(...))` is
  called directly, unconditionally, on every `measure()` invocation
  (`measure_token_reduction.py:539-540`), so the (a)/(b) distortions are not masked or
  amplified by caching; they flow straight through fresh every time.

Only a theoretical, practically-negligible caveat: `mtime_ns` collisions combined with
an unchanged file size could in principle produce a false hit on a filesystem with very
coarse mtime resolution, but append-only JSONL growth almost always changes `size` too,
so this is not a real-world risk for this data shape. No fix recommended.

## (e) What should be measured that isn't

Proposed minimal additions, in priority order:

1. **Double-block dedup rate** — the most urgent, because it would have caught (a)
   directly. Emit a stable `call_id` (hash of `session_key` + `tool_name` + raw
   `tool_input` + a coarse timestamp bucket, e.g. 1s) on every hook decision, and report
   what fraction of `hook_block`/`hook_warn`/`post_block_*` events share a `call_id`
   with another event within a short window. This single number would have surfaced the
   settings.json double-registration months ago instead of requiring a live repro.
2. **Time-to-compliance** — for each `hook_block`/`hook_warn`, the wall-clock gap to the
   agent's next helper invocation (or to `post_block_compliance`). Currently the
   pipeline only records the binary compliance/escape/abandon classification, not how
   long compliance took — useful for distinguishing "agent adapted immediately" from
   "agent flailed for 10 tool calls first."
3. **Silent-false-negative rate** — commands that were *not* flagged by
   `BROAD_BASH_PATTERNS`/`matches_any_broad_pattern`/`is_exploratory_rg` but whose actual
   output (if ever captured — see below) was large. Requires at least sampling real
   output size for a subset of allowed commands to calibrate against; today nothing
   measures what got through.
4. **Cold-start storm indicator** — count of hook invocations within the same
   short window across *distinct* `session_key`s in the same repo (this review
   personally hit this: two sessions, `c1f181f0-...` and `diag-*`, wrote to the same
   `events.jsonl`/`last_block.json` inside minutes of each other). This both flags (b)'s
   collision risk directly and would catch workspace-wide bulk-launch contention on the
   shared per-repo state files.
5. **Validated savings sample** — for a small sample of blocked commands, actually run
   the would-have-run command in a sandboxed/measured context and compare real output
   token count to `estimate_output_tokens()`'s prediction, to give the heuristic
   constants (50k/5k/8k/4k/3k) an empirical basis instead of round numbers.

None of these require new instrumentation infrastructure — `record_event()` already
accepts an arbitrary `meta` dict; items 1-2 are achievable by adding a couple of fields
to existing call sites (not done here — out of scope for a read-only review, and two of
the touched files are the other builder's).

## Appendix: live evidence captured during this review

Excerpted from `artifacts/token-reduction/events.jsonl` in this worktree, during this
session (`session_key: c1f181f0-953e-4aad-8362-fea138a18922`). Two Bash calls I issued
once each produced two `hook_block` events, ~7-8ms apart, with the attempt counter
incremented twice:

```
{"event":"hook_block","meta":{"attempt_count":3,...},"status":"blocked","timestamp":"2026-09-12T14:25:23.735022+00:00"}
{"event":"hook_block","meta":{"attempt_count":4,...},"status":"blocked","timestamp":"2026-09-12T14:25:23.742255+00:00"}
...
{"event":"hook_block","meta":{"attempt_count":5,...},"status":"blocked","timestamp":"2026-09-12T14:25:26.338754+00:00"}
{"event":"hook_block","meta":{"attempt_count":6,...},"status":"blocked","timestamp":"2026-09-12T14:25:26.346506+00:00"}
```

And a `hook_warn` immediately followed (~12ms later) by a `hook_block` for the *same*
command text and the *same* session key — i.e. what should have been a first-attempt
warn-and-allow was also independently evaluated a second time against already-bumped
state and hard-blocked:

```
{"event":"hook_warn","meta":{"attempt_count":1,"command":"cat pyproject.toml...","reason":"broad bash scan",...},"status":"warn","timestamp":"2026-09-12T14:24:16.615129+00:00"}
{"event":"hook_block","meta":{"attempt_count":2,"command":"cat pyproject.toml...","policy":"repeat_broad",...},"status":"blocked","timestamp":"2026-09-12T14:24:16.626942+00:00"}
```

The same file also carries entries from a concurrent process using synthetic session
keys (`diag-fake-0912`, `diag-fresh-cold-0912`, `diag-fresh-cold-0912b`) writing to the
same `events.jsonl` and the same singleton `last_block.json` during this window —
direct, live corroboration of the (b) per-repo-not-per-session sharing risk.
