#!/usr/bin/env python3
"""Summarize a running Cost Caliper Control Tower for token-reduce review."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from typing import Any


DEFAULT_CALIPER_URL = "http://127.0.0.1:49123"
DEFAULT_AGGREGATE_BUDGET_MS = 4000
DEFAULT_AGGREGATE_MAX_POLLS = 50


class CaliperUnavailable(RuntimeError):
    """Raised when the local Caliper API cannot be reached."""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except (OSError, urllib.error.URLError) as exc:
        raise CaliperUnavailable(f"could not reach Caliper API at {url}: {exc}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CaliperUnavailable(f"Caliper API returned non-JSON payload at {url}") from exc
    if not isinstance(data, dict):
        raise CaliperUnavailable(f"Caliper API returned unexpected payload at {url}")
    return data


def _aggregate_url(base_url: str, *, restart: bool, budget_ms: int) -> str:
    params: dict[str, str] = {"budgetMs": str(budget_ms)}
    if restart:
        params["restart"] = "1"
    return f"{base_url.rstrip('/')}/v1/aggregate?{urlencode(params)}"


def fetch_complete_aggregate(
    base_url: str,
    *,
    timeout: float = 2.0,
    budget_ms: int = DEFAULT_AGGREGATE_BUDGET_MS,
    max_polls: int = DEFAULT_AGGREGATE_MAX_POLLS,
) -> dict[str, Any]:
    """Fetch Caliper aggregate data, polling until the incremental scan is done."""
    polls = 0
    aggregate: dict[str, Any] = {}
    for poll_index in range(max(1, max_polls)):
        polls += 1
        aggregate = _fetch_json(
            _aggregate_url(base_url, restart=poll_index == 0, budget_ms=budget_ms),
            timeout,
        )
        if aggregate.get("done", True):
            break
    aggregate["_token_reduce_polls"] = polls
    aggregate["_token_reduce_complete"] = bool(aggregate.get("done", True))
    return aggregate


def fetch_caliper_payload(
    base_url: str,
    timeout: float = 2.0,
    budget_ms: int = DEFAULT_AGGREGATE_BUDGET_MS,
    max_polls: int = DEFAULT_AGGREGATE_MAX_POLLS,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "health": _fetch_json(f"{base}/v1/health", timeout),
        "aggregate": fetch_complete_aggregate(
            base,
            timeout=timeout,
            budget_ms=budget_ms,
            max_polls=max_polls,
        ),
    }


def _normalize_named_rows(rows: Any, name_key: str = "name", cost_key: str = "costUsd") -> list[dict[str, Any]]:
    if isinstance(rows, dict):
        iterable = []
        for key, value in rows.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault(name_key, key)
            else:
                item = {name_key: key, cost_key: value}
            iterable.append(item)
    elif isinstance(rows, list):
        iterable = [item for item in rows if isinstance(item, dict)]
    else:
        iterable = []

    normalized: list[dict[str, Any]] = []
    for item in iterable:
        name = str(
            item.get(name_key)
            or item.get("repo")
            or item.get("tier")
            or item.get("model")
            or item.get("folder")
            or "unknown"
        )
        normalized.append(
            {
                "name": name,
                "cost_usd": round(_float(item.get(cost_key, item.get("cost", item.get("usd")))), 6),
                "sessions": _int(item.get("sessions", item.get("sessionCount", 0))),
                "input_tokens": _int(item.get("inputTokens", item.get("input", 0))),
                "output_tokens": _int(item.get("outputTokens", item.get("output", 0))),
            }
        )
    return sorted(normalized, key=lambda item: item["cost_usd"], reverse=True)


def normalize_caliper_summary(payload: dict[str, Any], source_url: str) -> dict[str, Any]:
    aggregate = payload.get("aggregate", {})
    health = payload.get("health", {})
    totals = aggregate.get("totals", {}) if isinstance(aggregate.get("totals"), dict) else {}
    token_bucket = totals.get("tokens", {}) if isinstance(totals.get("tokens"), dict) else {}

    by_repo = _normalize_named_rows(aggregate.get("byRepo"), "repo")
    by_tier = _normalize_named_rows(aggregate.get("byTier"), "tier")
    by_day = _normalize_named_rows(aggregate.get("byDay"), "day")

    cache_write_tokens = _int(
        token_bucket.get(
            "cacheWr",
            totals.get("cacheCreationInputTokens", totals.get("cacheWriteTokens", totals.get("cache_write_tokens", 0))),
        )
    )
    cache_read_tokens = _int(
        token_bucket.get("cacheRd", totals.get("cacheReadInputTokens", totals.get("cacheReadTokens", 0)))
    )
    input_tokens = _int(token_bucket.get("in", totals.get("inputTokens", totals.get("input_tokens", 0))))
    output_tokens = _int(token_bucket.get("out", totals.get("outputTokens", totals.get("output_tokens", 0))))
    token_total = max(1, input_tokens + output_tokens + cache_write_tokens + cache_read_tokens)

    return {
        "source": "cost-caliper",
        "source_url": source_url.rstrip("/"),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "api_health": {
            "ok": bool(health.get("ok", health.get("status") == "ok")),
            "version": str(health.get("version", health.get("lensVersion", "unknown"))),
            "workflow_count": _int(health.get("workflowCount", health.get("workflows", 0))),
            "cassette_count": _int(health.get("cassetteCount", health.get("cassettes", 0))),
        },
        "aggregate": {
            "complete": bool(aggregate.get("_token_reduce_complete", aggregate.get("done", True))),
            "polls": _int(aggregate.get("_token_reduce_polls", 1), 1),
            "progress": aggregate.get("progress") if isinstance(aggregate.get("progress"), dict) else {},
        },
        "summary": {
            "estimated_cost_usd": round(_float(totals.get("costUsd", totals.get("cost_usd"))), 6),
            "sessions": _int(totals.get("sessions", totals.get("sessionCount", 0))),
            "folders": _int(totals.get("folders", totals.get("repoCount", 0))),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_token_pct": round(cache_write_tokens * 100.0 / token_total, 1),
            "cache_read_token_pct": round(cache_read_tokens * 100.0 / token_total, 1),
        },
        "by_repo": by_repo[:10],
        "by_tier": by_tier[:10],
        "by_day": by_day[:14],
        "raw_keys": sorted(aggregate.keys()),
    }


def fetch_summary(
    base_url: str | None = None,
    timeout: float = 2.0,
    budget_ms: int = DEFAULT_AGGREGATE_BUDGET_MS,
    max_polls: int = DEFAULT_AGGREGATE_MAX_POLLS,
) -> dict[str, Any]:
    source_url = base_url or os.environ.get("CALIPER_URL") or DEFAULT_CALIPER_URL
    return normalize_caliper_summary(
        fetch_caliper_payload(source_url, timeout, budget_ms, max_polls),
        source_url,
    )


def build_spend_findings(summary: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    data = summary.get("summary", {})
    aggregate = summary.get("aggregate", {}) if isinstance(summary.get("aggregate"), dict) else {}
    estimated_cost = _float(data.get("estimated_cost_usd"))
    sessions = _int(data.get("sessions"))
    cache_write_pct = _float(data.get("cache_write_token_pct"))
    cache_read_pct = _float(data.get("cache_read_token_pct"))
    by_tier = summary.get("by_tier", [])
    by_repo = summary.get("by_repo", [])

    if aggregate and not aggregate.get("complete", True):
        findings.append(
            {
                "priority": "high",
                "area": "caliper_aggregate_incomplete",
                "finding": (
                    f"Caliper aggregate did not finish after {_int(aggregate.get('polls'), 0)} poll(s); "
                    "spend totals and hotspot findings may be partial."
                ),
                "recommendation": "Rerun with a larger `--max-polls` or verify the Caliper Control Tower scan can complete before using spend data for routing decisions.",
            }
        )

    if sessions > 0 and estimated_cost > 0:
        avg_cost = estimated_cost / sessions
        if avg_cost >= 5.0:
            findings.append(
                {
                    "priority": "high",
                    "area": "caliper_spend",
                    "finding": f"Caliper estimates high average session spend at ${avg_cost:.2f}/session.",
                    "recommendation": "Review the top expensive sessions in Caliper, then apply token-reduce helper-first discovery, Headroom for large payload pressure, and delegated batch reviews where the main session is doing broad exploration.",
                }
            )

    expensive_tiers = [
        item for item in by_tier
        if item.get("name", "").lower() in {"opus", "fable"} and _float(item.get("cost_usd")) > 0
    ]
    if expensive_tiers:
        tier_text = ", ".join(f"{item['name']}=${item['cost_usd']:.2f}" for item in expensive_tiers[:3])
        findings.append(
            {
                "priority": "medium",
                "area": "caliper_model_mix",
                "finding": f"Caliper shows spend on expensive model tiers ({tier_text}).",
                "recommendation": "Use expensive tiers for synthesis/review, but keep discovery on token-reduce helpers, scoped reads, and cheap delegate batches before escalating model quality.",
            }
        )

    if cache_write_pct >= 25.0 and cache_read_pct < cache_write_pct * 0.5:
        findings.append(
            {
                "priority": "medium",
                "area": "caliper_cache_economics",
                "finding": f"Cache writes are high ({cache_write_pct:.1f}% of token volume) while cache reads are lower ({cache_read_pct:.1f}%).",
                "recommendation": "Reduce churn in always-loaded guidance and repeated large payloads; prefer stable AGENTS/CLAUDE blocks plus Headroom/context tools for oversized outputs.",
            }
        )

    if by_repo:
        top_repo = by_repo[0]
        if _float(top_repo.get("cost_usd")) >= max(10.0, estimated_cost * 0.4):
            findings.append(
                {
                    "priority": "medium",
                    "area": "caliper_repo_hotspot",
                    "finding": f"Caliper identifies `{top_repo['name']}` as the top spend hotspot at ${top_repo['cost_usd']:.2f}.",
                    "recommendation": "Run token-reduce review for that repo and update its local agent guidance where broad discovery, low Headroom use, or missing delegation is driving cost.",
                }
            )

    return findings


def render_markdown(summary: dict[str, Any]) -> str:
    data = summary.get("summary", {})
    lines = [
        "# Caliper Spend Summary",
        "",
        f"- Source: `{summary.get('source_url', '')}`",
        f"- API health: `{summary.get('api_health', {}).get('ok', False)}`",
        f"- Aggregate complete: `{summary.get('aggregate', {}).get('complete', False)}` after `{_int(summary.get('aggregate', {}).get('polls'), 0)}` poll(s)",
        f"- Estimated cost: `${_float(data.get('estimated_cost_usd')):.4f}`",
        f"- Sessions: `{_int(data.get('sessions'))}`",
        f"- Repos/folders: `{_int(data.get('folders'))}`",
        f"- Input/output tokens: `{_int(data.get('input_tokens'))}` / `{_int(data.get('output_tokens'))}`",
        f"- Cache write/read tokens: `{_int(data.get('cache_write_tokens'))}` / `{_int(data.get('cache_read_tokens'))}`",
        f"- Cache write/read token share: `{_float(data.get('cache_write_token_pct')):.1f}%` / `{_float(data.get('cache_read_token_pct')):.1f}%`",
        "",
        "## Spend-Aware Findings",
        "",
    ]
    findings = build_spend_findings(summary)
    if findings:
        for finding in findings:
            lines.append(f"- **{finding['priority'].upper()} · {finding['area']}**: {finding['finding']}")
            lines.append(f"  Recommendation: {finding['recommendation']}")
    else:
        lines.append("- No Caliper spend findings crossed the default thresholds.")

    lines.extend(["", "## Top Repos", ""])
    for item in summary.get("by_repo", [])[:5]:
        lines.append(f"- `{item['name']}`: ${_float(item.get('cost_usd')):.4f} across `{_int(item.get('sessions'))}` sessions")

    lines.extend(["", "## Model Tiers", ""])
    for item in summary.get("by_tier", [])[:5]:
        lines.append(f"- `{item['name']}`: ${_float(item.get('cost_usd')):.4f}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("CALIPER_URL", DEFAULT_CALIPER_URL))
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--budget-ms", type=int, default=DEFAULT_AGGREGATE_BUDGET_MS)
    parser.add_argument("--max-polls", type=int, default=DEFAULT_AGGREGATE_MAX_POLLS)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        summary = fetch_summary(args.url, args.timeout, args.budget_ms, args.max_polls)
    except CaliperUnavailable as exc:
        print(f"Caliper unavailable: {exc}", file=sys.stderr)
        return 2

    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, indent=2) + "\n")
    markdown = render_markdown(summary)
    if args.output_md:
        output_md = Path(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(markdown)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
