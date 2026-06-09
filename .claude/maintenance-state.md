# Maintenance State
last_run: 2026-06-09
focus: ts-cleanup (python ruff pass)
status: completed
completed: [ruff F401/F841 pass — removed last_block_info import, json import, renamed window_14d→_window_14d]
in_progress:
pending: [validate_skill_package, checkpoint_gate, rolling_baseline_report — zero coverage, lower priority]
known_failures:
  - qmd:// URL extraction: split("/", 3)[3] includes the index segment
skip_next_run: []
attempt_counts:
