from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adoption_report import build_report, classify_repo, render_markdown


def _repo(
    name: str,
    *,
    sessions: int = 0,
    helper_sessions: int = 0,
    telemetry_helper_calls: int = 0,
    installed: bool = True,
    docs: bool = True,
    root: str = "/skill",
    version_match: bool = True,
    commit_match: bool = True,
) -> dict:
    return {
        "repo": name,
        "local_skill_installed": installed,
        "skill_source_path": root,
        "skill_version_match": version_match,
        "skill_commit_match": commit_match,
        "token_reduce_docs": docs,
        "session_count": sessions,
        "helper_sessions": helper_sessions,
        "telemetry_helper_calls": telemetry_helper_calls,
    }


def _audit() -> dict:
    repos = [
        _repo("active-good", sessions=3, helper_sessions=2),
        _repo("active-miss", sessions=5),
        _repo("telemetry-only", sessions=2, telemetry_helper_calls=4),
        _repo("inactive"),
    ]
    return {
        "workspace_root": "/workspace",
        "lookback_days": 7,
        "expected_skill": {"root": "/skill", "version": "0.2.7", "commit": "abc123"},
        "summary": {
            "repo_count": 4,
            "local_skill_installed": 4,
            "token_reduce_docs": 4,
            "install_and_docs_compliant": 4,
            "repos_with_recent_sessions": 3,
            "active_repos_with_helper_usage": 2,
            "repos_with_helper_usage": 2,
            "total_recent_sessions": 10,
        },
        "gaps": {"active_without_helper_usage": ["active-miss"]},
        "repos": repos,
    }


def test_classify_active_repo_without_helper_usage() -> None:
    cause, action = classify_repo(_repo("portfolio", sessions=4), {"root": "/skill"})
    assert cause == "active_no_helper"
    assert "portfolio" in action


def test_classify_telemetry_only_usage() -> None:
    cause, action = classify_repo(
        _repo("repo", sessions=2, telemetry_helper_calls=3),
        {"root": "/skill"},
    )
    assert cause == "telemetry_only"
    assert "session parser" in action


def test_build_report_flags_active_helper_slo_failure() -> None:
    report = build_report(_audit(), active_helper_slo_pct=90.0, helper_usage_slo_pct=25.0)
    assert report["slo"]["active_helper_usage_actual_pct"] == 66.7
    assert report["slo"]["active_helper_usage_pass"] is False
    assert report["slo"]["workspace_helper_usage_actual_pct"] == 50.0
    assert report["slo"]["workspace_helper_usage_pass"] is True
    assert report["cause_counts"]["active_no_helper"] == 1


def test_build_report_prioritizes_active_no_helper_intervention() -> None:
    report = build_report(_audit())
    interventions = report["interventions"]
    assert interventions[0]["repo"] == "active-miss"
    assert interventions[0]["cause"] == "active_no_helper"


def test_render_markdown_includes_slo_and_intervention_table() -> None:
    markdown = render_markdown(build_report(_audit()))
    assert "# Token-Reduce Adoption Improvement Report" in markdown
    assert "Active repo helper usage" in markdown
    assert "`active-miss`" in markdown
    assert "| Repo | Cause | Sessions | Helper sessions | Telemetry calls | Action |" in markdown
