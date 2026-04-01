#!/usr/bin/env python3
"""Turn token-reduce metrics into prioritized recommendations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from measure_token_reduction import measure


def health_score(report: dict) -> float:
    compliance = float(report["compliance"]["discovery_compliance_pct"])
    helper = float(report["routing"]["helper_first_or_helper_any_pct"])
    telemetry_events = int(report["telemetry"]["event_count"])
    telemetry_component = 100.0 if telemetry_events > 0 else 0.0
    return round((compliance * 0.45) + (helper * 0.4) + (telemetry_component * 0.15), 1)


def build_findings(report: dict) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    session_count = int(report.get("session_count", 0))
    compliance = float(report["compliance"]["discovery_compliance_pct"])
    helper = float(report["routing"]["helper_first_or_helper_any_pct"])
    broad = int(report["compliance"]["sessions_with_broad_scan_violation"])
    mentions_without_helper = int(report["adoption"].get("mention_without_helper_sessions", 0))
    telemetry_events = int(report["telemetry"]["event_count"])

    codex = report["by_source"].get("codex", {})
    claude = report["by_source"].get("claude", {})
    codex_helper = float(codex.get("helper_first_or_helper_any_pct", 0.0))
    claude_helper = float(claude.get("helper_first_or_helper_any_pct", 0.0))

    if session_count == 0:
        findings.append(
            {
                "priority": "medium",
                "area": "sample_size",
                "finding": "No Claude or Codex session logs were found for this scope yet.",
                "recommendation": "Finish setup, exercise the helper in a few real sessions, then rerun measure and review.",
            }
        )
        if telemetry_events == 0:
            findings.append(
                {
                    "priority": "medium",
                    "area": "telemetry",
                    "finding": "No helper or hook telemetry has been recorded yet.",
                    "recommendation": "Run token-reduce-paths or token-reduce-snippet after setup to confirm events land in artifacts/token-reduction/events.jsonl.",
                }
            )
        return findings

    if telemetry_events == 0:
        findings.append(
            {
                "priority": "high",
                "area": "telemetry",
                "finding": "Direct helper and hook telemetry is missing.",
                "recommendation": "Confirm helper wrappers and Claude hooks are writing to artifacts/token-reduction/events.jsonl.",
            }
        )
    if compliance < 80.0:
        findings.append(
            {
                "priority": "high",
                "area": "hook_coverage",
                "finding": f"Discovery compliance is only {compliance:.1f}%.",
                "recommendation": "Tighten routing so broad Grep, Glob, and Bash fallbacks are blocked more consistently before discovery starts.",
            }
        )
    if codex_helper + 20.0 < claude_helper:
        findings.append(
            {
                "priority": "high",
                "area": "codex_routing",
                "finding": f"Codex helper usage ({codex_helper:.1f}%) trails Claude ({claude_helper:.1f}%) materially.",
                "recommendation": "Strengthen Codex-facing install prompts and routing guidance so token-reduce becomes the default first move more often.",
            }
        )
    if helper < 60.0:
        findings.append(
            {
                "priority": "medium",
                "area": "helper_adoption",
                "finding": f"Helper usage is still only {helper:.1f}% of measured sessions.",
                "recommendation": "Improve install verification and first-run prompting so the helper path gets exercised immediately after setup.",
            }
        )
    if broad > 0:
        findings.append(
            {
                "priority": "medium",
                "area": "broad_scans",
                "finding": f"{broad} measured sessions still attempted broad scans.",
                "recommendation": "Review blocked-tool telemetry and add missing patterns or tool coverage where broad scans still slip through.",
            }
        )
    if mentions_without_helper > 0:
        findings.append(
            {
                "priority": "medium",
                "area": "prompt_skill_gap",
                "finding": f"{mentions_without_helper} sessions mentioned token-reduce without using the helper.",
                "recommendation": "Tighten wording and examples so mentioning the skill correlates with helper invocation instead of vague compliance.",
            }
        )
    if not findings:
        findings.append(
            {
                "priority": "low",
                "area": "status",
                "finding": "No major telemetry-driven issues detected in the current sample.",
                "recommendation": "Keep collecting data and rerun the review after more Claude and Codex sessions.",
            }
        )
    return findings


def render_markdown(report: dict, findings: list[dict[str, str]]) -> str:
    lines = [
        "# Token-Reduce Self Review",
        "",
        f"- Health score: `{health_score(report)}`",
        f"- Session count: `{report['session_count']}`",
        f"- Discovery compliance: `{report['compliance']['discovery_compliance_pct']}%`",
        f"- Helper usage: `{report['routing']['helper_first_or_helper_any_pct']}%`",
        f"- Telemetry events (14d): `{report['telemetry']['event_count']}`",
        "",
        "## Prioritized Findings",
        "",
    ]
    for finding in findings:
        lines.extend(
            [
                f"- **{finding['priority'].upper()} · {finding['area']}**: {finding['finding']}",
                f"  Recommendation: {finding['recommendation']}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="repo", choices=["repo", "global"])
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = measure(args.scope, args.repo_root)
    findings = build_findings(report)
    payload = {
        "measured_at": report["measured_at"],
        "scope": report["scope"],
        "repo_root": report["repo_root"],
        "health_score": health_score(report),
        "summary": {
            "session_count": report["session_count"],
            "discovery_compliance_pct": report["compliance"]["discovery_compliance_pct"],
            "helper_first_or_helper_any_pct": report["routing"]["helper_first_or_helper_any_pct"],
            "telemetry_event_count": report["telemetry"]["event_count"],
        },
        "findings": findings,
        "report": report,
    }

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, indent=2) + "\n")
    markdown = render_markdown(report, findings)
    if args.output_md:
        Path(args.output_md).write_text(markdown)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
