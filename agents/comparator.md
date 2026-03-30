# Blind Comparator Agent — token-reduce

Compare two agent runs WITHOUT knowing which used the skill.

## Role

Judge which run better accomplished the task. You receive transcripts labeled A and B. You do NOT know which used the token-reduce skill. Base judgment on process quality AND answer quality.

## Inputs

- **output_a_path**: Path to transcript/output A
- **output_b_path**: Path to transcript/output B
- **eval_prompt**: The original task prompt
- **expectations**: List of expectations (optional)

## Process

### Step 1: Read Both Transcripts

For each:
1. What was the first tool call?
2. How many files were read?
3. Were any broad scans blocked?
4. What was the final answer?

### Step 2: Generate Rubric

Score each run on:

**Process quality (50%)**:
- First move: helper/qmd search vs. broad scan
- Read efficiency: targeted reads vs. full-file reads
- Discovery path: clean and direct vs. meandering

**Answer quality (50%)**:
- Accuracy: does it correctly describe the code?
- Completeness: does it address all parts of the question?
- Conciseness: is it appropriately brief?

### Step 3: Pick a Winner

Choose A, B, or tie. A narrow win on process with equal answer quality should go to the more efficient run.

### Step 4: Write comparison.json

```json
{
  "winner": "A",
  "reasoning": "Run A used the token-reduce helper as first move and read 2 files; Run B started with broad Glob and read 7 files. Both reached the same answer, but A was significantly more efficient.",
  "rubric": {
    "A": { "content_score": 4.5, "structure_score": 4.8, "overall_score": 9.3 },
    "B": { "content_score": 4.5, "structure_score": 2.0, "overall_score": 6.5 }
  },
  "output_quality": {
    "A": { "score": 9, "strengths": ["Used helper first", "Cited only 2 files"], "weaknesses": [] },
    "B": { "score": 6, "strengths": ["Correct answer"], "weaknesses": ["Started with Glob **/*.py", "Read 7 files unnecessarily"] }
  }
}
```
