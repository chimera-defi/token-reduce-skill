"""Track C — coverage tests.

Patterns must be detected by BOTH ``enforce-token-reduce-first.py`` and
``measure_token_reduction.py`` (single shared module: ``coverage_patterns``).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from coverage_patterns import (  # noqa: E402
    is_unscoped_rg,
    is_whole_dir_cat,
    matches_any_broad_pattern,
)


# --------------------------------------------------------------------------- #
# C1 — unscoped rg (no -g, no path)
# --------------------------------------------------------------------------- #


def test_unscoped_rg_pattern_only_detected() -> None:
    assert is_unscoped_rg("rg measure_token_reduction") is True




def test_unscoped_rg_with_path_arg_not_flagged() -> None:
    assert is_unscoped_rg("rg measure scripts/") is False




# --------------------------------------------------------------------------- #
# C2 — whole-dir cat/head/tail/wc
# --------------------------------------------------------------------------- #


def test_whole_dir_cat_star_detected() -> None:
    assert is_whole_dir_cat("cat scripts/*") is True
    assert is_whole_dir_cat("head scripts/*.py") is True
    assert is_whole_dir_cat("tail logs/*") is True
    assert is_whole_dir_cat("wc -l scripts/*") is True




# --------------------------------------------------------------------------- #
# C3 — python -c with glob.glob / os.walk
# --------------------------------------------------------------------------- #








# --------------------------------------------------------------------------- #
# C4 — xargs cat chains
# --------------------------------------------------------------------------- #






# --------------------------------------------------------------------------- #
# Single matches_any_broad_pattern entry point
# --------------------------------------------------------------------------- #




def test_matches_any_broad_pattern_safe_commands() -> None:
    safe = [
        "echo hi",
        "git status",
        "rg -g '*.py' measure",
        "cat scripts/foo.py",
    ]
    for cmd in safe:
        assert not matches_any_broad_pattern(cmd), cmd


# --------------------------------------------------------------------------- #
# Sync check: measure_token_reduction.apply_command_metrics flags the new
# patterns as broad_scan_violation (so review surfaces them).
# --------------------------------------------------------------------------- #


def test_measure_flags_unscoped_rg_as_violation() -> None:
    from measure_token_reduction import apply_command_metrics, fresh_metrics

    metrics = fresh_metrics("claude")
    apply_command_metrics(metrics, "rg measure_token_reduction")
    assert metrics["broad_scan_violation"] is True






