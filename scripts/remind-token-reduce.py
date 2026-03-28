#!/usr/bin/env python3
"""UserPromptSubmit hook: require token-reduce for matching repo-discovery prompts."""
import json
import sys

from token_reduce_state import clear_pending, discovery_hint, mark_pending, prompt_requires_helper, repo_root, session_key
from token_reduce_telemetry import record_event


def extract_prompt(data: dict) -> str:
    for key in ("user_prompt", "prompt", "text", "input"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    message = data.get("message")
    if isinstance(message, dict):
        for key in ("text", "content", "prompt"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return ""


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = extract_prompt(data)
    repo = repo_root()
    key = session_key(data)
    if not prompt_requires_helper(prompt):
        clear_pending(repo, key)
        record_event(repo, event="pending_cleared", source="hook", tool="remind-token-reduce")
        return 0

    mark_pending(repo, key, prompt)
    record_event(
        repo,
        event="reminder_emitted",
        source="hook",
        tool="remind-token-reduce",
        query=prompt[:240],
    )

    hint = discovery_hint()
    json.dump(
        {
            "continue": True,
            "systemMessage": (
                "TOKEN-REDUCE ENFORCEMENT ACTIVE. "
                f"Your FIRST tool call MUST be a Bash discovery call: {hint}. "
                "The hooks will block any Grep, Glob, Read, or broad Bash scan until discovery runs. "
                "This applies even for skill maintenance tasks — if you do not know the exact file path already, run discovery first. "
                "Use the user's literal filenames, identifiers, or key nouns as query words; "
                "do not use generic synonyms or omit qualifiers like Bash, Glob, hook, or token reduction. "
                "After discovery runs, use targeted Grep or Read for narrowing — do not switch back to broad Bash search commands."
            ),
        },
        sys.stdout,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
