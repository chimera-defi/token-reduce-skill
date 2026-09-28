#!/usr/bin/env python3
"""UserPromptSubmit reminder hook -- REMOVED 2026-09-28 (operator ruling).

This hook used to classify UserPromptSubmit prompts and inject a
TOKEN-REDUCE reminder (and set the PreToolUse enforcer's "pending" marker)
for discovery-shaped prompts. It was retired: telemetry showed 93% of its
firings were on harness-generated turns (task notifications, compaction
summaries, slash-command wrappers, etc.), and the false positives on real
human prompts had already been tightened out of the PreToolUse enforcer
directly, making the separate reminder redundant. See
references/worktree-deploy-sync.md for the consumer-coordination note, and
references/architecture.md / references/token-reduction-guide.md for the
current (enforcer-only) flow.

This file is kept ONLY because Etc-mono-repo's `.claude/settings.json`
invokes it raw (no `uv run`, no fail-open wrapper) via a symlinked copy of
this skill's `scripts/` directory:

    $CLAUDE_PROJECT_DIR/skills/token-reduce/scripts/remind-token-reduce.py

Deleting the file outright would make that consumer's UserPromptSubmit hook
error on a missing script on every prompt. It is safe to delete once no
consumer references it directly -- check with:

    grep -rn "remind-token-reduce.py" <consumer>/.claude/settings.json

Until then, this is a permanent no-op: it drains stdin (best-effort), never
emits a systemMessage or any other output, and always exits 0.
"""
import sys


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        # Absolute last resort: a UserPromptSubmit hook must never hard-fail.
        raise SystemExit(0)
