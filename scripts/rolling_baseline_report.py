#!/usr/bin/env python3
"""Build a rolling pre/post baseline report from telemetry snapshot history."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    paths: tuple[tuple[str, ...], ...]


METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="helper_sessions_pct",
        label="Helper Usage % (all sessions)",
        paths=(("global_measure_summary", "helper_sessions_pct"), ("remote_payload", "metrics", "helper_sessions_pct")),
    ),
    MetricSpec(
        key="helper_sessions_pct_observed_discovery",
        label="Helper Usage % (observed discovery sessions)",
        paths=(
            ("global_measure_summary", "helper_sessions_pct_observed_discovery"),
            ("remote_payload", "metrics", "helper_sessions_pct_observed_discovery"),
        ),
    ),
    MetricSpec(
        key="discovery_compliance_pct",
        label="Discovery Compliance % (all sessions)",
        paths=(("global_measure_summary", "discovery_compliance_pct"), ("remote_payload", "metrics", "discovery_compliance_pct")),
    ),
    MetricSpec(
        key="discovery_compliance_pct_observed",
        label="Discovery Compliance % (observed discovery sessions)",
        paths=(
            ("global_measure_summary", "discovery_compliance_pct_observed"),
            ("remote_payload", "metrics", "discovery_compliance_pct_observed"),
        ),
    ),
    MetricSpec(
        key="workspace_active_repos_with_helper_usage_pct",
        label="Workspace Active Repos With Helper Usage %",
        paths=(("remote_payload", "metrics", "workspace", "active_repos_with_helper_usage_pct"),),
    ),
    MetricSpec(
        key="helper_failure_overhead_pct",
        label="Helper Failure Overhead %",
        paths=(("remote_payload", "metrics", "helper_failure_overhead_pct"),),
    ),
    MetricSpec(
        key="helper_latency_p95_ms",
        label="Helper Latency P95 (ms)",
        paths=(("remote_payload", "metrics", "helper_latency_p95_ms"),),
    ),
    MetricSpec(
        key="logging_quality_score",
        label="Logging Quality Score",
        paths=(("remote_payload", "metrics", "logging_quality_score"),),
    ),
    MetricSpec(
        key="helper_latency_p95_ms_1d",
        label="Helper Latency P95 (1d window, ms)",
        paths=(("remote_payload", "metrics", "helper_latency_p95_ms_1d"),),
    ),
    MetricSpec(
        key="logging_quality_score_1d",
        label="Logging Quality Score (1d window)",
        paths=(("remote_payload", "metrics", "logging_quality_score_1d"),),
    ),
)


def parse_timestamp(raw: str | None) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def deep_get(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def first_number(payload: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> float | None:
    for path in paths:
        value = deep_get(payload, path)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_timestamp(payload.get("timestamp"))
        if ts is None:
            continue
        payload["_parsed_timestamp"] = ts
        rows.append(payload)
    rows.sort(key=lambda item: item["_parsed_timestamp"])
    return rows


def window_split(rows: list[dict[str, Any]], window_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 2:
        return [], []
    if len(rows) >= window_size * 2:
        recent = rows[-(window_size * 2) :]
        return recent[:window_size], recent[window_size:]
    half = len(rows) // 2
    return rows[:half], rows[half:]


def average(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def metric_stats(rows: list[dict[str, Any]], spec: MetricSpec) -> tuple[float, int]:
    values = [first_number(row, spec.paths) for row in rows]
    filtered = [value for value in values if value is not None]
    return average(filtered), len(filtered)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Rolling Baseline Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source file: `{report['source_file']}`",
        f"- Total snapshots: `{report['snapshot_count']}`",
        f"- Pre window size: `{report['windows']['pre']['count']}`",
        f"- Post window size: `{report['windows']['post']['count']}`",
        "",
        "| Metric | Pre Avg | Post Avg | Delta |",
        "|--------|---------|----------|-------|",
    ]
    for row in report["metrics"]:
        lines.append(
            f"| {row['label']} | `{row['pre_avg']}` | `{row['post_avg']}` | `{row['delta']}` |"
        )
    return "\n".join(lines) + "\n"


def build_report(rows: list[dict[str, Any]], window_size: int, source_file: Path) -> dict[str, Any]:
    pre, post = window_split(rows, window_size)
    metrics_payload: list[dict[str, Any]] = []
    for spec in METRICS:
        pre_avg, pre_points = metric_stats(pre, spec)
        post_avg, post_points = metric_stats(post, spec)
        metrics_payload.append(
            {
                "key": spec.key,
                "label": spec.label,
                "pre_avg": pre_avg,
                "post_avg": post_avg,
                "delta": round(post_avg - pre_avg, 2),
                "pre_points": pre_points,
                "post_points": post_points,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source_file),
        "snapshot_count": len(rows),
        "windows": {
            "pre": {
                "count": len(pre),
                "start": pre[0]["_parsed_timestamp"].isoformat() if pre else None,
                "end": pre[-1]["_parsed_timestamp"].isoformat() if pre else None,
            },
            "post": {
                "count": len(post),
                "start": post[0]["_parsed_timestamp"].isoformat() if post else None,
                "end": post[-1]["_parsed_timestamp"].isoformat() if post else None,
            },
        },
        "metrics": metrics_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=str(Path(__file__).resolve().parents[1] / "artifacts" / "token-reduction" / "telemetry-optin.jsonl"),
    )
    parser.add_argument("--window-size", type=int, default=5)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    rows = load_rows(source)
    report = build_report(rows, max(1, args.window_size), source)
    markdown = render_markdown(report)

    if args.output_json:
        out = Path(args.output_json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        out = Path(args.output_md).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
