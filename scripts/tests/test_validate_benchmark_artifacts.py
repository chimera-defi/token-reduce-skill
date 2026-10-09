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

import pytest

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

    def test_iso_with_z_suffix(self):
        ts = parse_timestamp("2026-06-01T00:00:00Z")
        assert ts is not None
        assert ts.tzinfo is not None


    def test_invalid_string_returns_none(self):
        assert parse_timestamp("not-a-date") is None






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



    @pytest.mark.parametrize(
        ("content", "expected"),
        [({"other": "data"}, "missing generated_at"), ({"generated_at": "bad-date"}, "invalid generated_at")],
    )
    def test_malformed_generated_at_returns_error(self, tmp_path: Path, content: dict, expected: str):
        path = tmp_path / "benchmark.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        assert any(expected in e for e in validate_artifact_freshness(path, 14))

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






    def test_wrong_token_count_triggers_error(self, tmp_path: Path):
        artifact = tmp_path / "local-benchmark.json"
        _write_artifact_with_benchmarks(artifact, [{"name": "script-x", "tokens": 100}])
        readme = "| `script-x` | `999` | desc |\n"
        errors = validate_readme_token_rows(readme, artifact)
        assert len(errors) == 1
        assert "script-x" in errors[0]

