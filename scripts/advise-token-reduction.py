#!/usr/bin/env python3
"""PreToolUse hook: block broad exploratory Bash scans and redirect to token-reduce workflow."""
import json
import re
import sys

BROAD_PATTERNS = [
    r"\bfind\s+(\.|/)",
    r"\bls\s+-R\b",
    r"\bgrep\s+-R\b",
    r"\bgrep\s+--recursive\b",
    r"\bdu\s+-a\b",
    r"\brg\b.*\s--files(?:\s+\.|\s*$)",
    r"\btree\b(?:\s+\.|\s*$)",
]

SAFE_HINTS = (
    "Use a path-only kickoff first.",
    "Shortcut: ./scripts/token-reduce-paths.sh topic words",
    "If you need one excerpt after the file list: ./scripts/token-reduce-snippet.sh topic words",
    "Examples: qmd search \"topic\" -n 5 --files",
    "          rg -n -g '*.ts' 'keyword'",
    "If the search space stays broad after two passes, stop and ask the user to narrow it.",
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = data.get("tool_name")
    if tool_name != "Bash":
        return 0

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "") or ""

    if any(re.search(pattern, command) for pattern in BROAD_PATTERNS):
        json.dump(
            {
                "decision": "block",
                "reason": " ".join(("Blocked broad exploratory Bash scan.",) + SAFE_HINTS),
            },
            sys.stdout,
        )
        print()
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
