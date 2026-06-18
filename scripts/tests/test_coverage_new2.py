"""Tests for previously zero-coverage modules: validate_skill_package and rolling_baseline_report."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_skill_package import parse_frontmatter, validate, REQUIRED_FRONTMATTER, REQUIRED_METADATA_FIELDS, REQUIRED_SECTIONS
from rolling_baseline_report import (
    MetricSpec,
    window_split,
    metric_stats,
    build_report,
    render_markdown,
)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_valid_frontmatter_returns_body(self):
        text = "---\nname: my-skill\nlicense: MIT\n---\n# Rest"
        result = parse_frontmatter(text)
        assert "name: my-skill" in result
        assert "license: MIT" in result

    def test_missing_frontmatter_raises_value_error(self):
        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_frontmatter("# No frontmatter here\n")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_frontmatter("")

    def test_only_opening_dashes_raises(self):
        with pytest.raises(ValueError):
            parse_frontmatter("---\nname: foo\n")

    def test_multiline_frontmatter_captured(self):
        text = "---\nname: skill\nlicense: MIT\ndescription: A description\nmetadata:\n  author: someone\n  category: tools\n---\nbody"
        result = parse_frontmatter(text)
        assert "author: someone" in result
        assert "category: tools" in result

    def test_frontmatter_body_excludes_delimiters(self):
        text = "---\nkey: val\n---\ncontent"
        result = parse_frontmatter(text)
        assert "---" not in result

    def test_empty_frontmatter_block(self):
        text = "---\n\n---\ncontent"
        # The regex requires at least a newline between delimiters — empty block still has the surrounding newlines
        result = parse_frontmatter(text)
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def _make_valid_skill_md() -> str:
    """Return a minimal SKILL.md that passes all checks."""
    return (
        "---\n"
        "name: my-skill\n"
        "license: MIT\n"
        "description: A test skill\n"
        "metadata:\n"
        "  author: tester\n"
        "  category: testing\n"
        "---\n"
        "# Token Reduction Skill\n\n"
        "## Description\n\nDoes things.\n\n"
        "## Triggers\n\nWhen X.\n"
    )


def _make_valid_readme() -> str:
    return (
        "# My Skill\n\n"
        "Uses [QMD](https://github.com/tobi/qmd), "
        "[RTK](https://github.com/rtk-ai/rtk), "
        "[`caveman`](https://github.com/JuliusBrussee/caveman), "
        "and [AXI](https://github.com/kunchenguid/axi).\n"
    )


class TestValidate:
    def test_fully_valid_package_returns_no_errors(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(_make_valid_skill_md(), encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.write_text("name: my-skill\n", encoding="utf-8")
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert errors == []

    def test_missing_frontmatter_returns_error(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# No frontmatter\n", encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("missing YAML frontmatter" in e for e in errors)

    def test_missing_required_frontmatter_field(self, tmp_path):
        # Omit 'license' from frontmatter
        text = (
            "---\n"
            "name: my-skill\n"
            "description: A test skill\n"
            "metadata:\n"
            "  author: tester\n"
            "  category: testing\n"
            "---\n"
            "# Token Reduction Skill\n\n"
            "## Description\n\n## Triggers\n"
        )
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("license" in e for e in errors)

    def test_missing_metadata_author_field(self, tmp_path):
        text = (
            "---\n"
            "name: my-skill\n"
            "license: MIT\n"
            "description: A test skill\n"
            "metadata:\n"
            "  category: testing\n"
            "---\n"
            "# Token Reduction Skill\n\n"
            "## Description\n\n## Triggers\n"
        )
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("metadata.author" in e for e in errors)

    def test_missing_required_section(self, tmp_path):
        # Omit "## Triggers" section
        text = (
            "---\n"
            "name: my-skill\n"
            "license: MIT\n"
            "description: A test skill\n"
            "metadata:\n"
            "  author: tester\n"
            "  category: testing\n"
            "---\n"
            "# Token Reduction Skill\n\n"
            "## Description\n\nDoes things.\n"
        )
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("## Triggers" in e for e in errors)

    def test_deprecated_trigger_section_flagged(self, tmp_path):
        text = (
            "---\n"
            "name: my-skill\n"
            "license: MIT\n"
            "description: A test skill\n"
            "metadata:\n"
            "  author: tester\n"
            "  category: testing\n"
            "---\n"
            "# Token Reduction Skill\n\n"
            "## Description\n\nDoes things.\n\n"
            "## Trigger\n\nOld style.\n\n"
            "## Triggers\n\nNew style too.\n"
        )
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("Triggers" in e and "Trigger" in e for e in errors)

    def test_missing_openai_yaml(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(_make_valid_skill_md(), encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        # deliberately not created
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("openai.yaml" in e for e in errors)

    def test_missing_readme(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(_make_valid_skill_md(), encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        # deliberately not created

        errors = validate(skill_md, openai_yaml, readme)
        assert any("README.md" in e for e in errors)

    def test_readme_missing_attribution_link(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(_make_valid_skill_md(), encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        openai_yaml.touch()
        readme = tmp_path / "README.md"
        # README missing all attribution links
        readme.write_text("# My Skill\n\nNo links here.\n", encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        assert any("QMD" in e for e in errors)
        assert any("RTK" in e for e in errors)

    def test_multiple_errors_accumulated(self, tmp_path):
        # Missing two frontmatter fields and missing openai.yaml
        text = (
            "---\n"
            "name: my-skill\n"
            "metadata:\n"
            "  author: tester\n"
            "  category: testing\n"
            "---\n"
            "# Token Reduction Skill\n\n"
            "## Description\n\n## Triggers\n"
        )
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        openai_yaml = tmp_path / "openai.yaml"
        # not created
        readme = tmp_path / "README.md"
        readme.write_text(_make_valid_readme(), encoding="utf-8")

        errors = validate(skill_md, openai_yaml, readme)
        # Missing 'license', 'description' frontmatter fields, and openai.yaml
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# window_split
# ---------------------------------------------------------------------------

def _make_rows(n: int) -> list[dict]:
    """Create n dummy rows (content doesn't matter for split logic)."""
    return [{"i": i} for i in range(n)]


class TestWindowSplit:
    def test_fewer_than_two_rows_returns_empty_pair(self):
        assert window_split([], 5) == ([], [])
        assert window_split([{"i": 0}], 5) == ([], [])

    def test_large_enough_for_full_windows(self):
        rows = _make_rows(12)
        pre, post = window_split(rows, 5)
        # 12 >= 10 so uses last 10: rows[2:], then split in half
        assert len(pre) == 5
        assert len(post) == 5

    def test_smaller_than_double_window_halved(self):
        rows = _make_rows(6)
        pre, post = window_split(rows, 5)
        # 6 < 10, half = 3
        assert len(pre) == 3
        assert len(post) == 3

    def test_exact_double_window_size(self):
        rows = _make_rows(10)
        pre, post = window_split(rows, 5)
        assert len(pre) == 5
        assert len(post) == 5

    def test_two_rows_halved(self):
        rows = _make_rows(2)
        pre, post = window_split(rows, 5)
        assert len(pre) == 1
        assert len(post) == 1

    def test_odd_count_halved_correctly(self):
        rows = _make_rows(7)
        pre, post = window_split(rows, 5)
        # 7 < 10, half = 3; rows[3:] has 4 items but post = rows[half:] = rows[3:] = 4
        assert len(pre) == 3
        assert len(post) == 4

    def test_recent_window_is_tail_of_rows(self):
        rows = [{"i": i} for i in range(20)]
        pre, post = window_split(rows, 5)
        # recent = rows[10:], pre = rows[10:15], post = rows[15:20]
        assert pre[0]["i"] == 10
        assert post[-1]["i"] == 19


# ---------------------------------------------------------------------------
# metric_stats
# ---------------------------------------------------------------------------

def _row_with_global(value: float) -> dict:
    return {"global_measure_summary": {"helper_sessions_pct": value}}


_SIMPLE_SPEC = MetricSpec(
    key="helper_sessions_pct",
    label="Helper Usage %",
    paths=(("global_measure_summary", "helper_sessions_pct"),),
)


class TestMetricStats:
    def test_average_of_values(self):
        rows = [_row_with_global(10.0), _row_with_global(20.0)]
        avg, count = metric_stats(rows, _SIMPLE_SPEC)
        assert avg == 15.0
        assert count == 2

    def test_missing_key_excluded(self):
        rows = [_row_with_global(10.0), {"unrelated": True}]
        avg, count = metric_stats(rows, _SIMPLE_SPEC)
        assert avg == 10.0
        assert count == 1

    def test_empty_rows_returns_zero_avg_zero_count(self):
        avg, count = metric_stats([], _SIMPLE_SPEC)
        assert avg == 0.0
        assert count == 0

    def test_all_missing_returns_zero(self):
        rows = [{"no": "data"}, {"no": "data"}]
        avg, count = metric_stats(rows, _SIMPLE_SPEC)
        assert avg == 0.0
        assert count == 0

    def test_single_row_avg_equals_value(self):
        rows = [_row_with_global(42.5)]
        avg, count = metric_stats(rows, _SIMPLE_SPEC)
        assert avg == 42.5
        assert count == 1

    def test_fallback_path_used(self):
        spec = MetricSpec(
            key="test",
            label="Test",
            paths=(
                ("missing_path", "key"),
                ("global_measure_summary", "helper_sessions_pct"),
            ),
        )
        rows = [_row_with_global(55.0)]
        avg, count = metric_stats(rows, spec)
        assert avg == 55.0
        assert count == 1


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

def _make_timestamped_rows(n: int) -> list[dict]:
    """Create rows with _parsed_timestamp fields (as build_report expects pre-parsed rows)."""
    rows = []
    for i in range(n):
        ts = datetime(2024, 1, i + 1, tzinfo=timezone.utc)
        rows.append({
            "_parsed_timestamp": ts,
            "global_measure_summary": {"helper_sessions_pct": float(i * 10)},
        })
    return rows


class TestBuildReport:
    def test_report_has_required_keys(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "telemetry.jsonl"
        report = build_report(rows, 5, source)

        assert "generated_at" in report
        assert "source_file" in report
        assert "snapshot_count" in report
        assert "windows" in report
        assert "metrics" in report

    def test_snapshot_count_matches_input(self, tmp_path):
        rows = _make_timestamped_rows(8)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 3, source)
        assert report["snapshot_count"] == 8

    def test_source_file_recorded(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "telemetry.jsonl"
        report = build_report(rows, 2, source)
        assert str(source) in report["source_file"]

    def test_metrics_list_not_empty(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 2, source)
        assert len(report["metrics"]) > 0

    def test_metrics_have_expected_fields(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 2, source)
        for m in report["metrics"]:
            assert "key" in m
            assert "label" in m
            assert "pre_avg" in m
            assert "post_avg" in m
            assert "delta" in m

    def test_delta_is_post_minus_pre(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 2, source)
        for m in report["metrics"]:
            expected = round(m["post_avg"] - m["pre_avg"], 2)
            assert m["delta"] == expected

    def test_windows_pre_and_post_counts(self, tmp_path):
        rows = _make_timestamped_rows(10)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 4, source)
        assert report["windows"]["pre"]["count"] == 4
        assert report["windows"]["post"]["count"] == 4

    def test_empty_rows_produces_null_windows(self, tmp_path):
        source = tmp_path / "data.jsonl"
        report = build_report([], 5, source)
        assert report["snapshot_count"] == 0
        assert report["windows"]["pre"]["start"] is None
        assert report["windows"]["post"]["start"] is None


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

def _minimal_report() -> dict:
    return {
        "generated_at": "2024-01-01T00:00:00+00:00",
        "source_file": "/data/telemetry.jsonl",
        "snapshot_count": 10,
        "windows": {
            "pre": {"count": 5},
            "post": {"count": 5},
        },
        "metrics": [
            {
                "label": "Helper Usage %",
                "pre_avg": 42.0,
                "post_avg": 55.0,
                "delta": 13.0,
            }
        ],
    }


class TestRenderMarkdown:
    def test_returns_string(self):
        report = _minimal_report()
        result = render_markdown(report)
        assert isinstance(result, str)

    def test_contains_report_header(self):
        result = render_markdown(_minimal_report())
        assert "# Rolling Baseline Report" in result

    def test_contains_generated_at(self):
        result = render_markdown(_minimal_report())
        assert "2024-01-01T00:00:00+00:00" in result

    def test_contains_snapshot_count(self):
        result = render_markdown(_minimal_report())
        assert "10" in result

    def test_contains_metric_label(self):
        result = render_markdown(_minimal_report())
        assert "Helper Usage %" in result

    def test_contains_pre_and_post_avgs(self):
        result = render_markdown(_minimal_report())
        assert "42.0" in result
        assert "55.0" in result

    def test_contains_delta(self):
        result = render_markdown(_minimal_report())
        assert "13.0" in result

    def test_contains_markdown_table_header(self):
        result = render_markdown(_minimal_report())
        assert "| Metric |" in result
        assert "| Pre Avg |" in result

    def test_ends_with_newline(self):
        result = render_markdown(_minimal_report())
        assert result.endswith("\n")

    def test_multiple_metrics_all_rendered(self):
        report = _minimal_report()
        report["metrics"] = [
            {"label": "Metric A", "pre_avg": 1.0, "post_avg": 2.0, "delta": 1.0},
            {"label": "Metric B", "pre_avg": 3.0, "post_avg": 4.0, "delta": 1.0},
        ]
        result = render_markdown(report)
        assert "Metric A" in result
        assert "Metric B" in result
