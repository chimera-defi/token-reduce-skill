# Token-Reduce Telemetry Evaluation & Improvement Plan

## Current State (2026-04-25)

### What Telemetry Tells Us Today

**Helper invocation telemetry** (`events.jsonl`) records:
- Tool, query, status, exit_code, latency_ms, chars/lines output
- Backend: `qmd_files`, `rg_content_hint`, `token-savior`, `adaptive`, `unknown`
- QMD sub-latency: `qmd_ensure_ms`, `qmd_files_ms`, `qmd_snippet_ms`, `fallback_ms`
- Adaptive routing: `tier`, `behavior_repeated_ratio`, `context_mode_recommended`, `code_review_graph_recommended`
- Context: `runtime`, `benchmark`, `test`

**Hook telemetry** records:
- `pending_marked` / `pending_cleared` — reminder hook activation
- `hook_block` — pre-tool blocks with tool name and blocked command/pattern
- `hook_error` — hook runtime failures

**Session parsing** (`measure_token_reduction.py`) scans Claude/Codex logs for:
- First-discovery compliance (QMD, helper, scoped rg vs broad scan)
- Helper adoption rate, mention-without-usage rate
- Companion usage: caveman, AXI tools
- Broad-scan violations per session

### What the Data Actually Shows

| Signal | Value | Interpretation |
|--------|-------|----------------|
| 14d total events | 201 | Small sample |
| Benchmark events | 186 (92.5%) | Latency stats are dominated by benchmark QMD collection creation |
| Runtime events | 11 (5.5%) | Very little real-world usage in this window |
| Runtime latency p95 | 12,392 ms | QMD collection creation/search dominates; structural is ~437 ms |
| 1d logging quality | 97.1 (high) | Recent instrumentation is excellent |
| 14d logging quality | 62.1 (low) | Legacy events drag aggregate down; benchmark events often miss full meta |
| Backend coverage (14d) | 14.7% | Old events lack backend tags |
| Backend coverage (runtime-only) | 71.4% | Recent runtime is much better |
| Pending leaks | 0 (current 14d) | State TTL + clear commands keep this in check |
| Hook blocks | Present but unmeasured post-action | We block, but don't know if the agent complies or escapes |

### Critical Gap: Benchmark Pollution

The 14d efficiency summary is **meaningless for runtime diagnosis** because:
- Benchmark runs create fresh QMD collections every iteration (`qmd_files_ms` ~8,900 ms)
- Runtime with fresh stamp should be fast, but runtime with collection refresh is also slow
- We cannot answer: "Is QMD hurting real users?" because benchmark tail swamps runtime signal.

### Critical Gap: No Outcome Correlation

We track **that** the helper ran, but not **whether it helped**:
- Did the agent read any of the files the helper returned?
- After a hook block, did the agent use the helper or find an escape hatch?
- Did `context_mode_recommended` or `code_review_graph_recommended` ever convert to actual usage?
- For adaptive tier routing, did `structural_symbol` return files the agent actually needed?

### Critical Gap: No Token Economics

We claim 71–83% savings vs broad scans in benchmarks, but telemetry has no per-session "tokens saved" signal. We cannot validate whether that claim holds in real Claude/Codex sessions.

---

## Improvement Plan

### P0: Context-Separated Efficiency Metrics

Split efficiency and logging summaries by context so runtime metrics are not drowned by benchmark noise.

**Target**: `token_reduce_telemetry.py` — `summarize_events()` returns `runtime_efficiency`, `benchmark_efficiency`, `test_efficiency` alongside the aggregate.

### P0: QMD Sub-Latency Percentiles in Summary

Currently `qmd_ensure_ms`, `qmd_files_ms`, `qmd_snippet_ms`, `fallback_ms` live in individual events but are **not summarized**. We can't see at a glance whether the 13s p95 is `ensure`, `files`, or `fallback`.

**Target**: `token_reduce_telemetry.py` — add `qmd_latency_breakdown` to efficiency summary with p50/p95 per sub-phase.

### P1: Post-Block Compliance Tracking

When `enforce-token-reduce-first.py` blocks a tool, we need to know what the agent does next. Add lightweight state to track the last block, and on the next tool use emit:
- `post_block_compliance` — next action is a helper kickoff
- `post_block_escape` — next action is another broad scan or different escape hatch
- `post_block_abandon` — session ends or switches to non-discovery topic

**Target**: `token_reduce_state.py` (add block state), `enforce-token-reduce-first.py` (read/write block state), `remind-token-reduce.py` (check block state on new prompt).

### P1: Helper Result Utilization

Track whether files returned by `token-reduce-paths` / `token-reduce-snippet` are actually consumed.

Approach: log `files_returned` (list of paths) in helper meta, then in session parsing (`measure_token_reduction.py`) check whether subsequent `Read` or `Grep` tool calls reference those paths.

**Simpler immediate approach**: add `files_returned_count` and `top_returned_paths` to helper meta. This alone enables future utilization analysis.

**Target**: `token-reduce-paths.sh`, `token-reduce-snippet.sh` (capture output paths), `token_reduce_telemetry.py` (store in meta).

### P1: Discovery Outcome Classification per Session

In `measure_token_reduction.py`, after detecting a helper invocation in a session, classify the remainder:
- `direct_hit` — agent reads files that match helper-returned paths within 5 tool calls
- `indirect_hit` — agent greps within helper-returned files within 5 tool calls
- `miss` — agent performs broad scan after helper
- `standoff` — no further discovery action after helper (task completed or abandoned)

**Target**: `measure_token_reduction.py` — new `discovery_outcomes` section in the report.

### P2: Companion Recommendation Conversion

Adaptive router emits `context_mode_recommended` and `code_review_graph_recommended` flags. We should track conversion:
- Add `companion_recommended` event with `companion=name`, `reason=adaptive_router`
- In session parsing, detect if the companion tool was invoked within N turns
- Emit `companion_accepted` or `companion_ignored`

**Target**: `token_reduce_adaptive.py`, `measure_token_reduction.py`.

### P2: Estimated Tokens Saved Heuristic

Add a lightweight heuristic to helper events:
```
estimated_tokens_saved = max(0, (repo_file_count × avg_lines_per_file × 4) - (helper_output_chars + subsequent_targeted_read_chars))
```
Or simpler: `files_in_repo`, `files_returned`, `scope_reduction_pct`.

This lets us trend savings without perfect token counting.

**Target**: `token-reduce-search.sh` (count `rg --files` for repo size), helper wrapper scripts (compute scope_reduction_pct).

---

## Files To Modify

1. `scripts/token_reduce_telemetry.py` — context-separated summaries, QMD sub-latency percentiles
2. `scripts/token_reduce_state.py` — post-block state primitives
3. `scripts/enforce-token-reduce-first.py` — write block state, emit post-block events
4. `scripts/remind-token-reduce.py` — check post-block state on prompt submit
5. `scripts/token-reduce-paths.sh` — capture `files_returned` from output
6. `scripts/token-reduce-snippet.sh` — capture `files_returned` from output
7. `scripts/measure_token_reduction.py` — discovery outcome classification
8. `scripts/review_token_reduction.py` — surface new findings from improved telemetry

---

## Expected Impact

| Improvement | What We Learn | Decision It Enables |
|-------------|---------------|---------------------|
| Context-separated latency | Real QMD latency vs benchmark artifact | Whether to lower runtime timeout or invest in QMD optimization |
| QMD sub-latency percentiles | Collection creation vs search vs fallback cost | Where to invest optimization effort |
| Post-block compliance | Hook effectiveness | Whether hooks need stricter coverage or softer guidance |
| Helper utilization | Helper quality (not just usage) | Whether to tune QMD ranking, rg fallback, or adaptive tiering |
| Discovery outcome | End-to-end discovery success | Whether "compliance" is a vanity metric or a quality metric |
| Companion conversion | Recommendation quality | Whether to keep/remove context_mode/code_review_graph recommendations |
| Estimated savings | Real-world ROI vs benchmark claims | Whether the skill's stated savings hold up in practice |
