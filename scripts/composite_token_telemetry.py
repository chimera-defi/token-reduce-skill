#!/usr/bin/env python3
"""Composite telemetry for token-reduce + companion tooling (RTK/QMD/hooks)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from measure_token_reduction import measure


def run_command(command: list[str], *, cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except FileNotFoundError as exc:
        return {"ok": False, "exit_code": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\ncommand timed out",
        }


def maybe_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def capture(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    result = run_command(command, cwd=cwd)
    payload: dict[str, Any] = {
        "command": command,
        "ok": result["ok"],
        "exit_code": result["exit_code"],
    }
    stderr = str(result.get("stderr", "")).strip()
    stdout = str(result.get("stdout", "")).strip()
    if stderr:
        payload["stderr"] = stderr
    if stdout:
        parsed = maybe_json(stdout)
        payload["data"] = parsed if parsed is not None else stdout
    return payload


def binary_info(name: str, version_cmd: list[str] | None = None) -> dict[str, Any]:
    path = shutil.which(name)
    info: dict[str, Any] = {"installed": bool(path), "path": path}
    if path and version_cmd:
        result = run_command(version_cmd)
        if result["ok"] and str(result.get("stdout", "")).strip():
            info["version"] = str(result["stdout"]).strip().splitlines()[0]
        elif str(result.get("stderr", "")).strip():
            info["version_error"] = str(result["stderr"]).strip().splitlines()[0]
    return info


def codex_skill_status(repo_root: Path) -> dict[str, Any]:
    skill_path = Path.home() / ".codex" / "skills" / "token-reduce"
    status: dict[str, Any] = {
        "path": str(skill_path),
        "exists": skill_path.exists(),
        "is_symlink": skill_path.is_symlink(),
    }
    if skill_path.exists():
        target = skill_path.resolve()
        status["resolved_target"] = str(target)
        status["points_to_repo"] = target == repo_root.resolve()
    return status


def _extract_commands(hook_entries: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for entry in hook_entries:
        for hook in entry.get("hooks", []):
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(command)
    return commands


def claude_hook_status() -> dict[str, Any]:
    settings_path = Path.home() / ".claude" / "settings.json"
    status: dict[str, Any] = {
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "read_error": None,
        "token_reduce_remind_count": 0,
        "token_reduce_enforce_matchers": [],
        "rtk_hook_commands": [],
    }
    if not settings_path.exists():
        return status

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive only
        status["read_error"] = str(exc)
        return status

    hooks = settings.get("hooks", {})
    user_prompt_submit = hooks.get("UserPromptSubmit", [])
    pre_tool_use = hooks.get("PreToolUse", [])
    ups_commands = _extract_commands(user_prompt_submit)
    ptu_commands = _extract_commands(pre_tool_use)

    status["token_reduce_remind_count"] = sum(
        1 for cmd in ups_commands if "remind-token-reduce.py" in cmd
    )
    status["token_reduce_enforce_matchers"] = sorted(
        {
            str(entry.get("matcher"))
            for entry in pre_tool_use
            for hook in entry.get("hooks", [])
            if "enforce-token-reduce-first.py" in str(hook.get("command", ""))
        }
    )
    status["rtk_hook_commands"] = sorted(
        {
            cmd
            for cmd in [*ups_commands, *ptu_commands]
            if "rtk-rewrite.sh" in cmd or "rtk rewrite" in cmd
        }
    )
    return status


def _extract_rtk_summary(command_payload: dict[str, Any]) -> dict[str, Any]:
    data = command_payload.get("data")
    if not isinstance(data, dict):
        return {}
    summary = data.get("summary")
    if not isinstance(summary, dict):
        return {}
    return {
        "total_commands": summary.get("total_commands"),
        "total_saved": summary.get("total_saved"),
        "avg_savings_pct": summary.get("avg_savings_pct"),
    }


def rtk_status(scope: str, repo_root: Path) -> dict[str, Any]:
    info = binary_info("rtk", ["rtk", "--version"])
    if not info["installed"]:
        return {"available": False, "binary": info}

    gain_cmd = ["rtk", "gain", "-f", "json"]
    if scope == "repo":
        gain_cmd.append("--project")

    discover_cmd = ["rtk", "discover", "--format", "json", "--since", "30"]
    if scope == "repo":
        discover_cmd.extend(["--project", str(repo_root)])
    else:
        discover_cmd.append("--all")

    gain = capture(gain_cmd, cwd=repo_root)
    discover = capture(discover_cmd, cwd=repo_root)
    session = capture(["rtk", "session"], cwd=repo_root)
    hook_audit = capture(["rtk", "hook-audit", "--since", "14"], cwd=repo_root)

    return {
        "available": True,
        "binary": info,
        "gain": gain,
        "discover": discover,
        "session": session,
        "hook_audit": hook_audit,
        "gain_summary": _extract_rtk_summary(gain),
    }


def benchmark_potential(repo_root: Path) -> dict[str, Any]:
    artifact = repo_root / "references" / "benchmarks" / "composite-benchmark.json"
    payload = maybe_json(artifact.read_text(encoding="utf-8")) if artifact.exists() else None
    if not isinstance(payload, dict):
        return {
            "artifact": str(artifact),
            "available": False,
            "quality_pass": False,
            "potential_savings_pct": 0.0,
        }

    benchmarks = payload.get("benchmarks")
    if not isinstance(benchmarks, list):
        return {
            "artifact": str(artifact),
            "available": False,
            "quality_pass": False,
            "potential_savings_pct": 0.0,
        }

    composite = next(
        (row for row in benchmarks if isinstance(row, dict) and row.get("name") == "composite_stack"),
        None,
    )
    broad = next(
        (row for row in benchmarks if isinstance(row, dict) and row.get("name") == "broad_shell"),
        None,
    )
    if not isinstance(composite, dict):
        return {
            "artifact": str(artifact),
            "available": False,
            "quality_pass": False,
            "potential_savings_pct": 0.0,
        }

    quality_pass = bool(composite.get("quality_pass"))
    potential_savings_pct = float(composite.get("savings_vs_broad_pct", 0.0) or 0.0)
    if not quality_pass:
        potential_savings_pct = 0.0
    return {
        "artifact": str(artifact),
        "available": True,
        "generated_at": payload.get("generated_at"),
        "quality_pass": quality_pass,
        "potential_savings_pct": round(max(0.0, potential_savings_pct), 1),
        "composite_tokens": composite.get("tokens"),
        "broad_tokens": broad.get("tokens") if isinstance(broad, dict) else None,
    }


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def realized_outcomes_summary(
    token_reduce: dict[str, Any], benchmark: dict[str, Any], dependency_overhead: dict[str, Any]
) -> dict[str, Any]:
    adoption = token_reduce.get("adoption", {})
    compliance = token_reduce.get("compliance", {})
    telemetry = token_reduce.get("telemetry", {})
    efficiency = telemetry.get("efficiency", {})
    logging = telemetry.get("logging", {})

    helper_calls = int(efficiency.get("helper_calls", 0) or 0)
    session_count = int(token_reduce.get("session_count", 0) or 0)
    observed_discovery_sessions = int(compliance.get("sessions_with_first_discovery_observed", 0) or 0)
    telemetry_events = int(telemetry.get("event_count", 0) or 0)
    telemetry_windows = token_reduce.get("telemetry_windows", {})
    window_1d = telemetry_windows.get("1d", {}) if isinstance(telemetry_windows, dict) else {}
    window_1d_helper_calls = int(window_1d.get("helper_calls", 0) or 0)

    helper_usage_pct = float(
        adoption.get("helper_sessions_pct_observed_discovery", adoption.get("helper_sessions_pct", 0.0)) or 0.0
    )
    compliance_pct = float(
        compliance.get(
            "discovery_compliance_pct_observed",
            compliance.get("discovery_compliance_pct", 0.0),
        )
        or 0.0
    )
    helper_error_rate_pct = float(efficiency.get("helper_error_rate_pct", 0.0) or 0.0)
    failure_overhead_pct = float(efficiency.get("failure_overhead_pct", 0.0) or 0.0)
    helper_latency_p95_ms = float(efficiency.get("helper_latency_p95_ms", 0.0) or 0.0)
    logging_quality_score = float(logging.get("logging_quality_score", 0.0) or 0.0)
    logging_tier = str(logging.get("logging_quality_tier", "no_data"))
    latency_reference_ms = helper_latency_p95_ms
    logging_reference_score = logging_quality_score
    latency_window_used = "14d"
    if window_1d_helper_calls >= 5:
        latency_reference_ms = round(
            helper_latency_p95_ms * 0.6 + float(window_1d.get("helper_latency_p95_ms", helper_latency_p95_ms)) * 0.4,
            1,
        )
        logging_reference_score = round(
            logging_quality_score * 0.6 + float(window_1d.get("logging_quality_score", logging_quality_score)) * 0.4,
            1,
        )
        latency_window_used = "blended_14d_1d"

    potential_savings_pct = float(benchmark.get("potential_savings_pct", 0.0) or 0.0)
    potential_available = bool(benchmark.get("available")) and bool(benchmark.get("quality_pass"))

    adoption_factor = _clamp(helper_usage_pct / 100.0, 0.0, 1.0)
    compliance_factor = _clamp(compliance_pct / 100.0, 0.0, 1.0)
    routing_realization_factor = adoption_factor * compliance_factor

    reliability_penalty = _clamp(
        (helper_error_rate_pct / 100.0) + (failure_overhead_pct / 100.0),
        0.0,
        0.8,
    )
    reliability_factor = round(1.0 - reliability_penalty, 3)

    latency_factor = 1.0
    if helper_calls > 0:
        latency_factor = _clamp(1.0 - max(0.0, latency_reference_ms - 4000.0) / 20000.0, 0.4, 1.0)
    logging_factor = _clamp(logging_reference_score / 100.0, 0.5, 1.0) if helper_calls > 0 else 0.0

    point_estimate_pct = (
        potential_savings_pct
        * routing_realization_factor
        * reliability_factor
        * latency_factor
        * logging_factor
    )

    sample_factor = _clamp(session_count / 50.0, 0.0, 1.0)
    telemetry_factor = _clamp(telemetry_events / 150.0, 0.0, 1.0)
    observed_factor = _clamp(observed_discovery_sessions / 40.0, 0.0, 1.0)
    confidence_score = round(
        (sample_factor * 0.4 + telemetry_factor * 0.3 + observed_factor * 0.3) * 100.0,
        1,
    )

    confidence_factor = _clamp(confidence_score / 100.0, 0.15, 1.0)
    uncertainty = 1.0 - confidence_factor
    conservative_pct = round(point_estimate_pct * _clamp(0.5 + confidence_factor * 0.5, 0.5, 1.0), 1)
    optimistic_pct = round(point_estimate_pct * _clamp(1.0 + uncertainty * 0.2, 1.0, 1.2), 1)
    realized_pct = round(point_estimate_pct, 1)

    headroom_pct = round(max(0.0, potential_savings_pct - realized_pct), 1)

    honesty_flags: list[str] = []
    if not potential_available:
        honesty_flags.append("benchmark_potential_unavailable_or_quality_fail")
    if confidence_score < 60.0:
        honesty_flags.append("low_confidence_sample")
    if logging_tier == "low":
        honesty_flags.append("low_logging_coverage")
    if latency_reference_ms > 8000.0:
        honesty_flags.append("high_helper_latency_p95")
    if float(dependency_overhead.get("helper_failure_overhead_pct", 0.0) or 0.0) > 10.0:
        honesty_flags.append("high_failure_overhead")

    return {
        "potential_savings_pct": round(potential_savings_pct, 1),
        "realized_savings_estimate_pct": realized_pct,
        "realized_savings_conservative_pct": conservative_pct,
        "realized_savings_optimistic_pct": optimistic_pct,
        "headroom_to_potential_pct": headroom_pct,
        "factors": {
            "helper_usage_pct_observed": round(helper_usage_pct, 1),
            "discovery_compliance_pct_observed": round(compliance_pct, 1),
            "routing_realization_factor": round(routing_realization_factor, 3),
            "reliability_factor": round(reliability_factor, 3),
            "latency_factor": round(latency_factor, 3),
            "latency_reference_ms": round(latency_reference_ms, 1),
            "latency_window_used": latency_window_used,
            "logging_factor": round(logging_factor, 3),
            "logging_reference_score": round(logging_reference_score, 1),
        },
        "confidence": {
            "score_pct": confidence_score,
            "sample_factor": round(sample_factor, 3),
            "telemetry_factor": round(telemetry_factor, 3),
            "observed_discovery_factor": round(observed_factor, 3),
        },
        "honesty": {
            "model": "potential * routing_realization * reliability * latency * logging",
            "flags": honesty_flags,
        },
    }


def dependency_overhead_summary(token_reduce: dict[str, Any], rtk: dict[str, Any]) -> dict[str, Any]:
    efficiency = token_reduce.get("telemetry", {}).get("efficiency", {})
    logging = token_reduce.get("telemetry", {}).get("logging", {})
    helper_calls = int(efficiency.get("helper_calls", 0) or 0)
    helper_error_calls = int(efficiency.get("helper_error_calls", 0) or 0)
    rapid_repeat_calls = int(efficiency.get("rapid_repeat_calls", 0) or 0)
    error_recovery_retries = int(efficiency.get("error_recovery_retries", 0) or 0)
    hook_error_count = int(efficiency.get("hook_error_count", 0) or 0)
    pending_leak_count = int(efficiency.get("pending_leak_count", 0) or 0)
    helper_latency_p95_ms = float(efficiency.get("helper_latency_p95_ms", 0.0) or 0.0)
    helper_latency_p50_ms = float(efficiency.get("helper_latency_p50_ms", 0.0) or 0.0)
    logging_quality_score = float(logging.get("logging_quality_score", 0.0) or 0.0)
    logging_quality_tier = str(logging.get("logging_quality_tier", "no_data"))

    rtk_failed_checks = 0
    if rtk.get("available"):
        for key in ("gain", "discover", "session", "hook_audit"):
            payload = rtk.get(key, {})
            if isinstance(payload, dict) and payload and not payload.get("ok", False):
                rtk_failed_checks += 1

    failure_overhead_calls = helper_error_calls + error_recovery_retries
    failure_overhead_pct = (
        round((failure_overhead_calls * 100.0 / helper_calls), 1) if helper_calls else 0.0
    )
    error_rate_pct = (
        round((helper_error_calls * 100.0 / helper_calls), 1) if helper_calls else 0.0
    )
    estimated_overhead_events = failure_overhead_calls + hook_error_count + pending_leak_count + rtk_failed_checks
    healthy = (
        failure_overhead_pct <= 10.0
        and error_rate_pct <= 5.0
        and hook_error_count == 0
        and pending_leak_count == 0
        and helper_latency_p95_ms <= 8000.0
        and logging_quality_score >= 75.0
        and rtk_failed_checks == 0
    )

    return {
        "helper_calls": helper_calls,
        "helper_error_calls": helper_error_calls,
        "helper_error_rate_pct": error_rate_pct,
        "helper_rapid_repeat_calls": rapid_repeat_calls,
        "helper_error_recovery_retries": error_recovery_retries,
        "helper_failure_overhead_calls": failure_overhead_calls,
        "helper_failure_overhead_pct": failure_overhead_pct,
        "helper_latency_p50_ms": round(helper_latency_p50_ms, 1),
        "helper_latency_p95_ms": round(helper_latency_p95_ms, 1),
        "logging_quality_score": round(logging_quality_score, 1),
        "logging_quality_tier": logging_quality_tier,
        "hook_error_count": hook_error_count,
        "pending_leak_count": pending_leak_count,
        "rtk_failed_checks": rtk_failed_checks,
        "estimated_overhead_events": estimated_overhead_events,
        "healthy": healthy,
    }


def composite(scope: str, repo_root: Path) -> dict[str, Any]:
    token_reduce = measure(scope, str(repo_root))
    rtk = rtk_status(scope, repo_root)
    benchmark = benchmark_potential(repo_root)
    dependency_overhead = dependency_overhead_summary(token_reduce, rtk)
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "repo_root": str(repo_root),
        "token_reduce": token_reduce,
        "benchmark_potential": benchmark,
        "realized_outcomes": realized_outcomes_summary(token_reduce, benchmark, dependency_overhead),
        "integration_status": {
            "binaries": {
                "token_reduce_paths": binary_info("token-reduce-paths"),
                "token_reduce_snippet": binary_info("token-reduce-snippet"),
                "token_reduce_manage": binary_info("token-reduce-manage"),
                "qmd": binary_info("qmd", ["qmd", "--version"]),
                "rtk": binary_info("rtk", ["rtk", "--version"]),
            },
            "codex_skill": codex_skill_status(repo_root),
            "claude_hooks": claude_hook_status(),
        },
        "rtk": rtk,
        "dependency_overhead": dependency_overhead,
    }


def write_markdown(report: dict[str, Any], output_path: Path) -> None:
    token_reduce = report["token_reduce"]
    adoption = token_reduce["adoption"]
    compliance = token_reduce["compliance"]
    telemetry = token_reduce["telemetry"]
    efficiency = telemetry.get("efficiency", {})
    logging = telemetry.get("logging", {})
    rtk = report["rtk"]
    benchmark = report.get("benchmark_potential", {})
    realized = report.get("realized_outcomes", {})
    dependency_overhead = report.get("dependency_overhead", {})
    gain_summary = rtk.get("gain_summary", {})
    md = f"""# Composite Token Telemetry

- Scope: `{report['scope']}`
- Measured at: `{report['measured_at']}`
- Repo: `{report['repo_root']}`

## Potential Vs Realized

- Benchmark potential savings: `{realized.get('potential_savings_pct', benchmark.get('potential_savings_pct', 0.0))}%`
- Realized savings estimate: `{realized.get('realized_savings_estimate_pct', 0.0)}%`
- Realized savings (conservative): `{realized.get('realized_savings_conservative_pct', 0.0)}%`
- Realized savings (optimistic): `{realized.get('realized_savings_optimistic_pct', 0.0)}%`
- Headroom to potential: `{realized.get('headroom_to_potential_pct', 0.0)}%`
- Honesty flags: `{", ".join(realized.get('honesty', {}).get('flags', [])) or "none"}`

## Token-Reduce Runtime

- Session count: `{token_reduce['session_count']}`
- Discovery sessions observed: `{compliance.get('sessions_with_first_discovery_observed', 0)}`
- Helper usage pct (all): `{adoption['helper_sessions_pct']}`
- Helper usage pct (observed): `{adoption.get('helper_sessions_pct_observed_discovery', adoption['helper_sessions_pct'])}`
- Discovery compliance pct (all): `{compliance['discovery_compliance_pct']}`
- Discovery compliance pct (observed): `{compliance.get('discovery_compliance_pct_observed', compliance['discovery_compliance_pct'])}`
- Broad scan violations: `{compliance['broad_scan_violations']}`
- Telemetry events (14d): `{telemetry['event_count']}`
- Helper error rate: `{efficiency.get('helper_error_rate_pct', 0.0)}%`
- Helper failure overhead: `{efficiency.get('failure_overhead_pct', 0.0)}%`
- Helper latency p50/p95: `{efficiency.get('helper_latency_p50_ms', 0.0)} / {efficiency.get('helper_latency_p95_ms', 0.0)} ms`
- Hook errors: `{efficiency.get('hook_error_count', 0)}`
- Pending state leaks: `{efficiency.get('pending_leak_count', 0)}`

## Logging Quality

- Logging quality score: `{logging.get('logging_quality_score', 0.0)}`
- Logging quality tier: `{logging.get('logging_quality_tier', 'no_data')}`
- Latency coverage: `{logging.get('helper_latency_coverage_pct', 0.0)}%`
- Exit-code coverage: `{logging.get('helper_exit_code_coverage_pct', 0.0)}%`
- Size coverage: `{logging.get('helper_size_coverage_pct', 0.0)}%`
- Backend coverage: `{logging.get('helper_backend_coverage_pct', 0.0)}%`
- Status/exit mismatches: `{logging.get('helper_status_exit_mismatch_count', 0)}`

## RTK

- Available: `{rtk.get('available', False)}`
- Gain command ok: `{rtk.get('gain', {}).get('ok', False)}`
- Discover command ok: `{rtk.get('discover', {}).get('ok', False)}`
- Session command ok: `{rtk.get('session', {}).get('ok', False)}`
- Hook audit command ok: `{rtk.get('hook_audit', {}).get('ok', False)}`
- RTK total commands: `{gain_summary.get('total_commands')}`
- RTK total saved: `{gain_summary.get('total_saved')}`
- RTK avg savings pct: `{gain_summary.get('avg_savings_pct')}`

## Dependency Overhead

- Estimated overhead events: `{dependency_overhead.get('estimated_overhead_events', 0)}`
- Helper rapid repeats: `{dependency_overhead.get('helper_rapid_repeat_calls', 0)}`
- Helper error-recovery retries: `{dependency_overhead.get('helper_error_recovery_retries', 0)}`
- Helper failure overhead calls: `{dependency_overhead.get('helper_failure_overhead_calls', 0)}`
- Helper error calls: `{dependency_overhead.get('helper_error_calls', 0)}`
- Hook errors: `{dependency_overhead.get('hook_error_count', 0)}`
- Pending state leaks: `{dependency_overhead.get('pending_leak_count', 0)}`
- RTK failed checks: `{dependency_overhead.get('rtk_failed_checks', 0)}`
- Healthy: `{dependency_overhead.get('healthy', False)}`

## Integration Health

- Codex skill installed: `{report['integration_status']['codex_skill']['exists']}`
- Token-reduce remind hooks: `{report['integration_status']['claude_hooks']['token_reduce_remind_count']}`
- Token-reduce enforce matchers: `{len(report['integration_status']['claude_hooks']['token_reduce_enforce_matchers'])}`
- RTK rewrite hooks: `{len(report['integration_status']['claude_hooks']['rtk_hook_commands'])}`
"""
    output_path.write_text(md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["repo", "global"], default="repo")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-md", required=False)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = composite(args.scope, repo_root)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if args.output_md:
        write_markdown(report, Path(args.output_md))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
