# Maintenance State
last_run: 2026-06-26
focus: dead-code
status: completed
completed:
  - Dead code scan on new round1-3 files (brain_hint.py, command_rewrites.py, cost_ledger.py, coverage_patterns.py, escalation.py, rank_paths.py, review_token_reduction.py, qmd_warm_cache.py, enforce-token-reduce-first.py, measure_token_reduction.py)
  - Main scripts: only `from __future__ import annotations` flagged — this is a valid PEP 563 directive, not dead code
  - Test file unused imports (os, sys, textwrap in test_n3_n4_shell_fixes.py; pytest in test_n5_n7_adaptive_fixes.py and test_track_b_gate_guide.py; json+constants in test_coverage_new2.py): all covered by open PR #43 (chore/maintenance-2026-06-23, not yet merged)
  - rg TODO/FIXME/HACK: no results in scripts/
  - No orphaned files found
in_progress:
pending:
  - Merge PR #43 (unused imports in 4 test files)
known_failures:
  - qmd:// URL extraction: split("/", 3)[3] includes index segment — known issue
attempt_counts: {}
