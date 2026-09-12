"""Track B helpers — auto-rewrite suggestions, catastrophic detection,
pre-flight token estimates, and one-line block-message formatting.

These functions are intentionally pure (no I/O, no telemetry) so they can be
unit-tested directly. The enforce hook composes them into the actual block
decision.
"""
from __future__ import annotations

import functools
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
    # F7: rg's defaults skip hidden files and respect .gitignore, so a naive
    # `rg -g '<pat>' --files <root>` silently drops results `find` would
    # have returned (verified live: 0 vs 1454 hits under a dot-directory).
    # Over-inclusion (--hidden --no-ignore) is the safe default for a
    # find-replacement suggestion -- a caller who copies this as-is must
    # not get a silently incomplete answer.
    return f"rg --files --hidden --no-ignore -g '{pattern}' {root}".rstrip()


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
    # ls -R / or ls -lR / etc.
    re.compile(r"\bls\s+-[a-zA-Z]*R[a-zA-Z]*\s+/"),
    # rg --files . / rg --files ./ at repo root
    re.compile(r"\brg\s+--files\s+(?:\.|\.\/)\s*$"),
)

# R1: `find` accepts GNU/POSIX global options BEFORE its root path/operand
# (-H, -L, -P with no arg; -O<level> attached; -D <debugopts> with a
# separate arg). Every find-root regex in this module (and the symlink
# guard in enforce-token-reduce-first.py, which imports FIND_ROOT_ARG_RE)
# must tolerate them, or `find -L / -name '*.py'` slips every classifier by
# not looking like `find\s+(\.|/)` at all -- confirmed live.
_FIND_GLOBAL_OPTS = r"(?:-[HLP]\b\s+|-O\S+\s+|-D\s+\S+\s+)*"
_FIND_ROOT_RE = re.compile(rf"\bfind\s+{_FIND_GLOBAL_OPTS}(/\S*)")


def _find_targets_broad_root(command: str) -> bool:
    """True when `find` is rooted at the filesystem root or a near-top-level
    directory (<=2 path segments -- e.g. /, /usr, /home, /home/<user>).

    A single invocation at that depth can return an enormous listing
    regardless of any -maxdepth, because the fan-out at that level (every
    top-level system dir, or every repo/workspace under a home directory) is
    itself huge. Deeper, specifically-named roots (e.g. one project or skill
    directory several levels down) are not catastrophic here -- they still
    hit the broad-scan warn-once/block-on-repeat path via
    BROAD_BASH_PATTERNS, they just aren't hard-blocked on the first attempt.
    """
    m = _FIND_ROOT_RE.search(command)
    if not m:
        return False
    segments = [seg for seg in m.group(1).split("/") if seg]
    return len(segments) <= 2


def is_catastrophic(command: str) -> bool:
    """True for the must-always-block patterns from the brief.

    These are wall-of-output scans (root filesystem, full repo listings) where
    even a single attempt blows the context budget.
    """
    if not command:
        return False
    if _find_targets_broad_root(command):
        return True
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


# --------------------------------------------------------------------------- #
# Cost-aware `find` classification (F4)
# --------------------------------------------------------------------------- #


# R1: the single shared "find's root argument, past any global options"
# regex -- was duplicated byte-for-byte as `_FIND_PATH_ARG_RE` in
# enforce-token-reduce-first.py's find_symlink_guard; that module now
# imports this one instead of keeping its own copy. Public (no leading
# underscore) because it's used cross-module.
FIND_ROOT_ARG_RE = re.compile(rf"\bfind\s+{_FIND_GLOBAL_OPTS}(\S+)")
_FIND_DOT_SLASH_ROOT_RE = re.compile(rf"\bfind\s+{_FIND_GLOBAL_OPTS}(?:\.|/)")
_FIND_MAXDEPTH_RE = re.compile(r"-maxdepth\s+(\d+)")


def is_broad_find(command: str) -> bool:
    """True when a ``find <root>`` invocation is broad enough to warrant the
    helper-first gate.

    A find with an explicit ``-maxdepth N`` (N<=2) rooted at a specific,
    non-root, non-repo-root directory is cost-bounded (see
    ``_find_targets_broad_root``) even though it starts with the same
    ``find .``/``find /`` shape the plain broad-bash pattern matches -- e.g.
    ``find /home/agents/.claude/projects -maxdepth 1 -type d``. Everything
    else that starts a find at ``.`` or ``/`` is still broad.
    """
    if not _FIND_DOT_SLASH_ROOT_RE.search(command):
        return False
    if _find_targets_broad_root(command):
        return True
    root_match = FIND_ROOT_ARG_RE.search(command)
    root = root_match.group(1) if root_match else None
    if root in (None, "/", ".", "./"):
        return True
    depth_match = _FIND_MAXDEPTH_RE.search(command)
    if depth_match and int(depth_match.group(1)) <= 2:
        return False
    return True


# --------------------------------------------------------------------------- #
# Quote-aware command scan surfaces (F3)
# --------------------------------------------------------------------------- #


_QUOTED_SPAN_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
# Command-executors whose quoted argument is itself run as a real command --
# a broad/coverage pattern hidden inside must still count. Anything else
# (echo/printf payloads, JSON blobs, commit messages) is inert data and must
# NOT be scanned, or a quoted string that merely contains "find /..." as
# literal text gets misread as a real scan (the live over-block repro: a
# JSON payload piped through a tool got counted as a broad scan).
#
# Known limitation: this is a regex heuristic, not a shell tokenizer, so it
# does not understand backslash-escaped quotes inside a quoted span (e.g.
# `echo "{\"k\":\"find /x\"}"`); the brief's own repro uses single-quoted
# JSON with double-quoted internals, which this handles correctly.
_EXECUTOR_QUOTE_LEADER_RE = re.compile(
    r"\b(?:"
    r"(?:bash|sh|zsh)\s+-c"
    r"|python(?:\d+(?:\.\d+)?)?\s+-c"
    r"|eval"
    r"|xargs\b[^|;&]*"
    r"|tmux\s+(?:new-session|send-keys|run-shell)\b[^|;&]*"
    r"|(?:timeout|env|nohup|watch|ssh)\b[^|;&]*"
    r")\s*$"
)


@functools.lru_cache(maxsize=128)
def command_scan_surfaces(line: str) -> list[str]:
    """Return the text(s) to regex-scan for broad/coverage patterns.

    By default this is ``line`` with every quoted argument span replaced by
    a placeholder, so a broad-looking token inside inert quoted data (echo
    payloads, JSON, commit messages) is not mistaken for a real scan. When a
    quoted span is the command argument of a known command-executor (shell
    ``-c``, ``python -c``, ``eval``, ``xargs``, ``tmux new-session``/
    ``send-keys``/``run-shell``, or a ``timeout``/``env``/``nohup``/
    ``watch``/``ssh`` prefix), that quoted body really does run -- so TWO
    extra surfaces are appended, recursing the broad check into it, instead
    of the body being dropped:

    1. leader + (quote-stripped) body combined into one string. Some
       patterns (e.g. ``is_glob_walk_python``) require both the launcher
       words and the body content in the SAME string to match.
    2. the body ALONE, with no leader prefix. Command-position-sensitive
       checks (``is_exploratory_rg``'s "must start with rg ", or
       ``matches_broad_bash``'s fd/tree command-position check) need to see
       the body as its own command line -- e.g. recursing
       ``tmux new-session -d 'rg -n bar .'`` must expose "rg -n bar ." as a
       surface that itself starts with "rg ", not only "tmux new-session -d
       rg -n bar ." where "rg" is buried mid-string and a naive "is rg
       anywhere" catch-all would be needed (and would then also
       false-positive on unrelated text like `which rg fd rtk`).
    """
    if not line or ("'" not in line and '"' not in line):
        return [line]
    executed_surfaces: list[str] = []
    for match in _QUOTED_SPAN_RE.finditer(line):
        prefix = line[: match.start()]
        leader_match = _EXECUTOR_QUOTE_LEADER_RE.search(prefix)
        if leader_match:
            body = match.group(0)[1:-1]
            executed_surfaces.append(prefix[leader_match.start() :] + body)
            executed_surfaces.append(body)
    stripped = _QUOTED_SPAN_RE.sub(" ", line)
    return [stripped, *executed_surfaces]
