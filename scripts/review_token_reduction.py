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
    headroom_mentions = int(report["adoption"].get("headroom_mentions", 0))
    headroom_command_sessions = int(report["adoption"].get("headroom_command_sessions", 0))
    headroom_command_pct = float(report["adoption"].get("headroom_command_pct", 0.0))
    axi_tool_pct = float(report["adoption"].get("axi_tool_sessions_pct", 0.0))
    telemetry_events = int(report["telemetry"]["event_count"])
    companion_recommendations = report["telemetry"].get("companion_recommendations", {})
    headroom_recommended_events = int(companion_recommendations.get("headroom_recommended_events", 0) or 0)
    headroom_conversion_pct = (
        round((headroom_command_sessions * 100.0 / headroom_recommended_events), 1)
        if headroom_recommended_events
        else 0.0
    )
    telemetry_windows = report.get("telemetry_windows", {})
    window_1d = telemetry_windows.get("1d", {}) if isinstance(telemetry_windows, dict) else {}
    _window_14d = telemetry_windows.get("14d", {}) if isinstance(telemetry_windows, dict) else {}
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
    recent_runtime_latency_healthy = window_1d_helper_calls >= 1 and 0.0 < window_1d_latency_p95 <= 2000.0

    codex = report["by_source"].get("codex", {})
    claude = report["by_source"].get("claude", {})
    codex_helper = float(codex.get("helper_first_or_helper_any_pct", 0.0))
    claude_helper = float(claude.get("helper_first_or_helper_any_pct", 0.0))

    # New telemetry signals
    efficiency_by_context = report["telemetry"].get("efficiency_by_context", {})
    runtime_efficiency = efficiency_by_context.get("runtime", {})
    benchmark_efficiency = efficiency_by_context.get("benchmark", {})
    qmd_breakdown = report["telemetry"].get("qmd_latency_breakdown", {})
    post_block_events = report["telemetry"].get("by_event", {})
    post_block_compliance = int(post_block_events.get("post_block_compliance", 0))
    post_block_escape = int(post_block_events.get("post_block_escape", 0))
    post_block_abandon = int(post_block_events.get("post_block_abandon", 0))
    post_block_total = post_block_compliance + post_block_escape + post_block_abandon
    discovery_outcomes = report["adoption"]
    discovery_miss_pct = float(discovery_outcomes.get("discovery_outcome_miss_pct", 0.0))
    discovery_standoff_pct = float(discovery_outcomes.get("discovery_outcome_standoff_pct", 0.0))
    discovery_direct_hit_pct = float(discovery_outcomes.get("discovery_outcome_direct_hit_pct", 0.0))

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
        if recent_runtime_latency_healthy:
            findings.append(
                {
                    "priority": "medium",
                    "area": "latency_overhead",
                    "finding": (
                        f"14d helper latency remains elevated (p95 {helper_latency_p95_ms:.0f} ms, "
                        f"max {helper_latency_max_ms:.0f} ms), but recent 1d runtime p95 is healthy "
                        f"({window_1d_latency_p95:.0f} ms)."
                    ),
                    "recommendation": (
                        "Treat this as historical tail latency; keep watching runtime windows while "
                        "continuing to reduce QMD-heavy paths."
                    ),
                }
            )
        else:
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
    if headroom_mentions > 0 and headroom_command_sessions == 0:
        findings.append(
            {
                "priority": "medium",
                "area": "headroom_adoption",
                "finding": "Headroom is mentioned in session text, but no Headroom command usage was detected.",
                "recommendation": "For large tool-result or long-session pressure, verify `headroom install status` or `/readyz`, then use `headroom wrap codex`/`headroom wrap claude` or the proxy with telemetry disabled.",
            }
        )
    if headroom_recommended_events > 0 and headroom_command_sessions == 0:
        findings.append(
            {
                "priority": "high",
                "area": "headroom_conversion",
                "finding": f"Headroom was recommended {headroom_recommended_events} time(s), but no Headroom command usage was detected.",
                "recommendation": "When adaptive routing recommends Headroom, run `headroom install status` or `/readyz`; if healthy, use `headroom wrap codex`/`headroom wrap claude` or the proxy with telemetry disabled.",
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
    if session_count >= 20 and headroom_command_pct < 5.0:
        findings.append(
            {
                "priority": "medium",
                "area": "headroom_adoption",
                "finding": f"Headroom command usage is low at {headroom_command_pct:.1f}% of sessions.",
                "recommendation": "Exercise Headroom on output-heavy test/log/API sessions and long-running agent sessions, then compare quality and latency against RTK/token-reduce alone.",
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
    if post_block_total >= 3 and post_block_escape > post_block_compliance:
        escape_rate = round((post_block_escape * 100.0 / post_block_total), 1)
        findings.append(
            {
                "priority": "high",
                "area": "post_block_escape",
                "finding": f"Agents escape hook blocks more than they comply ({post_block_escape} escapes vs {post_block_compliance} compliances, {escape_rate}% escape rate).",
                "recommendation": "Strengthen block coverage or add an immediate helper injection after block so the agent cannot retry with alternative broad-scan patterns.",
            }
        )
    if qmd_breakdown and qmd_breakdown.get("qmd_files_ms", {}).get("p95_ms", 0) > 5000:
        qmd_p95 = qmd_breakdown["qmd_files_ms"]["p95_ms"]
        qmd_avg = qmd_breakdown["qmd_files_ms"]["avg_ms"]
        if recent_runtime_latency_healthy:
            findings.append(
                {
                    "priority": "medium",
                    "area": "qmd_latency",
                    "finding": (
                        f"QMD latency is high in 14d aggregate (p95 {qmd_p95:.0f} ms, avg {qmd_avg:.0f} ms), "
                        f"but recent runtime latency is healthy ({window_1d_latency_p95:.0f} ms p95 in 1d)."
                    ),
                    "recommendation": (
                        "Keep collection masks tight and continue runtime monitoring; treat this as a backlog "
                        "cleanup signal unless 1d/2d windows regress."
                    ),
                }
            )
        else:
            findings.append(
                {
                    "priority": "high",
                    "area": "qmd_latency",
                    "finding": f"QMD search latency is high (p95 {qmd_p95:.0f} ms, avg {qmd_avg:.0f} ms).",
                    "recommendation": "Consider lowering TOKEN_REDUCE_QMD_REFRESH_TTL_SECONDS, pre-warming the QMD collection in CI, or reducing the indexed file mask to exclude generated artifacts.",
                }
            )
    if runtime_efficiency and runtime_efficiency.get("helper_latency_p95_ms", 0) > 0:
        rt_p95 = runtime_efficiency["helper_latency_p95_ms"]
        rt_avg = runtime_efficiency["helper_latency_avg_ms"]
        bm_p95 = benchmark_efficiency.get("helper_latency_p95_ms", 0)
        if rt_p95 < bm_p95 * 0.5:
            findings.append(
                {
                    "priority": "low",
                    "area": "runtime_vs_benchmark_latency",
                    "finding": f"Runtime helper latency (p95 {rt_p95:.0f} ms, avg {rt_avg:.0f} ms) is much lower than benchmark latency (p95 {bm_p95:.0f} ms).",
                    "recommendation": "Benchmark events are dominated by collection-creation spikes; use runtime-separated metrics for operational decisions.",
                }
            )
    if discovery_miss_pct > 10.0:
        findings.append(
            {
                "priority": "medium",
                "area": "discovery_outcome",
                "finding": f"{discovery_miss_pct:.1f}% of sessions used the helper but still broad-scanned afterward (miss).",
                "recommendation": "Helper results may be irrelevant or ignored; review top_returned_paths utilization and tune ranking or fallback behavior.",
            }
        )
    if discovery_standoff_pct > 15.0:
        findings.append(
            {
                "priority": "medium",
                "area": "discovery_outcome",
                "finding": f"{discovery_standoff_pct:.1f}% of sessions used the helper but performed no subsequent targeted reads (standoff).",
                "recommendation": "Agent may not trust helper results; add stronger prompt steering to read returned paths before alternative discovery.",
            }
        )
    if discovery_direct_hit_pct > 0 and discovery_direct_hit_pct < 30.0:
        findings.append(
            {
                "priority": "low",
                "area": "discovery_outcome",
                "finding": f"Only {discovery_direct_hit_pct:.1f}% of helper sessions converted to direct targeted reads (direct_hit).",
                "recommendation": "Track whether returned files are the right ones; low direct_hit may mean ranking quality or query relevance issues.",
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


# --------------------------------------------------------------------------- #
# Track D4 — per-companion conversion funnel
# --------------------------------------------------------------------------- #

_COMPANION_SAVINGS_PCT = {
    "headroom": 30.0,
    "caveman": 40.0,
    "context_mode": 50.0,
    "code_review_graph": 60.0,
    "axi": 15.0,
}


def _funnel_row(
    companion: str,
    *,
    mentions: int,
    recommended: int,
    used: int,
    sessions_total: int = 0,
) -> dict:
    conversion_pct = round((used * 100.0 / recommended), 1) if recommended else 0.0
    # Per-use savings is a benchmark constant from references/benchmarks/.
    # We surface two things: (1) the per-use constant so the reader knows
    # what one adoption is worth, and (2) the weighted-savings estimate:
    # (used / sessions_total) * per_use_savings — the share of sessions
    # plausibly benefiting at that per-use rate.
    per_use_savings_pct = round(_COMPANION_SAVINGS_PCT.get(companion, 0.0), 1)
    weighted_savings_pct = (
        round(per_use_savings_pct * used / sessions_total, 1)
        if used and sessions_total
        else 0.0
    )
    return {
        "companion": companion,
        "mentions": mentions,
        "recommended": recommended,
        "used": used,
        "conversion_pct": conversion_pct,
        "per_use_savings_pct": per_use_savings_pct,
        "weighted_savings_pct": weighted_savings_pct,
        # Back-compat alias for any consumer still reading the old key.
        "estimated_savings_pct": per_use_savings_pct,
    }


def build_companion_funnels(report: dict) -> list[dict]:
    """Return mention -> recommended -> used -> savings rows per companion.

    Mentions come from the adoption section (text scan), recommended from the
    telemetry section (router events), used from explicit command-session
    counts. Estimated savings are per-companion constants applied per use.
    """
    adoption = report.get("adoption", {}) or {}
    telemetry = report.get("telemetry", {}) or {}
    rec_events = telemetry.get("companion_recommendations", {}) or {}
    sessions_total = int(adoption.get("session_count", 0) or 0)

    rows: list[dict] = []
    rows.append(
        _funnel_row(
            "headroom",
            mentions=int(adoption.get("headroom_mentions", 0) or 0),
            recommended=int(rec_events.get("headroom_recommended_events", 0) or 0),
            used=int(adoption.get("headroom_command_sessions", 0) or 0),
            sessions_total=sessions_total,
        )
    )
    rows.append(
        _funnel_row(
            "caveman",
            mentions=int(adoption.get("caveman_mentions", 0) or 0),
            recommended=int(adoption.get("caveman_mentions", 0) or 0),
            used=int(adoption.get("caveman_command_sessions", 0) or 0),
            sessions_total=sessions_total,
        )
    )
    rows.append(
        _funnel_row(
            "context_mode",
            mentions=int(adoption.get("context_mode_mentions", 0) or 0),
            recommended=int(rec_events.get("context_mode_recommended_events", 0) or 0),
            used=int(adoption.get("context_mode_command_sessions", 0) or 0),
            sessions_total=sessions_total,
        )
    )
    rows.append(
        _funnel_row(
            "code_review_graph",
            mentions=int(adoption.get("code_review_graph_mentions", 0) or 0),
            recommended=int(rec_events.get("code_review_graph_recommended_events", 0) or 0),
            used=int(adoption.get("code_review_graph_command_sessions", 0) or 0),
            sessions_total=sessions_total,
        )
    )
    axi_used = int(adoption.get("axi_tool_sessions", 0) or 0)
    rows.append(
        _funnel_row(
            "axi",
            mentions=int(adoption.get("axi_mentions", 0) or 0),
            recommended=axi_used,
            used=axi_used,
            sessions_total=sessions_total,
        )
    )
    return rows


def format_companion_funnels_markdown(report: dict) -> str:
    rows = build_companion_funnels(report)
    lines = [
        "## Companion conversion funnel",
        "",
        "_Per-use savings is the benchmark constant. Weighted savings = per-use × (used / total sessions)._",
        "",
        "| Companion | Mentions | Recommended | Used | Conversion | Per-use savings | Weighted savings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['companion']} | {row['mentions']} | {row['recommended']} | "
            f"{row['used']} | {row['conversion_pct']}% | {row['per_use_savings_pct']}% | "
            f"{row['weighted_savings_pct']}% |"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: dict, findings: list[dict[str, str]]) -> str:
    companion_recommendations = report["telemetry"].get("companion_recommendations", {})
    headroom_recommended_events = int(companion_recommendations.get("headroom_recommended_events", 0) or 0)
    headroom_command_sessions = int(report["adoption"].get("headroom_command_sessions", 0) or 0)
    headroom_conversion_pct = (
        round((headroom_command_sessions * 100.0 / headroom_recommended_events), 1)
        if headroom_recommended_events
        else 0.0
    )
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
        f"- Headroom command usage: `{report['adoption'].get('headroom_command_pct', 0.0)}%`",
        f"- Headroom recommendation conversion: `{headroom_conversion_pct}%` ({headroom_command_sessions}/{headroom_recommended_events})",
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
        "## Context-Separated Efficiency",
        "",
    ]
    ctx_eff = report["telemetry"].get("efficiency_by_context", {})
    for ctx in ("runtime", "benchmark", "test"):
        eff = ctx_eff.get(ctx)
        if not eff:
            continue
        lines.append(
            f"- **{ctx}**: calls={eff['helper_calls']} "
            f"p95={eff['helper_latency_p95_ms']:.0f}ms "
            f"err={eff['helper_error_rate_pct']:.1f}% "
            f"retry={eff['failure_overhead_pct']:.1f}%"
        )
    lines.extend(["", "## QMD Sub-Latency Breakdown", ""])
    qmd = report["telemetry"].get("qmd_latency_breakdown", {})
    for phase in ("qmd_ensure_ms", "qmd_files_ms", "qmd_snippet_ms", "fallback_ms"):
        data = qmd.get(phase)
        if not data or data.get("count", 0) == 0:
            continue
        lines.append(
            f"- **{phase}**: count={data['count']} avg={data['avg_ms']:.0f}ms p50={data['p50_ms']:.0f}ms p95={data['p95_ms']:.0f}ms"
        )
    lines.extend(["", "## Discovery Outcomes", ""])
    outcomes = report["adoption"]
    for outcome in ("direct_hit", "indirect_hit", "miss", "standoff", "bypass", "direct"):
        pct_val = outcomes.get(f"discovery_outcome_{outcome}_pct", 0.0)
        lines.append(f"- **{outcome}**: `{pct_val:.1f}%`")
    # Track D4 + F2 — companion funnel and context impact sections appear
    # before the prioritized findings so reviewers see the rollups first.
    lines.extend(["", format_companion_funnels_markdown(report)])
    raw_sessions = report.get("raw_session_metrics") or []
    if raw_sessions:
        from cost_ledger import build_context_impact_markdown
        lines.extend(["", build_context_impact_markdown(raw_sessions)])
    lines.extend(["", "## Prioritized Findings", ""])
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
