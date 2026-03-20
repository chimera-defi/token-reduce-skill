#!/usr/bin/env python3
"""PreToolUse hook: block broad exploratory Glob patterns."""
import json
import sys


def is_broad(pattern: str) -> bool:
    """Return True for patterns that scan the full repo without a directory prefix."""
    if not pattern:
        return False
    # Strip leading ./ for comparison
    p = pattern.lstrip("./")
    # Unscoped wildcards at the root: **/* **/*.ts **/foo etc.
    if p.startswith("**/"):
        return True
    # Bare multi-wildcard with no directory scope: *.* **/* etc.
    if p.count("*") >= 2 and "/" not in p:
        return True
    # path/** grabs every file under a directory — treat as broad.
    if p.endswith("/**") or p.endswith("/**/*"):
        return True
    # Scoped patterns like src/**/*.ts are fine; only block when the directory
    # segment itself is a wildcard (e.g. **/**/* or */**).
    parts = p.split("/")
    if len(parts) > 1 and all(seg.startswith("*") for seg in parts[:2]):
        return True
    return False


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name") != "Glob":
        return 0

    pattern = (data.get("tool_input", {}) or {}).get("pattern", "")
    if is_broad(pattern):
        json.dump(
            {
                "decision": "block",
                "reason": (
                    "Blocked broad exploratory Glob pattern. "
                    "Use ./scripts/token-reduce-paths.sh for a path-only kickoff, "
                    "./scripts/token-reduce-snippet.sh for one ranked excerpt, "
                    "or scoped rg -g first."
                ),
            },
            sys.stdout,
        )
        print()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
