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
    is_glob_walk_python,
    is_unscoped_rg,
    is_whole_dir_cat,
    is_xargs_cat_chain,
    matches_any_broad_pattern,
)


# --------------------------------------------------------------------------- #
# C1 — unscoped rg (no -g, no path)
# --------------------------------------------------------------------------- #


def test_unscoped_rg_pattern_only_detected() -> None:
    assert is_unscoped_rg("rg measure_token_reduction") is True


def test_unscoped_rg_with_glob_not_flagged() -> None:
    assert is_unscoped_rg("rg -g '*.py' measure") is False


def test_unscoped_rg_with_path_arg_not_flagged() -> None:
    assert is_unscoped_rg("rg measure scripts/") is False


def test_unscoped_rg_with_files_flag_not_unscoped() -> None:
    # --files is a separate category (already caught by RG_FILES_BROAD_RE)
    assert is_unscoped_rg("rg --files .") is False


# --------------------------------------------------------------------------- #
# C2 — whole-dir cat/head/tail/wc
# --------------------------------------------------------------------------- #


def test_whole_dir_cat_star_detected() -> None:
    assert is_whole_dir_cat("cat scripts/*") is True
    assert is_whole_dir_cat("head scripts/*.py") is True
    assert is_whole_dir_cat("tail logs/*") is True
    assert is_whole_dir_cat("wc -l scripts/*") is True


def test_whole_dir_cat_single_file_not_flagged() -> None:
    assert is_whole_dir_cat("cat scripts/foo.py") is False
    assert is_whole_dir_cat("head -n 20 scripts/foo.py") is False
    assert is_whole_dir_cat("tail -n 50 logs/today.log") is False


# --------------------------------------------------------------------------- #
# C3 — python -c with glob.glob / os.walk
# --------------------------------------------------------------------------- #


def test_python_glob_glob_detected() -> None:
    assert is_glob_walk_python(
        "python -c 'import glob; print(glob.glob(\"**/*.py\"))'"
    ) is True


def test_python_os_walk_detected() -> None:
    assert is_glob_walk_python(
        'python3 -c "import os; [print(p) for p,_,_ in os.walk(\\".\\")]"'
    ) is True


def test_python_unrelated_not_flagged() -> None:
    assert is_glob_walk_python("python -c 'print(1+1)'") is False
    assert is_glob_walk_python("python scripts/foo.py") is False


# --------------------------------------------------------------------------- #
# C4 — xargs cat chains
# --------------------------------------------------------------------------- #


def test_xargs_cat_chain_detected() -> None:
    assert is_xargs_cat_chain("find . -name '*.py' | xargs cat") is True
    assert is_xargs_cat_chain("ls | xargs cat") is True


def test_xargs_other_not_flagged() -> None:
    assert is_xargs_cat_chain("find . -name '*.py' | xargs wc -l") is False
    assert is_xargs_cat_chain("git status | xargs echo") is False


# --------------------------------------------------------------------------- #
# Single matches_any_broad_pattern entry point
# --------------------------------------------------------------------------- #


def test_matches_any_broad_pattern_covers_all() -> None:
    cases = [
        "rg measure_token_reduction",
        "cat scripts/*",
        "python -c 'import glob; print(glob.glob(\"**/*.py\"))'",
        "find . -name '*.py' | xargs cat",
    ]
    for cmd in cases:
        assert matches_any_broad_pattern(cmd), cmd


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


def test_measure_flags_whole_dir_cat_as_violation() -> None:
    from measure_token_reduction import apply_command_metrics, fresh_metrics

    metrics = fresh_metrics("claude")
    apply_command_metrics(metrics, "cat scripts/*")
    assert metrics["broad_scan_violation"] is True


def test_measure_flags_python_glob_as_violation() -> None:
    from measure_token_reduction import apply_command_metrics, fresh_metrics

    metrics = fresh_metrics("claude")
    apply_command_metrics(
        metrics,
        "python -c 'import glob; print(glob.glob(\"**/*.py\"))'",
    )
    assert metrics["broad_scan_violation"] is True


def test_measure_flags_xargs_cat_as_violation() -> None:
    from measure_token_reduction import apply_command_metrics, fresh_metrics

    metrics = fresh_metrics("claude")
    apply_command_metrics(metrics, "find . -name '*.py' | xargs cat")
    assert metrics["broad_scan_violation"] is True
