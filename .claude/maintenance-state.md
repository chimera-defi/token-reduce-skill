# Maintenance State
last_run: 2026-06-12
focus: dead-code
status: completed
completed: [dead code scan — no actionable removals found]
in_progress:
pending: [validate_skill_package, checkpoint_gate, rolling_baseline_report — zero coverage, lower priority]
known_failures:
  - qmd:// URL extraction: split("/", 3)[3] includes the index segment — e.g. "qmd://repo/index/src/file.ts" → "index/src/file.ts" not "src/file.ts"
  - token-reduce-skill main entrypoint: token_reduce.py --help returns empty flags — no argparse CLI; telemetry check N/A
skip_next_run: [token_reduce_config, extract_paths_meta tests already added]

## Dead Code Scan Notes (2026-06-12)
- rg TODO/FIXME/HACK: no results
- rg dead print(): no results
- vulture --min-confidence 80: no results
- No stale TODOs, orphaned files, or unused exports found
