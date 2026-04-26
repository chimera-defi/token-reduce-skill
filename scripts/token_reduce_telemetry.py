#!/usr/bin/env python3
"""Repo-local telemetry for token-reduce helper and hook events."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

NON_RUNTIME_CONTEXTS = {"benchmark", "test", "synthetic"}


def default_repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    try:
        root = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return script_dir.parents[1]
    return Path(root)


def events_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "token-reduction" / "events.jsonl"


def record_event(
    repo_root: Path,
    *,
    event: str,
    source: str,
    tool: str | None = None,
    status: str = "ok",
    query: str | None = None,
    meta: dict | None = None,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "source": source,
        "status": status,
    }
    if tool:
        payload["tool"] = tool
    if query:
        payload["query"] = query
    if meta:
        payload["meta"] = meta

    path = events_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_events(repo_root: Path, *, days: int | None = None) -> list[dict]:
    path = events_path(repo_root)
    if not path.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff is not None:
            raw_ts = event.get("timestamp")
            if isinstance(raw_ts, str):
                try:
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = None
                if ts is not None and ts < cutoff:
                    continue
        events.append(event)
    return events


def event_timestamp(event: dict) -> datetime | None:
    raw_ts = event.get("timestamp")
    if not isinstance(raw_ts, str):
        return None
    try:
        return datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def event_context(event: dict) -> str:
    meta = event.get("meta")
    if isinstance(meta, dict):
        raw_context = meta.get("context")
        if isinstance(raw_context, str) and raw_context.strip():
            return raw_context.strip().lower()
    return "runtime"


def summarize_events(events: list[dict], *, include_non_runtime: bool = False) -> dict:
    def percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int(round((pct / 100.0) * (len(ordered) - 1)))
        return ordered[max(0, min(idx, len(ordered) - 1))]

    by_event = Counter()
    by_tool = Counter()
    by_status = Counter()
    by_context = Counter()
    tool_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "chars_total": 0, "lines_total": 0, "latency_total": 0.0}
    )
    helper_events: list[dict] = []
    helper_query_counts: Counter[tuple[str, str]] = Counter()
    hook_error_count = 0
    helper_latencies_ms: list[float] = []
    helper_tool_latencies_ms: dict[str, list[float]] = defaultdict(list)
    helper_backend_latencies_ms: dict[str, list[float]] = defaultdict(list)
    helper_backend_counts: Counter[str] = Counter()
    helper_meta_present_count = 0
    helper_latency_coverage_count = 0
    helper_size_coverage_count = 0
    helper_exit_code_coverage_count = 0
    helper_context_coverage_count = 0
    helper_backend_coverage_count = 0
    helper_status_exit_mismatch_count = 0
    helper_non_numeric_latency_count = 0
    helper_negative_latency_count = 0

    excluded_event_count = 0
    for event in events:
        context = event_context(event)
        by_context[context] += 1
        if not include_non_runtime and context in NON_RUNTIME_CONTEXTS:
            excluded_event_count += 1
            continue

        event_name = str(event.get("event", "unknown"))
        by_event[event_name] += 1
        if tool := event.get("tool"):
            by_tool[str(tool)] += 1
        by_status[str(event.get("status", "unknown"))] += 1

        meta = event.get("meta", {})
        if tool and isinstance(meta, dict):
            stats = tool_stats[str(tool)]
            stats["count"] += 1
            stats["chars_total"] += int(meta.get("chars", 0) or 0)
            stats["lines_total"] += int(meta.get("lines", 0) or 0)
            latency_ms = meta.get("latency_ms")
            if isinstance(latency_ms, (int, float)):
                latency_value = float(latency_ms)
                stats["latency_total"] += latency_value
                if event_name == "helper_invocation":
                    helper_latencies_ms.append(latency_value)
                    helper_tool_latencies_ms[str(tool)].append(latency_value)

        if event_name == "hook_error":
            hook_error_count += 1
        if event_name == "helper_invocation":
            helper_events.append(event)
            helper_query_counts[(str(event.get("tool", "unknown")), str(event.get("query", "")))] += 1

            status = str(event.get("status", "unknown"))
            if isinstance(meta, dict) and meta:
                helper_meta_present_count += 1

            if isinstance(meta, dict):
                raw_context = meta.get("context")
                if isinstance(raw_context, str) and raw_context.strip():
                    helper_context_coverage_count += 1

                raw_backend = meta.get("backend")
                backend = (
                    str(raw_backend).strip().lower()
                    if isinstance(raw_backend, str) and raw_backend.strip()
                    else "unknown"
                )
                helper_backend_counts[backend] += 1
                if backend != "unknown":
                    helper_backend_coverage_count += 1

                chars = meta.get("chars")
                lines = meta.get("lines")
                if isinstance(chars, (int, float)) and isinstance(lines, (int, float)):
                    helper_size_coverage_count += 1

                exit_code = meta.get("exit_code")
                if isinstance(exit_code, int):
                    helper_exit_code_coverage_count += 1
                    if (status == "ok" and exit_code != 0) or (status == "error" and exit_code == 0):
                        helper_status_exit_mismatch_count += 1

                latency_ms = meta.get("latency_ms")
                if isinstance(latency_ms, (int, float)):
                    if float(latency_ms) >= 0:
                        helper_latency_coverage_count += 1
                        helper_backend_latencies_ms[backend].append(float(latency_ms))
                    else:
                        helper_negative_latency_count += 1
                elif latency_ms is not None:
                    helper_non_numeric_latency_count += 1
            else:
                helper_backend_counts["unknown"] += 1

    helper_stats = {}
    for tool, stats in sorted(tool_stats.items()):
        count = int(stats["count"])
        helper_stats[tool] = {
            "count": count,
            "avg_chars": round(stats["chars_total"] / count, 1) if count else 0.0,
            "avg_lines": round(stats["lines_total"] / count, 1) if count else 0.0,
            "avg_latency_ms": round(stats["latency_total"] / count, 1) if count else 0.0,
        }

    helper_ok_calls = 0
    helper_error_calls = 0
    rapid_repeat_calls = 0
    error_recovery_retries = 0
    repeated_helper_calls = sum(max(0, count - 1) for count in helper_query_counts.values())
    last_call_by_key: dict[tuple[str, str], datetime] = {}
    last_error_by_key: dict[tuple[str, str], datetime] = {}
    sorted_helper_events = sorted(
        helper_events,
        key=lambda item: event_timestamp(item) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for event in sorted_helper_events:
        key = (str(event.get("tool", "unknown")), str(event.get("query", "")))
        status = str(event.get("status", "unknown"))
        ts = event_timestamp(event)
        if status == "error":
            helper_error_calls += 1
        else:
            helper_ok_calls += 1

        prev_ts = last_call_by_key.get(key)
        if ts is not None and prev_ts is not None:
            if (ts - prev_ts).total_seconds() <= 120:
                rapid_repeat_calls += 1
        if status != "error":
            prev_err = last_error_by_key.get(key)
            if ts is not None and prev_err is not None:
                if 0 < (ts - prev_err).total_seconds() <= 300:
                    error_recovery_retries += 1
                    last_error_by_key.pop(key, None)
        if status == "error" and ts is not None:
            last_error_by_key[key] = ts
        if ts is not None:
            last_call_by_key[key] = ts

    helper_calls = len(helper_events)
    pct = lambda count: round((count * 100.0 / helper_calls), 1) if helper_calls else 0.0

    helper_meta_present_pct = pct(helper_meta_present_count)
    helper_latency_coverage_pct = pct(helper_latency_coverage_count)
    helper_size_coverage_pct = pct(helper_size_coverage_count)
    helper_exit_code_coverage_pct = pct(helper_exit_code_coverage_count)
    helper_context_coverage_pct = pct(helper_context_coverage_count)
    helper_backend_coverage_pct = pct(helper_backend_coverage_count)
    helper_status_exit_mismatch_pct = pct(helper_status_exit_mismatch_count)
    helper_missing_latency_count = max(0, helper_calls - helper_latency_coverage_count)

    helper_error_rate_pct = round((helper_error_calls * 100.0 / helper_calls), 1) if helper_calls else 0.0
    failure_overhead_calls = helper_error_calls + error_recovery_retries
    failure_overhead_pct = round((failure_overhead_calls * 100.0 / helper_calls), 1) if helper_calls else 0.0
    helper_latency_avg_ms = round(sum(helper_latencies_ms) / len(helper_latencies_ms), 1) if helper_latencies_ms else 0.0
    helper_latency_p50_ms = round(percentile(helper_latencies_ms, 50), 1) if helper_latencies_ms else 0.0
    helper_latency_p90_ms = round(percentile(helper_latencies_ms, 90), 1) if helper_latencies_ms else 0.0
    helper_latency_p95_ms = round(percentile(helper_latencies_ms, 95), 1) if helper_latencies_ms else 0.0
    helper_latency_max_ms = round(max(helper_latencies_ms), 1) if helper_latencies_ms else 0.0
    latency_by_tool = {
        tool: {
            "avg_ms": round(sum(values) / len(values), 1),
            "p95_ms": round(percentile(values, 95), 1),
        }
        for tool, values in sorted(helper_tool_latencies_ms.items())
        if values
    }
    latency_by_backend = {
        backend: {
            "avg_ms": round(sum(values) / len(values), 1),
            "p95_ms": round(percentile(values, 95), 1),
        }
        for backend, values in sorted(helper_backend_latencies_ms.items())
        if values
    }

    logging_quality_score = round(
        (
            helper_latency_coverage_pct * 0.4
            + helper_exit_code_coverage_pct * 0.2
            + helper_size_coverage_pct * 0.2
            + helper_context_coverage_pct * 0.1
            + helper_backend_coverage_pct * 0.1
        ),
        1,
    )
    if helper_calls == 0:
        logging_quality_tier = "no_data"
    elif logging_quality_score >= 90.0 and helper_status_exit_mismatch_count == 0:
        logging_quality_tier = "high"
    elif logging_quality_score >= 75.0:
        logging_quality_tier = "medium"
    else:
        logging_quality_tier = "low"
    pending_marked = int(by_event.get("pending_marked", 0))
    pending_cleared = int(by_event.get("pending_cleared", 0))
    pending_balance = pending_marked - pending_cleared
    pending_leak_count = pending_balance if pending_balance > 0 else 0

    return {
        "event_count": len(events) - excluded_event_count,
        "total_event_count": len(events),
        "excluded_event_count": excluded_event_count,
        "excluded_contexts": sorted(NON_RUNTIME_CONTEXTS),
        "context_breakdown": dict(sorted(by_context.items())),
        "by_event": dict(sorted(by_event.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "by_status": dict(sorted(by_status.items())),
        "tool_stats": helper_stats,
        "logging": {
            "helper_meta_present_pct": helper_meta_present_pct,
            "helper_latency_coverage_pct": helper_latency_coverage_pct,
            "helper_size_coverage_pct": helper_size_coverage_pct,
            "helper_exit_code_coverage_pct": helper_exit_code_coverage_pct,
            "helper_context_coverage_pct": helper_context_coverage_pct,
            "helper_backend_coverage_pct": helper_backend_coverage_pct,
            "helper_missing_latency_count": helper_missing_latency_count,
            "helper_non_numeric_latency_count": helper_non_numeric_latency_count,
            "helper_negative_latency_count": helper_negative_latency_count,
            "helper_status_exit_mismatch_count": helper_status_exit_mismatch_count,
            "helper_status_exit_mismatch_pct": helper_status_exit_mismatch_pct,
            "helper_backend_breakdown": dict(sorted(helper_backend_counts.items())),
            "helper_latency_by_backend": latency_by_backend,
            "logging_quality_score": logging_quality_score,
            "logging_quality_tier": logging_quality_tier,
        },
        "efficiency": {
            "helper_calls": helper_calls,
            "helper_ok_calls": helper_ok_calls,
            "helper_error_calls": helper_error_calls,
            "helper_error_rate_pct": helper_error_rate_pct,
            "unique_helper_queries": len(helper_query_counts),
            "repeated_helper_calls": repeated_helper_calls,
            "rapid_repeat_calls": rapid_repeat_calls,
            "error_recovery_retries": error_recovery_retries,
            "failure_overhead_calls": failure_overhead_calls,
            "failure_overhead_pct": failure_overhead_pct,
            "retry_overhead_pct": failure_overhead_pct,
            "helper_latency_avg_ms": helper_latency_avg_ms,
            "helper_latency_p50_ms": helper_latency_p50_ms,
            "helper_latency_p90_ms": helper_latency_p90_ms,
            "helper_latency_p95_ms": helper_latency_p95_ms,
            "helper_latency_max_ms": helper_latency_max_ms,
            "helper_latency_by_tool": latency_by_tool,
            "helper_latency_coverage_pct": helper_latency_coverage_pct,
            "helper_size_coverage_pct": helper_size_coverage_pct,
            "helper_exit_code_coverage_pct": helper_exit_code_coverage_pct,
            "helper_backend_coverage_pct": helper_backend_coverage_pct,
            "helper_status_exit_mismatch_count": helper_status_exit_mismatch_count,
            "helper_status_exit_mismatch_pct": helper_status_exit_mismatch_pct,
            "logging_quality_score": logging_quality_score,
            "logging_quality_tier": logging_quality_tier,
            "hook_error_count": hook_error_count,
            "pending_marked": pending_marked,
            "pending_cleared": pending_cleared,
            "pending_leak_count": pending_leak_count,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    subparsers = parser.add_subparsers(dest="command", required=True)

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--event", required=True)
    log_parser.add_argument("--source", required=True)
    log_parser.add_argument("--tool")
    log_parser.add_argument("--status", default="ok")
    log_parser.add_argument("--query")
    log_parser.add_argument("--meta-json")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--days", type=int, default=14)
    summary_parser.add_argument(
        "--include-non-runtime",
        action="store_true",
        help="Include benchmark/test/synthetic events in summary totals.",
    )

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    if args.command == "log":
        meta = None
        if args.meta_json:
            try:
                meta = json.loads(args.meta_json)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid --meta-json: {exc}")
        record_event(
            repo_root,
            event=args.event,
            source=args.source,
            tool=args.tool,
            status=args.status,
            query=args.query,
            meta=meta,
        )
        return 0

    if args.command == "summary":
        print(
            json.dumps(
                summarize_events(
                    load_events(repo_root, days=args.days),
                    include_non_runtime=args.include_non_runtime,
                ),
                indent=2,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
