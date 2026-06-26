# Maintenance State
last_run: 2026-06-08
focus: deps
status: completed
completed: [no npm/Python deps to bump (no package.json deps, no requirements.txt); skills telemetry: 35 tests passing baseline]
in_progress:
pending: [validate_skill_package, checkpoint_gate, rolling_baseline_report — zero coverage, lower priority]
known_failures:
  - qmd:// URL extraction: split("/", 3)[3] includes the index segment — e.g. "qmd://repo/index/src/file.ts" → "index/src/file.ts" not "src/file.ts"
skip_next_run: [token_reduce_config, extract_paths_meta tests already added]
attempt_counts:
