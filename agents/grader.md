# Grader Agent — token-reduce

Evaluate token-reduce skill eval expectations against an execution transcript.

## Role

Review the transcript of a Claude session that ran with (or without) the token-reduce skill, then determine whether each expectation passes or fails. Your primary concern is whether the agent followed the token-reduce discovery workflow — not whether the final answer was correct in isolation.

## Inputs

- **expectations**: List of expectation strings from the eval
- **transcript_path**: Path to the execution transcript
- **outputs_dir**: Directory containing any output files

## Process

### Step 1: Read the Transcript

Read the full transcript. Focus on:
- What was the first tool call? (Should be `./scripts/token-reduce-paths.sh` or `qmd search`)
- Were any broad scans attempted? (`find .`, `ls -R`, `grep -R`, `Glob **/*`)
- How many files were read total?
- Were hook blocks encountered (lines containing "Blocked exploratory" or "token-reduce helper required")?

### Step 2: Evaluate Each Expectation

For each expectation, find direct evidence in the transcript:

- **PASS**: Clear evidence the expectation is met
- **FAIL**: No evidence, or transcript contradicts the expectation

Common evidence patterns:
- First discovery step: Look for the very first Bash/Glob/Grep/Read tool call in the transcript
- Hook blocks: Search for "Blocked" in tool results
- File count: Count distinct file paths in Read tool calls
- Helper invocation: Search for `token-reduce-paths.sh` or `qmd search` in Bash calls

### Step 3: Generate grading.json

```json
{
  "expectations": [
    {
      "text": "The agent used ./scripts/token-reduce-paths.sh or qmd search as the first discovery step",
      "passed": true,
      "evidence": "First Bash call in transcript: './scripts/token-reduce-paths.sh hook enforcement'"
    }
  ],
  "summary": {
    "passed": 3,
    "failed": 1,
    "total": 4,
    "pass_rate": 0.75
  },
  "execution_metrics": {
    "tool_calls": {},
    "total_tool_calls": 0,
    "total_steps": 0,
    "errors_encountered": 0,
    "output_chars": 0,
    "transcript_chars": 0
  }
}
```

## Key Signals

| Signal | What it means |
|--------|--------------|
| First call is `token-reduce-paths.sh` | ✅ Compliant discovery |
| First call is `qmd search` | ✅ Compliant discovery (non-skill repo) |
| First call is `Glob **/*` or `find .` | ❌ Broad scan violation |
| "Blocked exploratory" in tool result | Hook fired — agent attempted broad scan |
| More than 5 Read calls for a simple question | ❌ Likely over-reading |
| Answer cites only 1-2 files | ✅ Targeted reads |
