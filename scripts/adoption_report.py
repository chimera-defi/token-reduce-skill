#!/usr/bin/env python3
"""Build workspace-level token-reduce adoption SLO reports."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from audit_workspace_skills import build_payload


DEFAULT_ACTIVE_HELPER_SLO_PCT = 90.0
DEFAULT_HELPER_USAGE_SLO_PCT = 25.0


def pct(part: int | float, total: int | float) -> float:
    return round((float(part) * 100.0 / float(total)), 1) if total else 0.0


def load_audit(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workspace audit JSON must contain an object")
    return payload


def classify_repo(repo: dict, expected_skill: dict) -> tuple[str, str]:
    """Return likely cause and next action for one repo row."""
    name = str(repo.get("repo", ""))
    if not repo.get("local_skill_installed"):
        return "missing_install", "Run workspace-install or setup, then rerun improve-adoption."
    if not repo.get("token_reduce_docs"):
        return "missing_guidance", "Install or refresh AGENTS.md/CLAUDE.md token-reduce routing guidance."
    if repo.get("skill_source_path") != expected_skill.get("root"):
        return "wrong_skill_root", "Force-relink this repo to the canonical token-reduce skill root."
    if repo.get("local_skill_installed") and not repo.get("skill_version_match"):
        return "version_drift", "Refresh this repo's skill symlink or installed copy to the expected package version."
    if repo.get("local_skill_installed") and not repo.get("skill_commit_match"):
        return "commit_drift", "Refresh this repo's skill symlink or installed copy to the expected commit."
    sessions = int(repo.get("session_count", 0) or 0)
    helper_sessions = int(repo.get("helper_sessions", 0) or 0)
    telemetry_calls = int(repo.get("telemetry_helper_calls", 0) or 0)
    if sessions > 0 and helper_sessions == 0 and telemetry_calls == 0:
        return (
            "active_no_helper",
            (
                f"Open the next {name} task with token-reduce-paths/adaptive first; "
                "inspect session prompts or hooks if adoption stays at zero."
            ),
        )
    if sessions > 0 and helper_sessions == 0 and telemetry_calls > 0:
        return (
            "telemetry_only",
            "Helper telemetry exists but session parser did not see shell usage; inspect host log coverage.",
        )
    if sessions == 0 and telemetry_calls > 0:
        return (
            "telemetry_without_sessions",
            "Recent helper calls exist but no host session log was attributed; inspect workspace/cwd parsing.",
        )
    if sessions == 0:
        return "inactive", "No action until this repo has recent Claude/Codex sessions."
    return "healthy", "Keep monitoring trailing-window helper usage."


def repo_priority(repo: dict, cause: str) -> int:
    if cause in {"missing_install", "wrong_skill_root", "version_drift", "commit_drift"}:
        return 0
    if cause == "active_no_helper":
        return 1
    if cause in {"missing_guidance", "telemetry_only", "telemetry_without_sessions"}:
        return 2
    if cause == "healthy":
        return 4
    return 3


def build_report(
    audit: dict,
    *,
    active_helper_slo_pct: float = DEFAULT_ACTIVE_HELPER_SLO_PCT,
    helper_usage_slo_pct: float = DEFAULT_HELPER_USAGE_SLO_PCT,
) -> dict:
    summary = audit.get("summary", {}) or {}
    repos = audit.get("repos", []) or []
    expected_skill = audit.get("expected_skill", {}) or {}
    active_repo_count = int(summary.get("repos_with_recent_sessions", 0) or 0)
    active_helper_repos = int(summary.get("active_repos_with_helper_usage", 0) or 0)
    helper_repos = int(summary.get("repos_with_helper_usage", 0) or 0)
    repo_count = int(summary.get("repo_count", 0) or 0)
    active_helper_pct = pct(active_helper_repos, active_repo_count)
    helper_usage_pct = pct(helper_repos, repo_count)

    interventions: list[dict] = []
    cause_counts: dict[str, int] = {}
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        cause, action = classify_repo(repo, expected_skill)
        cause_counts[cause] = cause_counts.get(cause, 0) + 1
        if cause in {
            "missing_install",
            "missing_guidance",
            "wrong_skill_root",
            "version_drift",
            "commit_drift",
            "active_no_helper",
            "telemetry_only",
            "telemetry_without_sessions",
        }:
            interventions.append(
                {
                    "repo": repo.get("repo", ""),
                    "cause": cause,
                    "sessions": int(repo.get("session_count", 0) or 0),
                    "helper_sessions": int(repo.get("helper_sessions", 0) or 0),
                    "telemetry_helper_calls": int(repo.get("telemetry_helper_calls", 0) or 0),
                    "docs": bool(repo.get("token_reduce_docs")),
                    "installed": bool(repo.get("local_skill_installed")),
                    "action": action,
                    "priority": repo_priority(repo, cause),
                }
            )
    interventions.sort(key=lambda row: (int(row["priority"]), -int(row["sessions"]), str(row["repo"])))

    slo = {
        "active_helper_usage_target_pct": active_helper_slo_pct,
        "active_helper_usage_actual_pct": active_helper_pct,
        "active_helper_usage_pass": active_helper_pct >= active_helper_slo_pct if active_repo_count else False,
        "workspace_helper_usage_target_pct": helper_usage_slo_pct,
        "workspace_helper_usage_actual_pct": helper_usage_pct,
        "workspace_helper_usage_pass": helper_usage_pct >= helper_usage_slo_pct if repo_count else False,
        "active_repos_without_helper_usage": audit.get("gaps", {}).get("active_without_helper_usage", []),
    }

    findings: list[dict[str, str]] = []
    if not slo["active_helper_usage_pass"]:
        findings.append(
            {
                "priority": "high",
                "area": "active_repo_adoption",
                "finding": (
                    f"Active repo helper usage is {active_helper_pct:.1f}% "
                    f"({active_helper_repos}/{active_repo_count}), below target {active_helper_slo_pct:.1f}%."
                ),
                "recommendation": "Prioritize active_no_helper repos before adding more dependency integrations.",
            }
        )
    if not slo["workspace_helper_usage_pass"]:
        findings.append(
            {
                "priority": "medium",
                "area": "workspace_adoption",
                "finding": (
                    f"Only {helper_usage_pct:.1f}% of workspace repos show helper usage "
                    f"({helper_repos}/{repo_count})."
                ),
                "recommendation": "Keep workspace-install clean, then use SessionStart nudges and repo-specific interventions.",
            }
        )
    if int(summary.get("install_and_docs_compliant", 0) or 0) == repo_count and interventions:
        findings.append(
            {
                "priority": "medium",
                "area": "behavior_not_install",
                "finding": "All repos have install/docs compliance, but adoption gaps remain.",
                "recommendation": "Treat this as an agent-routing problem: nudge first moves and track missed opportunities.",
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": audit.get("workspace_root", ""),
        "lookback_days": audit.get("lookback_days", 0),
        "expected_skill": expected_skill,
        "summary": summary,
        "slo": slo,
        "cause_counts": cause_counts,
        "findings": findings,
        "interventions": interventions,
    }


def render_markdown(report: dict) -> str:
    summary = report.get("summary", {}) or {}
    slo = report.get("slo", {}) or {}
    lines = [
        "# Token-Reduce Adoption Improvement Report",
        "",
        f"- Generated: `{report.get('generated_at', '')}`",
        f"- Workspace: `{report.get('workspace_root', '')}`",
        f"- Lookback days: `{report.get('lookback_days', '')}`",
        f"- Expected skill: `{report.get('expected_skill', {}).get('root', '')}`",
        "",
        "## SLO",
        "",
        (
            f"- Active repo helper usage: `{slo.get('active_helper_usage_actual_pct', 0.0)}%` "
            f"(target `{slo.get('active_helper_usage_target_pct', 0.0)}%`, "
            f"pass `{str(slo.get('active_helper_usage_pass', False)).lower()}`)"
        ),
        (
            f"- Workspace helper usage: `{slo.get('workspace_helper_usage_actual_pct', 0.0)}%` "
            f"(target `{slo.get('workspace_helper_usage_target_pct', 0.0)}%`, "
            f"pass `{str(slo.get('workspace_helper_usage_pass', False)).lower()}`)"
        ),
        f"- Recent sessions: `{summary.get('total_recent_sessions', 0)}`",
        f"- Active repos: `{summary.get('repos_with_recent_sessions', 0)}`",
        f"- Active repos with helper usage: `{summary.get('active_repos_with_helper_usage', 0)}`",
        "",
    ]

    findings = report.get("findings", []) or []
    if findings:
        lines.extend(["## Findings", ""])
        for finding in findings:
            lines.append(
                f"- **{str(finding.get('priority', '')).upper()} · {finding.get('area', '')}**: "
                f"{finding.get('finding', '')} Recommendation: {finding.get('recommendation', '')}"
            )
        lines.append("")

    interventions = report.get("interventions", []) or []
    lines.extend(
        [
            "## Interventions",
            "",
            "| Repo | Cause | Sessions | Helper sessions | Telemetry calls | Action |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in interventions[:30]:
        lines.append(
            f"| `{row.get('repo', '')}` | `{row.get('cause', '')}` | {row.get('sessions', 0)} | "
            f"{row.get('helper_sessions', 0)} | {row.get('telemetry_helper_calls', 0)} | "
            f"{row.get('action', '')} |"
        )
    if not interventions:
        lines.append("| _none_ | `healthy` | 0 | 0 | 0 | Keep monitoring. |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-json", help="Read an existing workspace-audit JSON artifact.")
    parser.add_argument("--workspace-root", default="/home/agents/workspace")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--include-source-repo", action="store_true")
    parser.add_argument("--active-helper-slo-pct", type=float, default=DEFAULT_ACTIVE_HELPER_SLO_PCT)
    parser.add_argument("--helper-usage-slo-pct", type=float, default=DEFAULT_HELPER_USAGE_SLO_PCT)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()

    if args.audit_json:
        audit = load_audit(Path(args.audit_json))
    else:
        audit = build_payload(Path(args.workspace_root).resolve(), args.days, args.include_source_repo)
    report = build_report(
        audit,
        active_helper_slo_pct=args.active_helper_slo_pct,
        helper_usage_slo_pct=args.helper_usage_slo_pct,
    )
    encoded = json.dumps(report, indent=2)
    markdown = render_markdown(report)
    if args.output_json:
        out = Path(args.output_json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded + "\n", encoding="utf-8")
    if args.output_md:
        out_md = Path(args.output_md).resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(markdown, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
