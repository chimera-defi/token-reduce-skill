#!/usr/bin/env python3
"""UserPromptSubmit hook: require token-reduce for matching repo-discovery prompts."""
import json
import sys

from token_reduce_state import clear_pending, mark_pending, prompt_requires_helper, repo_root, session_key
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

    json.dump(
        {
            "continue": True,
            "systemMessage": (
                "For repo discovery in this workspace, start with the token-reduce workflow. "
                "If the task is about maintaining this skill itself, use the skill instructions and then begin discovery with a single standalone Bash command: "
                "./scripts/token-reduce-paths.sh topic words. "
                "That helper gives a low-token path-only kickoff. "
                "Use the user's literal filenames, identifiers, or key nouns as the query words; "
                "do not replace them with generic synonyms or drop key qualifiers like Bash, Glob, hook, or token reduction. "
                "If you need one ranked excerpt after the file list, use "
                "./scripts/token-reduce-snippet.sh topic words. "
                "For token-reduction hook or script questions, the likely answers are under ./scripts, not .githooks. "
                "Do not start with find, ls, grep, Grep, Read, or broad Glob fallbacks before the helper runs. "
                "After the helper runs, prefer Grep or Read for follow-up narrowing; do not switch back to Bash search commands unless you are calling the helper again."
            ),
        },
        sys.stdout,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
