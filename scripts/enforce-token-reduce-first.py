#!/usr/bin/env python3
"""PreToolUse hook: require token-reduce helper before exploratory Grep/Glob/Read/Bash."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from token_reduce_state import is_pending, repo_root, session_key


BROAD_BASH_PATTERNS = [
    r"\bfind\s+(\.|/)",
    r"\bls\s+-R\b",
    r"\bgrep\s+-R\b",
    r"\bgrep\s+--recursive\b",
    r"\bdu\s+-a\b",
    r"\brg\b.*\s--files(?:\s+\.|\s*$)",
    r"\btree\b(?:\s+\.|\s*$)",
]
# Commands that are safe orchestrators — they may have broad-looking args in --body/--message,
# but are never themselves filesystem scanners.
_SAFE_TOOL_RE = re.compile(
    r"^\s*(gh|git|npm|bun|node|uv|curl|wget|python3?|ruby|perl|cargo|go\s+run)\b"
)
HELPER_COMMAND_RE = re.compile(r"token-reduce-(?:paths|snippet)\.sh\b")


def block(reason: str) -> int:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    print()
    return 2


def is_broad_glob(pattern: str) -> bool:
    if not pattern:
        return False
    p = pattern.lstrip("./")
    if p.startswith("**/"):
        return True
    if p.count("*") >= 2:
        return True
    if p.endswith("/**") or p.endswith("/**/*"):
        return True
    parts = p.split("/")
    return len(parts) > 1 and all(seg.startswith("*") for seg in parts[:2])


def is_exploratory_glob(pattern: str) -> bool:
    if not pattern:
        return False
    return any(char in pattern for char in "*?[")


def is_exploratory_grep(tool_input: dict[str, object], repo: Path) -> bool:
    path_value = str(tool_input.get("path", "") or "")
    glob_value = str(tool_input.get("glob", "") or "")
    output_mode = str(tool_input.get("output_mode", "") or "")

    # Broad glob filter always exploratory
    if any(char in glob_value for char in "*?["):
        return True

    # No path or root path = exploratory
    if not path_value or path_value in {".", "./"}:
        return True

    candidate = (repo / path_value).resolve()
    if candidate.exists():
        if candidate.is_dir():
            return True
        # It's a specific file — allow files_with_matches on exact files
        return False

    # Unknown path: exploratory if no extension (likely a dir name)
    return "." not in Path(path_value).name


def helper_required_reason() -> str:
    return (
        "token-reduce helper required for this prompt. "
        "Run ./scripts/token-reduce-paths.sh topic words first, or "
        "./scripts/token-reduce-snippet.sh topic words if you explicitly need one excerpt. "
        "After the helper runs, targeted Grep, Glob, and Read follow-ups are allowed."
    )


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {}) or {}
    repo = repo_root()
    pending = is_pending(repo, session_key(data))

    if pending:
        if tool_name == "Bash":
            command = tool_input.get("command", "") or ""
            if HELPER_COMMAND_RE.search(command.split("\n")[0]):
                return 0
            return block(helper_required_reason())
        if tool_name in {"Glob", "Grep", "Read"}:
            return block(helper_required_reason())
        return 0

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        first_line = command.split("\n")[0]
        # Safe orchestrators: may carry broad-looking strings as arguments
        if _SAFE_TOOL_RE.match(first_line):
            return 0
        # Check all lines — broad scans may be on continuation lines
        lines = [l.rstrip("\\").strip() for l in command.split("\n") if l.strip() and l.strip() != "\\"]
        if any(
            re.search(pattern, line)
            for line in lines
            for pattern in BROAD_BASH_PATTERNS
        ):
            return block(
                "Blocked broad exploratory Bash scan. "
                "Use a path-only kickoff first: ./scripts/token-reduce-paths.sh topic words. "
                "If you need one excerpt after the file list: ./scripts/token-reduce-snippet.sh topic words."
            )
        return 0

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "") or ""
        if is_broad_glob(pattern) or is_exploratory_glob(pattern):
            return block(
                "Blocked exploratory Glob pattern. "
                "Use ./scripts/token-reduce-paths.sh for a path-only kickoff, "
                "./scripts/token-reduce-snippet.sh for one ranked excerpt, "
                "then switch to Read on an exact file path."
            )
        return 0

    if tool_name == "Grep" and is_exploratory_grep(tool_input, repo):
        return block(
            "Blocked exploratory Grep before helper kickoff. "
            "Run ./scripts/token-reduce-paths.sh topic words first, then use Grep on an exact file path or a much narrower scope."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
