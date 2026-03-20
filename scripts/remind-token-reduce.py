#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge repo exploration onto the token-reduce path."""
import json
import re
import sys


# Require compound patterns that signal actual repo-discovery intent.
# Single common words like "find", "where", "context", "review" fire on almost
# every coding prompt and add ~85 tokens of system message with no benefit.
TRIGGERS = (
    r"\bexplor(e|ing|ation)\b.{0,60}\b(repo|codebase|files?|code)\b",
    r"\b(find|locate|where)\b.{0,60}\b(file|class|function|hook|script|lives?|defined|lives?)\b",
    r"\b(read|load|gather)\b.{0,60}\bcontext\b",
    r"\bsearch\b.{0,60}\b(repo|codebase|files?)\b",
    r"\breview\b.{0,60}\b(repo|codebase|entire|whole)\b",
    r"\bwhere\s+(is|are|does|do)\b",
    r"\bwhere.{0,20}\blive[s]?\b",
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = data.get("user_prompt", "") or ""
    if not any(re.search(pattern, prompt, re.IGNORECASE) for pattern in TRIGGERS):
        return 0

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
