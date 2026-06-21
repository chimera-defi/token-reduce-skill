"""Track C — shared detection patterns for enforce + measure.

Both ``enforce-token-reduce-first.py`` (advisory warn → block per B3) and
``measure_token_reduction.py`` (broad-scan counting) import from here so the
two stay in sync. The previous bug was that one side would gain a pattern
and the other wouldn't, so a violation either escaped enforcement or
escaped measurement.
"""
from __future__ import annotations

import re
import shlex


# C1 — unscoped rg ----------------------------------------------------------- #


def is_unscoped_rg(command: str) -> bool:
    """``rg <pattern>`` with no -g/--glob and no path argument.

    A bare ``rg foo`` walks every file under cwd. Detection is conservative:
    we only flag commands that start with ``rg`` and have neither a glob
    flag nor a positional path beyond the pattern.
    """
    if not command:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or tokens[0] != "rg":
        return False
    # --files is its own category; not "unscoped rg pattern"
    if any(t in {"--files", "--files-with-matches", "--files-without-match"} for t in tokens):
        return False
    # Has glob? then it's scoped
    if any(t in {"-g", "--glob"} or t.startswith("--glob=") or t.startswith("-g=") for t in tokens):
        return False
    # Walk tokens: skip option flags + their values, then expect <pattern> [<path>...]
    positional: list[str] = []
    i = 1
    SKIP_NEXT = {"-e", "--regexp", "-f", "--file", "-t", "--type", "-T", "--type-not", "-m", "-A", "-B", "-C"}
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            positional.extend(tokens[i + 1:])
            break
        if t.startswith("-"):
            if t in SKIP_NEXT:
                i += 2
                continue
            i += 1
            continue
        positional.append(t)
        i += 1
    if len(positional) <= 1:
        # only a pattern, no path → unscoped
        return True
    return False


# C2 — whole-dir cat / head / tail / wc -------------------------------------- #


_WHOLE_DIR_RE = re.compile(
    r"\b(?:cat|head|tail|wc)\b[^|;&]*?\s+([^\s|;&]+/\*[^\s|;&]*)"
)


def is_whole_dir_cat(command: str) -> bool:
    """``cat dir/*``, ``head dir/*.py``, ``tail logs/*``, ``wc -l dir/*``."""
    if not command:
        return False
    return bool(_WHOLE_DIR_RE.search(command))


# C3 — python -c with glob.glob / os.walk ------------------------------------ #


_PYTHON_C_RE = re.compile(r"\bpython3?\b[^|;&]*?\s+-c\s+")
_GLOB_WALK_RE = re.compile(r"\b(?:glob\.glob|os\.walk)\b")


def is_glob_walk_python(command: str) -> bool:
    if not command:
        return False
    return bool(_PYTHON_C_RE.search(command) and _GLOB_WALK_RE.search(command))


# C4 — xargs cat chains ------------------------------------------------------ #


_XARGS_CAT_RE = re.compile(r"\|\s*xargs\s+(?:-[a-zA-Z0-9]+\s+)*cat\b")


def is_xargs_cat_chain(command: str) -> bool:
    if not command:
        return False
    return bool(_XARGS_CAT_RE.search(command))


# Combined entry point ------------------------------------------------------- #


def matches_any_broad_pattern(command: str) -> bool:
    return (
        is_unscoped_rg(command)
        or is_whole_dir_cat(command)
        or is_glob_walk_python(command)
        or is_xargs_cat_chain(command)
    )
