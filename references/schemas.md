# JSON Schemas — token-reduce

This document defines the JSON schemas used by the token-reduce skill's eval infrastructure.

---

## evals/evals.json

Defines eval test cases for the skill.

```json
{
  "skill_name": "token-reduce",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": [],
      "expectations": [
        "The agent used ./scripts/token-reduce-paths.sh or qmd search as the first discovery step",
        "The agent did not start with a broad Glob or find command"
      ]
    }
  ]
}
```

**Fields:**
- `skill_name`: Must match the skill's frontmatter name
- `evals[].id`: Unique integer
- `evals[].prompt`: Task to execute
- `evals[].expected_output`: Human-readable success description
- `evals[].files`: Optional input file paths (relative to skill root)
- `evals[].expectations`: Verifiable statements for the grader

---

## grading.json

Output from the grader agent. Located at `<run-dir>/grading.json`.

```json
{
  "expectations": [
    {
      "text": "The agent used ./scripts/token-reduce-paths.sh or qmd search as the first discovery step",
      "passed": true,
      "evidence": "First Bash call: './scripts/token-reduce-paths.sh hook enforcement'"
    }
  ],
  "summary": {
    "passed": 3,
    "failed": 1,
    "total": 4,
    "pass_rate": 0.75
  },
  "execution_metrics": {
    "tool_calls": { "Read": 2, "Bash": 3, "Grep": 1 },
    "total_tool_calls": 6,
    "total_steps": 4,
    "errors_encountered": 0,
    "output_chars": 1200,
    "transcript_chars": 4500
  }
}
```

**Critical:** Use exactly `text`, `passed`, `evidence` in expectations — not `name`/`met`/`details`.

---

## benchmark.json

Output from aggregate_benchmark.py.

```json
{
  "metadata": {
    "skill_name": "token-reduce",
    "skill_path": "/path/to/token-reduce",
    "executor_model": "claude-sonnet-4-6",
    "timestamp": "2026-03-30T00:00:00Z",
    "evals_run": [1, 2, 3, 4],
    "runs_per_configuration": 3
  },
  "runs": [
    {
      "eval_id": 1,
      "eval_name": "hook-enforcement-exploration",
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 1.0,
        "passed": 4,
        "failed": 0,
        "total": 4,
        "time_seconds": 28.5,
        "tokens": 4200,
        "tool_calls": 8,
        "errors": 0
      },
      "expectations": [
        {"text": "...", "passed": true, "evidence": "..."}
      ]
    }
  ],
  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.85, "stddev": 0.10},
      "time_seconds": {"mean": 30.0, "stddev": 5.0},
      "tokens": {"mean": 4000, "stddev": 500}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.30, "stddev": 0.15},
      "time_seconds": {"mean": 45.0, "stddev": 10.0},
      "tokens": {"mean": 8000, "stddev": 1500}
    },
    "delta": {
      "pass_rate": "+0.55",
      "time_seconds": "-15.0",
      "tokens": "-4000"
    }
  },
  "notes": []
}
```

**Important:** The `configuration` field must be exactly `"with_skill"` or `"without_skill"`.

---

## timing.json

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

Capture from task notification immediately — not persisted elsewhere.

---

## adoption-repo-*.json (token-reduce telemetry)

Output from `scripts/token-reduce-manage.sh measure`. Located at `artifacts/token-reduction/`.

```json
{
  "repo": "/path/to/repo",
  "session_count": 19,
  "discovery_compliance_pct": 47.4,
  "helper_usage_pct": 10.5,
  "broad_scan_violations": 4,
  "health_score": 40.5
}
```

This is the skill's own telemetry format — separate from the standard benchmark.json. Use `token-reduce-manage.sh measure` to generate it, `token-reduce-manage.sh review` for the review report.
