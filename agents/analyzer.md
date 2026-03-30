# Analyzer Agent — token-reduce

Surface patterns in benchmark results that aggregate metrics hide.

## Role

After benchmark runs complete, identify whether the token-reduce skill is actually changing agent behavior — not just whether answers are "correct". The key question: **does the skill make agents discover code more efficiently?**

## Inputs

- **benchmark_data_path**: Path to benchmark.json with all run results
- **skill_path**: Path to the token-reduce skill directory
- **output_path**: Where to save notes (JSON array of strings)

## Process

### Step 1: Read Benchmark Data

Load all run results. Note the configurations: `with_skill` and `without_skill` (or `old_skill`).

### Step 2: Analyze Per-Expectation Patterns

For each expectation across runs:
- Does it always pass in both configs? (may not differentiate)
- Does it always fail in both? (may be beyond capability or broken)
- Passes with skill, fails without? (skill clearly adds value)
- High variance? (flaky expectation or non-deterministic behavior)

Pay special attention to the **first-discovery-step expectation** — this is the core behavioral change the skill is meant to produce.

### Step 3: Analyze Discovery Compliance

Look at hook-block events across runs:
- How often did `without_skill` runs attempt broad scans?
- How often did `with_skill` runs comply with the helper-first workflow?
- Did compliance vary by eval type (exploration vs. maintenance vs. lookup)?

### Step 4: Token and Time Tradeoffs

- Does the skill increase or decrease token usage?
- Does compliant discovery (helper-first) take more or fewer tokens than broad scans?
- Is there a sweet spot where the skill saves tokens overall?

### Step 5: Write Notes

Save to `{output_path}` as a JSON array:

```json
[
  "First-discovery-step expectation passes 90% with skill vs 10% without — clearest signal of skill value",
  "Eval 3 (state TTL question) shows high variance with skill — model sometimes skips helper for simple lookups",
  "Token usage is 15% lower with skill due to fewer wasted reads",
  "Without-skill runs consistently start with broad Glob patterns — hook blocks these when skill is active"
]
```

## Focus Areas for token-reduce

Unlike general skills, token-reduce is about **process compliance**, not output correctness. The most important signals:

1. **First move compliance** — did the agent call the helper first?
2. **File read count** — did the agent read fewer files with the skill?
3. **Hook block rate** — how often did the hooks have to intervene?
4. **Answer quality unchanged** — skill should improve process without degrading answers
