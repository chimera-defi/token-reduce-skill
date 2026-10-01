"""Tests for validate-benchmark-artifacts.py pure helpers.

Covers:
- parse_timestamp: ISO-8601 parsing including Z suffix, invalid inputs
- validate_artifact_freshness: missing file, missing field, stale vs fresh
- validate_readme_token_rows: missing row, present row, non-list benchmarks
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_benchmark_artifacts",
        SCRIPT_DIR / "validate-benchmark-artifacts.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_module()
parse_timestamp = _mod.parse_timestamp
validate_artifact_freshness = _mod.validate_artifact_freshness
validate_readme_token_rows = _mod.validate_readme_token_rows


# ---------------------------------------------------------------------------
# parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_iso_with_offset(self):
        ts = parse_timestamp("2026-01-15T12:00:00+00:00")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 15

    def test_iso_with_z_suffix(self):
        ts = parse_timestamp("2026-06-01T00:00:00Z")
        assert ts is not None
        assert ts.tzinfo is not None

    def test_iso_with_positive_offset(self):
        ts = parse_timestamp("2026-03-10T08:30:00+05:30")
        assert ts is not None

    def test_invalid_string_returns_none(self):
        assert parse_timestamp("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert parse_timestamp("") is None

    def test_partial_date_returns_none(self):
        assert parse_timestamp("2026-01") is None

    def test_returns_aware_datetime(self):
        ts = parse_timestamp("2026-09-17T00:00:00Z")
        assert ts is not None
        assert ts.tzinfo is not None

    def test_z_suffix_treated_as_utc(self):
        ts_z = parse_timestamp("2026-09-17T12:00:00Z")
        ts_utc = parse_timestamp("2026-09-17T12:00:00+00:00")
        assert ts_z is not None and ts_utc is not None
        assert ts_z == ts_utc


# ---------------------------------------------------------------------------
# validate_artifact_freshness
# ---------------------------------------------------------------------------


def _write_artifact(path: Path, generated_at: str) -> None:
    path.write_text(json.dumps({"generated_at": generated_at}), encoding="utf-8")


class TestValidateArtifactFreshness:
    def test_missing_file_returns_error(self, tmp_path: Path):
        missing = tmp_path / "benchmark.json"
        errors = validate_artifact_freshness(missing, 14)
        assert len(errors) == 1
        assert "missing benchmark artifact" in errors[0]

    def test_missing_generated_at_returns_error(self, tmp_path: Path):
        path = tmp_path / "benchmark.json"
        path.write_text(json.dumps({"other": "data"}), encoding="utf-8")
        errors = validate_artifact_freshness(path, 14)
        assert any("missing generated_at" in e for e in errors)

    def test_invalid_timestamp_returns_error(self, tmp_path: Path):
        path = tmp_path / "benchmark.json"
        path.write_text(json.dumps({"generated_at": "bad-date"}), encoding="utf-8")
        errors = validate_artifact_freshness(path, 14)
        assert any("invalid generated_at" in e for e in errors)

    def test_fresh_artifact_returns_no_errors(self, tmp_path: Path):
        path = tmp_path / "benchmark.json"
        fresh_ts = datetime.now(timezone.utc).isoformat()
        _write_artifact(path, fresh_ts)
        errors = validate_artifact_freshness(path, 14)
        assert errors == []

    def test_stale_artifact_returns_error(self, tmp_path: Path):
        path = tmp_path / "benchmark.json"
        stale = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        _write_artifact(path, stale)
        errors = validate_artifact_freshness(path, 14)
        assert len(errors) == 1
        assert "stale benchmark artifact" in errors[0]

    def test_just_under_max_age_is_fresh(self, tmp_path: Path):
        path = tmp_path / "benchmark.json"
        just_under = (datetime.now(timezone.utc) - timedelta(days=13, hours=23)).isoformat()
        _write_artifact(path, just_under)
        errors = validate_artifact_freshness(path, 14)
        assert errors == []

    def test_stale_message_includes_path_and_max_days(self, tmp_path: Path):
        path = tmp_path / "my-benchmark.json"
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        _write_artifact(path, old)
        errors = validate_artifact_freshness(path, 7)
        assert len(errors) == 1
        assert "7 days" in errors[0]
        assert "my-benchmark.json" in errors[0]


# ---------------------------------------------------------------------------
# validate_readme_token_rows
# ---------------------------------------------------------------------------


def _write_artifact_with_benchmarks(path: Path, benchmarks: list) -> None:
    path.write_text(json.dumps({"benchmarks": benchmarks}), encoding="utf-8")


class TestValidateReadmeTokenRows:
    def test_matching_row_present_returns_no_errors(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "my-script", "tokens": 1234}])
        readme = "# Benchmarks\n| `my-script` | `1234` | some description |\n"
        errors = validate_readme_token_rows(readme, artifact)
        assert errors == []

    def test_missing_row_returns_error(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "missing-script", "tokens": 999}])
        readme = "# Benchmarks\n| `other-script` | `100` | desc |\n"
        errors = validate_readme_token_rows(readme, artifact)
        assert len(errors) == 1
        assert "missing-script" in errors[0]
        assert "999" in errors[0]

    def test_multiple_benchmarks_all_must_be_present(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(
            artifact,
            [
                {"name": "script-a", "tokens": 100},
                {"name": "script-b", "tokens": 200},
            ],
        )
        readme = "| `script-a` | `100` |\n"
        errors = validate_readme_token_rows(readme, artifact)
        assert len(errors) == 1
        assert "script-b" in errors[0]

    def test_non_list_benchmarks_returns_error(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        artifact.write_text(json.dumps({"benchmarks": "not-a-list"}), encoding="utf-8")
        errors = validate_readme_token_rows("# readme", artifact)
        assert any("must be a list" in e for e in errors)

    def test_empty_benchmarks_list_returns_no_errors(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [])
        errors = validate_readme_token_rows("# readme with no table", artifact)
        assert errors == []

    def test_benchmark_entry_missing_name_skipped(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"tokens": 500}])
        errors = validate_readme_token_rows("# readme", artifact)
        assert errors == []

    def test_benchmark_entry_missing_tokens_skipped(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "my-script"}])
        errors = validate_readme_token_rows("# readme", artifact)
        assert errors == []

    def test_wrong_token_count_triggers_error(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "script-x", "tokens": 100}])
        readme = "| `script-x` | `999` | desc |\n"
        errors = validate_readme_token_rows(readme, artifact)
        assert len(errors) == 1
        assert "script-x" in errors[0]

    def test_error_includes_artifact_filename(self, tmp_path: Path):
        artifact = tmp_path / "composite-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "foo", "tokens": 42}])
        errors = validate_readme_token_rows("# no table", artifact)
        assert any("composite-benchmark.json" in e for e in errors)
