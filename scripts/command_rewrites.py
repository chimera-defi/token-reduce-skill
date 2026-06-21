"""Track B helpers — auto-rewrite suggestions, catastrophic detection,
pre-flight token estimates, and one-line block-message formatting.

These functions are intentionally pure (no I/O, no telemetry) so they can be
unit-tested directly. The enforce hook composes them into the actual block
decision.
"""
from __future__ import annotations

import re
from typing import Optional


# --------------------------------------------------------------------------- #
# Auto-rewrite suggestions (B1)
# --------------------------------------------------------------------------- #


_FIND_NAME_RE = re.compile(
    r"""\bfind\s+
        (?P<root>[^\s]+)\s+
        (?:.*\s)?-(?:i?name)\s+
        (?P<quote>['"]?)
        (?P<pattern>[^'"\s]+)
        (?P=quote)
    """,
    re.VERBOSE,
)


def _find_name_rewrite(command: str) -> Optional[str]:
    m = _FIND_NAME_RE.search(command)
    if not m:
        return None
    root = m.group("root")
    pattern = m.group("pattern")
    if root in {"/", "//"} or root.startswith("/"):
        # find / or absolute root → use helper, not rg
        return None
    return f"rg -g '{pattern}' --files {root}".rstrip()


def suggest_rewrite(command: str) -> Optional[str]:
    """Suggest a cheaper alternative for a broad/exploratory command.

    Returns a short shell snippet ready to copy, or None when no specific
    rewrite is available (caller should fall back to the helper hint).
    """
    if not command:
        return None
    cmd = command.strip()

    # find . -name "*.py" → rg -g '*.py' --files
    rewrite = _find_name_rewrite(cmd)
    if rewrite:
        return rewrite

    # find / or other system-rooted scans → punt to helper
    if re.match(r"\s*find\s+/", cmd):
        return "use token-reduce-paths <topic> or qmd search instead"

    # ls -R or ls -lR → punt to helper
    if re.match(r"\s*ls\s+-[a-zA-Z]*R", cmd):
        return "use token-reduce-paths <topic> instead"

    # grep -R pattern . → rg -e pattern
    m = re.match(r"\s*grep\s+-(?:[a-zA-Z]*R[a-zA-Z]*)\s+(\S+)\s+(\S+)", cmd)
    if m:
        pattern = m.group(1)
        scope = m.group(2)
        return f"rg -e {pattern} -g '*' {scope}"

    # rg --files . or rg --files ./ → helper
    if re.match(r"\s*rg\s+--files\s+(\.|\.\/)\s*$", cmd):
        return "use token-reduce-paths <topic> instead"

    return None


# --------------------------------------------------------------------------- #
# Catastrophic detection (B3 — always block)
# --------------------------------------------------------------------------- #


_CATASTROPHIC_RES: tuple[re.Pattern[str], ...] = (
    # find / or find /usr style
    re.compile(r"\bfind\s+/(?:\s|$|[a-zA-Z])"),
    # ls -R / or ls -lR / etc.
    re.compile(r"\bls\s+-[a-zA-Z]*R[a-zA-Z]*\s+/"),
    # rg --files . / rg --files ./ at repo root
    re.compile(r"\brg\s+--files\s+(?:\.|\.\/)\s*$"),
)


def is_catastrophic(command: str) -> bool:
    """True for the must-always-block patterns from the brief.

    These are wall-of-output scans (root filesystem, full repo listings) where
    even a single attempt blows the context budget.
    """
    if not command:
        return False
    for rx in _CATASTROPHIC_RES:
        if rx.search(command):
            return True
    return False


# --------------------------------------------------------------------------- #
# Pre-flight output estimate (B5)
# --------------------------------------------------------------------------- #


def estimate_output_tokens(command: str) -> Optional[int]:
    """Rough estimate of tokens a command's output will consume.

    Returns None when the command is not a known broad/exploratory pattern.
    The estimate is intentionally conservative; the goal is a "this will cost
    you ~Xk" annotation, not a precise count.
    """
    if not command:
        return None
    cmd = command.strip()

    # find / or rg --files / ls -R / → catastrophic, large estimate
    if is_catastrophic(cmd):
        return 50_000

    # find . -name <pat> → mid-sized
    if _FIND_NAME_RE.search(cmd):
        return 5_000

    # grep -R / rg --files <subdir>
    if re.search(r"\bgrep\s+-[a-zA-Z]*R", cmd):
        return 8_000
    if re.search(r"\brg\s+--files\b", cmd):
        return 4_000
    if re.search(r"\bls\s+-[a-zA-Z]*R", cmd):
        return 3_000
    return None


# --------------------------------------------------------------------------- #
# One-line block message (B2)
# --------------------------------------------------------------------------- #


def format_block_message(
    *,
    reason: str,
    command: str,
    helper_hint: str,
) -> str:
    """Build a tight, single-line block message with an actionable rewrite.

    Format: ``Blocked: <reason>. Try: <rewrite>. Or: <helper>``.
    Truncated to keep block output cheap.
    """
    rewrite = suggest_rewrite(command)
    parts = [f"Blocked: {reason}."]
    if rewrite and "token-reduce" not in rewrite.lower():
        parts.append(f"Try: {rewrite}.")
    parts.append(f"Or: {helper_hint}.")
    msg = " ".join(parts)
    return msg[:240]
