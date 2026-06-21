# AI Delegate Call Reduction (via the delegate-skill router)

Delegate *selection* goes through the `delegate-skill` router — do not hand-pick a delegate or hardcode one wrapper. The router maps the task to the right backend and keeps the parent context small (only the result summary returns):

| Task | Router picks | Wrapper |
|------|--------------|---------|
| Browser / UI / screenshot / sandbox | devin | `devin-delegate` |
| Cheap research / review / summarize / draft | kimi | `kimi-delegate` |
| Multi-file refactor / large codebase | grok | `grok-delegate` |
| Local Codex write-mode implementation | spark | `/spark` |
| Unknown scope | kimi to scope, then escalate | `kimi-delegate` |

For owned workspace projects, default to the PR-backed delegation workflow:

1. Keep the parent agent as orchestrator, integrator, and final verifier.
2. Pick the delegate with the `delegate-skill` router, not by hand. See `delegate-skill/SKILL.md` for the full routing table and health checks.
3. Always call the wrapper the router names (`devin-delegate`, `kimi-delegate`, `grok-delegate`, `/spark`) — never raw `devin`, raw `pi --provider kimi-coding`, or backgrounded delegate commands. Wrappers preserve envelope checks, fallback, and telemetry.
4. Give every delegate the workspace path, scope, constraints, acceptance checks, and expected output. Prefer batched questions and file references over pasted code.
5. For non-trivial owned-repo changes, stage only relevant files, run the repo's validation, push a feature branch, and open a PR so the work is backed up off the server.

The call-reduction tips below apply to whichever wrapper the router selects (written here as `<delegate>-delegate`). Orchestrator-to-subagent calls have fixed overhead (envelope, fallback wiring, telemetry). Reduce by:

## 1. Batch — 5 questions per call, not 1

```bash
# BAD: 5 calls × overhead
<delegate>-delegate --task "Check zero-value guard in submit()"
<delegate>-delegate --task "Check oracle replay protection"
...

# GOOD: 1 call, 5 questions, ~70% token savings
<delegate>-delegate --task "Answer CLEAN or FINDING+file:line for each:
Q1. StakingRouter.submit(): zero-value ETH guard?
Q2. reportModuleBeaconBalance: replay protection?
Q3-Q5. ..."
```

## 2. Reference, don't quote

```bash
# BAD (pastes 50 lines into prompt)
<delegate>-delegate --task "Review this: [code block]"

# GOOD (the delegate reads it itself — 30-70% cheaper)
<delegate>-delegate --task "Read OracleAdapter.sol:120-135. Does _validateSlashGuard
enforce a floor? CLEAN or FINDING."
```

## 3. Constrain output format

Append to every task: `"Answer CLEAN or FINDING+file:line. No preamble."` — cuts response tokens 40-60%.

## 4. Pre-compress context before delegating

```bash
./scripts/token-reduce-paths.sh "staking contracts" > /tmp/ctx.txt
<delegate>-delegate --task "..." --context-file /tmp/ctx.txt
```

## 5. Never background with `&` — use Agent tool for parallelism

`<delegate>-delegate ... 2>&1 &` writes to terminal FD, not the task output file.
Use `Agent(description=..., prompt="Use <delegate>-delegate ...")` instead.

## 6. Build the envelope with the wrapper to reduce in-model planning

```bash
# --print-envelope emits the structured plan; no per-skill script paths needed
<delegate>-delegate --print-envelope --task "audit X" > /tmp/envelope.txt
<delegate>-delegate --context-file /tmp/envelope.txt --task "execute the plan above"
```

Details: `references/meta-learnings-2026-05-31.md`
