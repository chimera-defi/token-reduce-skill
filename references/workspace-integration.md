# Workspace Integration

Add token-reduce to any repo in three steps:

1. Clone the skill into `tools/token-reduce-skill/`
2. Wire the hooks below into your `.claude/settings.json`
3. Add one line to your `AGENTS.md` or `CLAUDE.md`

For maximum savings also run `./tools/token-reduce-skill/scripts/setup.sh` to install QMD and RTK.

## Claude Code — Hook Wiring

Two hook layers work together:

- **token-reduce hooks** block wasteful discovery commands before they fire
- **RTK hook** (`~/.claude/hooks/rtk-rewrite.sh`) compresses output of commands that do run — install with `scripts/setup.sh` or `rtk init -g`

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
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
            "command": "uv run \"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/enforce-token-reduce-first.py"
          },
          {
            "type": "command",
            "command": "~/.claude/hooks/rtk-rewrite.sh"
          }
        ]
      },
      {
        "matcher": "Glob",
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/enforce-token-reduce-first.py"
          }
        ]
      },
      {
        "matcher": "Grep",
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/enforce-token-reduce-first.py"
          }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "uv run \"$CLAUDE_PROJECT_DIR\"/tools/token-reduce-skill/scripts/enforce-token-reduce-first.py"
          }
        ]
      }
    ]
  }
}
```

The RTK hook is a no-op if RTK is not installed — safe to include unconditionally.

## Repo Instructions (AGENTS.md / CLAUDE.md)

Add one line:

```text
If file location is unknown, start with ./tools/token-reduce-skill/scripts/token-reduce-paths.sh topic words before any Grep, Glob, or Read.
```

## Codex

```text
Use ./tools/token-reduce-skill/scripts/token-reduce-paths.sh for ambiguous repo discovery before broader search.
Use ./tools/token-reduce-skill/scripts/token-reduce-snippet.sh only when the file list is not enough.
Avoid find ., ls -R, grep -R, and rg --files . for first-pass discovery.
```

## Minimal Consumer Layout

```text
repo/
├── AGENTS.md          ← add one-line instruction above
├── .claude/
│   └── settings.json  ← add hook wiring above
└── tools/
    └── token-reduce-skill/  ← git clone here
```
