# Maintenance State
last_run: 2026-06-04
focus: test-coverage
status: completed
completed: [add 22 tests for token_reduce_config.deep_merge/parse_value and extract_paths_meta.extract_paths (13→35 tests), PR #28 open and green]
in_progress:
pending: [validate_skill_package, checkpoint_gate, rolling_baseline_report — zero coverage, lower priority]
known_failures:
  - qmd:// URL extraction: split("/", 3)[3] includes the index segment — e.g. "qmd://repo/index/src/file.ts" → "index/src/file.ts" not "src/file.ts"
skip_next_run: [token_reduce_config, extract_paths_meta tests already added]
