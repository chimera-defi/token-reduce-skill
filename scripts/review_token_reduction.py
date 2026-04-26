#!/usr/bin/env python3
"""Turn token-reduce metrics into prioritized recommendations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from measure_token_reduction import measure


def health_score(report: dict) -> float:
    compliance = float(
        report["compliance"].get(
            "discovery_compliance_pct_observed",
            report["compliance"]["discovery_compliance_pct"],
        )
    )
    helper = float(
        report["adoption"].get(
            "helper_sessions_pct_observed_discovery",
            report["routing"]["helper_first_or_helper_any_pct"],
        )
    )
    telemetry_events = int(report["telemetry"]["event_count"])
    telemetry_component = 100.0 if telemetry_events > 0 else 0.0
    return round((compliance * 0.45) + (helper * 0.4) + (telemetry_component * 0.15), 1)


def build_findings(report: dict) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    session_count = int(report.get("session_count", 0))
    compliance_all = float(report["compliance"]["discovery_compliance_pct"])
    compliance_observed = float(report["compliance"].get("discovery_compliance_pct_observed", compliance_all))
    helper_all = float(report["routing"]["helper_first_or_helper_any_pct"])
    helper_observed = float(report["adoption"].get("helper_sessions_pct_observed_discovery", helper_all))
    observed_discovery_sessions = int(report["compliance"].get("sessions_with_first_discovery_observed", 0))
    compliance = compliance_observed if observed_discovery_sessions > 0 else compliance_all
    helper = helper_observed if observed_discovery_sessions > 0 else helper_all
    broad = int(report["compliance"]["sessions_with_broad_scan_violation"])
    mentions_without_helper_all = int(report["adoption"].get("mention_without_helper_sessions", 0))
    mentions_without_helper_observed = int(
        report["adoption"].get("mention_without_helper_sessions_observed", mentions_without_helper_all)
    )
    mentions_without_helper = (
        mentions_without_helper_observed if observed_discovery_sessions > 0 else mentions_without_helper_all
    )
    caveman_mentions = int(report["adoption"].get("caveman_mentions", 0))
    caveman_command_sessions = int(report["adoption"].get("caveman_command_sessions", 0))
    caveman_command_pct = float(report["adoption"].get("caveman_command_pct", 0.0))
    axi_tool_pct = float(report["adoption"].get("axi_tool_sessions_pct", 0.0))
    telemetry_events = int(report["telemetry"]["event_count"])
    telemetry_windows = report.get("telemetry_windows", {})
    window_1d = telemetry_windows.get("1d", {}) if isinstance(telemetry_windows, dict) else {}
    window_14d = telemetry_windows.get("14d", {}) if isinstance(telemetry_windows, dict) else {}
    efficiency = report["telemetry"].get("efficiency", {})
    logging = report["telemetry"].get("logging", {})
    helper_error_rate = float(efficiency.get("helper_error_rate_pct", 0.0))
    retry_overhead_pct = float(efficiency.get("retry_overhead_pct", 0.0))
    helper_latency_p95_ms = float(efficiency.get("helper_latency_p95_ms", 0.0))
    helper_latency_max_ms = float(efficiency.get("helper_latency_max_ms", 0.0))
    hook_errors = int(efficiency.get("hook_error_count", 0))
    pending_leak_count = int(efficiency.get("pending_leak_count", 0))
    logging_quality_score = float(logging.get("logging_quality_score", 0.0))
    logging_quality_tier = str(logging.get("logging_quality_tier", "no_data"))
    latency_coverage_pct = float(logging.get("helper_latency_coverage_pct", 0.0))
    exit_code_coverage_pct = float(logging.get("helper_exit_code_coverage_pct", 0.0))
    backend_coverage_pct = float(logging.get("helper_backend_coverage_pct", 0.0))
    status_exit_mismatch_count = int(logging.get("helper_status_exit_mismatch_count", 0))
    window_1d_helper_calls = int(window_1d.get("helper_calls", 0) or 0)
    window_1d_latency_p95 = float(window_1d.get("helper_latency_p95_ms", 0.0) or 0.0)
    window_1d_logging_score = float(window_1d.get("logging_quality_score", 0.0) or 0.0)

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
    if helper_error_rate > 5.0:
        findings.append(
            {
                "priority": "high",
                "area": "helper_errors",
                "finding": f"Helper error rate is elevated at {helper_error_rate:.1f}%.",
                "recommendation": "Inspect helper failures and root-cause command/repo resolution issues so helper calls are not retried repeatedly.",
            }
        )
    if retry_overhead_pct > 10.0:
        findings.append(
            {
                "priority": "high",
                "area": "retry_overhead",
                "finding": f"Helper retry overhead is high at {retry_overhead_pct:.1f}% of helper calls.",
                "recommendation": "Track repeated helper queries and enforce dependency-health fixes when retries exceed the threshold.",
            }
        )
    if helper_latency_p95_ms > 8000.0:
        findings.append(
            {
                "priority": "high",
                "area": "latency_overhead",
                "finding": (
                    f"Helper latency is elevated (p95 {helper_latency_p95_ms:.0f} ms, "
                    f"max {helper_latency_max_ms:.0f} ms)."
                ),
                "recommendation": (
                    "Inspect dependency latency (QMD collection refresh/search, filesystem scope, "
                    "and fallback path noise) and treat high-latency calls as overhead even when status is ok."
                ),
            }
        )
    if logging_quality_tier == "low" or logging_quality_score < 75.0:
        findings.append(
            {
                "priority": "high",
                "area": "logging_coverage",
                "finding": (
                    f"Helper telemetry coverage is weak (quality {logging_quality_score:.1f}, "
                    f"tier {logging_quality_tier})."
                ),
                "recommendation": (
                    "Ensure all helper tiers emit consistent latency, backend, lines/chars, and exit_code fields "
                    "so latency and savings outcomes can be trusted."
                ),
            }
        )
    if status_exit_mismatch_count > 0:
        findings.append(
            {
                "priority": "high",
                "area": "telemetry_integrity",
                "finding": f"Found {status_exit_mismatch_count} helper events with status/exit_code mismatch.",
                "recommendation": "Treat these as instrumentation bugs and fix wrappers so status and exit codes align.",
            }
        )
    if latency_coverage_pct < 95.0:
        findings.append(
            {
                "priority": "medium",
                "area": "latency_observability",
                "finding": f"Latency coverage is incomplete at {latency_coverage_pct:.1f}% of helper events.",
                "recommendation": "Log latency_ms for every helper invocation path, including structural and error branches.",
            }
        )
    if exit_code_coverage_pct < 95.0:
        findings.append(
            {
                "priority": "medium",
                "area": "exitcode_observability",
                "finding": f"Exit-code coverage is incomplete at {exit_code_coverage_pct:.1f}% of helper events.",
                "recommendation": "Include integer exit_code in helper telemetry to separate true failures from retries.",
            }
        )
    if backend_coverage_pct < 80.0:
        findings.append(
            {
                "priority": "medium",
                "area": "backend_attribution",
                "finding": f"Backend attribution is low at {backend_coverage_pct:.1f}% of helper events.",
                "recommendation": "Emit backend tags (qmd/rg/token-savior/path-hint) so latency can be traced to the right tier.",
            }
        )
    if window_1d_helper_calls >= 5 and window_1d_logging_score >= 90.0 and logging_quality_score < 80.0:
        findings.append(
            {
                "priority": "low",
                "area": "telemetry_trend",
                "finding": (
                    f"Recent runtime logging quality looks improved ({window_1d_logging_score:.1f} over 1d) "
                    f"vs 14d aggregate ({logging_quality_score:.1f})."
                ),
                "recommendation": "Keep collecting runtime sessions; treat current low 14d score as mixed legacy+current instrumentation until the window rolls forward.",
            }
        )
    if window_1d_helper_calls >= 5 and 0 < window_1d_latency_p95 < helper_latency_p95_ms:
        findings.append(
            {
                "priority": "low",
                "area": "latency_trend",
                "finding": (
                    f"Recent runtime latency p95 ({window_1d_latency_p95:.0f} ms over 1d) "
                    f"is below 14d aggregate ({helper_latency_p95_ms:.0f} ms)."
                ),
                "recommendation": "Use both 1d and 14d windows in release decisions to separate current regressions from historical tail behavior.",
            }
        )
    if hook_errors > 0:
        findings.append(
            {
                "priority": "high",
                "area": "hook_runtime_errors",
                "finding": f"Hook runtime errors were recorded ({hook_errors}).",
                "recommendation": "Stabilize hook input parsing and state-path resolution so pending state and enforcement behavior remain consistent.",
            }
        )
    if pending_leak_count > 0:
        findings.append(
            {
                "priority": "high",
                "area": "hook_state_persistence",
                "finding": f"Pending helper state appears to leak ({pending_leak_count} more marks than clears).",
                "recommendation": "Audit session-key handling and helper clear paths so marked pending state is reliably cleared after compliant helper kickoff.",
            }
        )
    if compliance < 80.0:
        scope_note = (
            " among sessions with observed discovery actions"
            if observed_discovery_sessions > 0
            else ""
        )
        findings.append(
            {
                "priority": "high",
                "area": "hook_coverage",
                "finding": f"Discovery compliance{scope_note} is only {compliance:.1f}%.",
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
        helper_scope_note = (
            " among sessions with observed discovery actions"
            if observed_discovery_sessions > 0
            else ""
        )
        findings.append(
            {
                "priority": "medium",
                "area": "helper_adoption",
                "finding": f"Helper usage{helper_scope_note} is still only {helper:.1f}%.",
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
        scope_note = (
            " with observed discovery actions"
            if observed_discovery_sessions > 0
            else ""
        )
        findings.append(
            {
                "priority": "medium",
                "area": "prompt_skill_gap",
                "finding": f"{mentions_without_helper} sessions{scope_note} mentioned token-reduce without using the helper.",
                "recommendation": "Tighten wording and examples so mentioning the skill correlates with helper invocation instead of vague compliance.",
            }
        )
    if caveman_mentions > 0 and caveman_command_sessions == 0:
        findings.append(
            {
                "priority": "medium",
                "area": "caveman_activation_gap",
                "finding": "Caveman is being mentioned but not actually activated in measured sessions.",
                "recommendation": "Add explicit examples (`/caveman lite`, `/caveman:compress CLAUDE.md`) to repo instructions so mentions convert into usage.",
            }
        )
    if session_count >= 20 and caveman_command_pct < 5.0:
        findings.append(
            {
                "priority": "medium",
                "area": "caveman_adoption",
                "finding": f"Caveman command usage is low at {caveman_command_pct:.1f}% of sessions.",
                "recommendation": "Install caveman globally and add short trigger cues in AGENTS.md/CLAUDE.md where terse output is useful.",
            }
        )
    if session_count >= 20 and axi_tool_pct < 2.0:
        findings.append(
            {
                "priority": "low",
                "area": "axi_adoption",
                "finding": f"AXI companion tool usage is low at {axi_tool_pct:.1f}% of sessions.",
                "recommendation": "For GitHub/browser-heavy tasks, prefer gh-axi or chrome-devtools-axi where available to reduce turns and retries.",
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
        f"- Discovery sessions observed: `{report['compliance'].get('sessions_with_first_discovery_observed', 0)}`",
        f"- Discovery compliance (all sessions): `{report['compliance']['discovery_compliance_pct']}%`",
        f"- Discovery compliance (observed sessions): `{report['compliance'].get('discovery_compliance_pct_observed', report['compliance']['discovery_compliance_pct'])}%`",
        f"- Helper usage (all sessions): `{report['routing']['helper_first_or_helper_any_pct']}%`",
        f"- Helper usage (observed sessions): `{report['adoption'].get('helper_sessions_pct_observed_discovery', report['routing']['helper_first_or_helper_any_pct'])}%`",
        f"- Caveman command usage: `{report['adoption'].get('caveman_command_pct', 0.0)}%`",
        f"- AXI tool usage: `{report['adoption'].get('axi_tool_sessions_pct', 0.0)}%`",
        f"- Telemetry events (14d, runtime): `{report['telemetry']['event_count']}`",
        f"- Telemetry events excluded (benchmark/test): `{report['telemetry'].get('excluded_event_count', 0)}`",
        f"- Telemetry window 1d (helpers / p95 / logging): `{report.get('telemetry_windows', {}).get('1d', {}).get('helper_calls', 0)} / {report.get('telemetry_windows', {}).get('1d', {}).get('helper_latency_p95_ms', 0.0)} ms / {report.get('telemetry_windows', {}).get('1d', {}).get('logging_quality_score', 0.0)}`",
        f"- Telemetry window 14d (helpers / p95 / logging): `{report.get('telemetry_windows', {}).get('14d', {}).get('helper_calls', 0)} / {report.get('telemetry_windows', {}).get('14d', {}).get('helper_latency_p95_ms', 0.0)} ms / {report.get('telemetry_windows', {}).get('14d', {}).get('logging_quality_score', 0.0)}`",
        f"- Helper error rate: `{report['telemetry'].get('efficiency', {}).get('helper_error_rate_pct', 0.0)}%`",
        f"- Retry overhead: `{report['telemetry'].get('efficiency', {}).get('retry_overhead_pct', 0.0)}%`",
        f"- Helper latency p95: `{report['telemetry'].get('efficiency', {}).get('helper_latency_p95_ms', 0.0)} ms`",
        f"- Logging quality: `{report['telemetry'].get('logging', {}).get('logging_quality_score', 0.0)}` (`{report['telemetry'].get('logging', {}).get('logging_quality_tier', 'no_data')}`)",
        f"- Latency coverage: `{report['telemetry'].get('logging', {}).get('helper_latency_coverage_pct', 0.0)}%`",
        f"- Exit-code coverage: `{report['telemetry'].get('logging', {}).get('helper_exit_code_coverage_pct', 0.0)}%`",
        f"- Backend coverage: `{report['telemetry'].get('logging', {}).get('helper_backend_coverage_pct', 0.0)}%`",
        f"- Status/exit mismatches: `{report['telemetry'].get('logging', {}).get('helper_status_exit_mismatch_count', 0)}`",
        f"- Hook errors: `{report['telemetry'].get('efficiency', {}).get('hook_error_count', 0)}`",
        f"- Pending state leaks: `{report['telemetry'].get('efficiency', {}).get('pending_leak_count', 0)}`",
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
            "discovery_compliance_pct_observed": report["compliance"].get(
                "discovery_compliance_pct_observed",
                report["compliance"]["discovery_compliance_pct"],
            ),
            "helper_first_or_helper_any_pct": report["routing"]["helper_first_or_helper_any_pct"],
            "helper_sessions_pct_observed_discovery": report["adoption"].get(
                "helper_sessions_pct_observed_discovery",
                report["routing"]["helper_first_or_helper_any_pct"],
            ),
            "telemetry_event_count": report["telemetry"]["event_count"],
            "telemetry_excluded_event_count": report["telemetry"].get("excluded_event_count", 0),
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
