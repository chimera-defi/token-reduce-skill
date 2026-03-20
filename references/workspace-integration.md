# Workspace Integration

Use this package in a consumer repo by wiring three things:

1. discovery helper commands
2. guardrail hooks
3. short repo instructions that tell the agent to start with the helper

## Claude

Example project hook wiring:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/remind-token-reduce.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/advise-token-reduction.py"
          }
        ]
      },
      {
        "matcher": "Glob",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/enforce-glob-scope.py"
          }
        ]
      }
    ]
  }
}
```

Recommended repo instruction:

```text
If file location is unknown, start with ./tools/token-reduce-skill/scripts/token-reduce-paths.sh topic words.
If you need one ranked excerpt after the path list, use ./tools/token-reduce-skill/scripts/token-reduce-snippet.sh topic words.
Do not start with find ., ls -R, grep -R, rg --files ., or broad Glob patterns.
```

## Codex

Recommended repo instruction:

```text
Use ./tools/token-reduce-skill/scripts/token-reduce-paths.sh for ambiguous repo discovery before broader search.
Use ./tools/token-reduce-skill/scripts/token-reduce-snippet.sh only when the file list is not enough.
Avoid find ., ls -R, grep -R, and rg --files . for first-pass discovery.
```

## Minimal Consumer Layout

```text
repo/
├── AGENTS.md
├── .claude/settings.json
└── tools/
    └── token-reduce-skill/
```
