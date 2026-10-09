"""Tests for previously zero-coverage modules: validate_skill_package and rolling_baseline_report."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_skill_package import validate
from rolling_baseline_report import (
    MetricSpec,
    build_report,
    render_markdown,
)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------



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
        "[`headroom`](https://github.com/chopratejas/headroom), "
        "[Cost Caliper](https://github.com/Cost-Caliper/caliper), "
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





    def test_delta_is_post_minus_pre(self, tmp_path):
        rows = _make_timestamped_rows(4)
        source = tmp_path / "data.jsonl"
        report = build_report(rows, 2, source)
        for m in report["metrics"]:
            expected = round(m["post_avg"] - m["pre_avg"], 2)
            assert m["delta"] == expected




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





    def test_contains_pre_and_post_avgs(self):
        result = render_markdown(_minimal_report())
        assert "42.0" in result
        assert "55.0" in result




