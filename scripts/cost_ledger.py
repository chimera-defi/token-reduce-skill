"""Track F — Cost ledger.

Translates session metrics (from ``measure_token_reduction``) into rough
token-cost estimates using the coefficients in
``references/benchmarks/local-benchmark.json``:

- ``broad_inventory`` -> 1028 tokens per broad-scan session
- ``token_reduce_paths_warm`` -> 245 tokens per helper-used session

Numbers are deliberately coarse — the value is the *direction* (helper
sessions save tokens, broad-scan sessions spend them) more than the
exact magnitude.
"""
from __future__ import annotations

from collections import defaultdict


# Pulled from references/benchmarks/local-benchmark.json (broad_inventory
# tokens and token_reduce_paths_warm tokens, rounded for stability).
BENCHMARK_BROAD_TOKENS = 1028
BENCHMARK_HELPER_TOKENS = 245
BENCHMARK_SAVINGS_PER_HELPER = BENCHMARK_BROAD_TOKENS - BENCHMARK_HELPER_TOKENS


def _is_helper(metrics: dict) -> bool:
    return bool(
        metrics.get("qmd_search")
        or metrics.get("token_reduce_search")
        or metrics.get("scoped_rg")
        or metrics.get("structural_helper")
    )


def estimate_session_cost(metrics: dict) -> dict:
    """Estimate tokens saved/spent for one session.

    Returns a dict with ``session_kind`` (helper/broad/mixed/none),
    ``estimated_tokens_saved`` (positive when helper avoided a broad
    scan), and ``estimated_tokens_spent_on_broad`` (positive when the
    session ran a broad scan anyway).
    """
    helper = _is_helper(metrics)
    broad = bool(metrics.get("broad_scan_violation"))

    if helper and broad:
        kind = "mixed"
        # Helper still ran, but broad scan also paid full cost — no net save.
        saved = 0
        spent = BENCHMARK_BROAD_TOKENS
    elif helper:
        kind = "helper"
        saved = BENCHMARK_SAVINGS_PER_HELPER
        spent = 0
    elif broad:
        kind = "broad"
        saved = 0
        spent = BENCHMARK_BROAD_TOKENS
    else:
        kind = "none"
        saved = 0
        spent = 0

    return {
        "session_kind": kind,
        "estimated_tokens_saved": int(saved),
        "estimated_tokens_spent_on_broad": int(spent),
    }


def aggregate_by_source(items: list[dict]) -> dict[str, dict]:
    """Roll up cost estimates per source (claude/codex/...).

    Each per-source bucket includes session counts by kind, avg helper
    and broad token spend, and totals for the saved/spent columns.
    """
    by_source: dict[str, dict] = defaultdict(lambda: {
        "sessions": 0,
        "helper_sessions": 0,
        "broad_sessions": 0,
        "mixed_sessions": 0,
        "none_sessions": 0,
        "total_estimated_tokens_saved": 0,
        "total_estimated_tokens_spent_on_broad": 0,
    })
    for item in items:
        cost = estimate_session_cost(item)
        kind = cost["session_kind"]
        src = str(item.get("source") or "unknown")
        bucket = by_source[src]
        bucket["sessions"] += 1
        bucket[f"{kind}_sessions"] += 1
        bucket["total_estimated_tokens_saved"] += cost["estimated_tokens_saved"]
        bucket["total_estimated_tokens_spent_on_broad"] += cost["estimated_tokens_spent_on_broad"]

    for bucket in by_source.values():
        helper_n = bucket["helper_sessions"] + bucket["mixed_sessions"]
        broad_n = bucket["broad_sessions"] + bucket["mixed_sessions"]
        # These are *benchmark* constants applied per session — we don't have
        # per-session token measurements yet, so labelling them "avg" was
        # misleading. Keep the legacy keys as aliases for back-compat with
        # any callers that already read them, but the canonical fields are
        # the ``benchmark_*`` ones.
        bench_helper = round(BENCHMARK_HELPER_TOKENS * 1.0, 1) if helper_n else 0.0
        bench_broad = round(BENCHMARK_BROAD_TOKENS * 1.0, 1) if broad_n else 0.0
        bucket["benchmark_helper_tokens"] = bench_helper
        bucket["benchmark_broad_tokens"] = bench_broad
        # Back-compat aliases (will be removed once review/markdown migrates).
        bucket["avg_helper_tokens"] = bench_helper
        bucket["avg_broad_tokens"] = bench_broad
    return dict(by_source)


def build_context_impact_markdown(items: list[dict]) -> str:
    """Render the per-source 'Context Impact' review section."""
    agg = aggregate_by_source(items)
    if not agg:
        return "## Context Impact\n\n_No sessions to summarize._\n"
    lines = [
        "## Context Impact",
        "",
        "Estimated tokens saved vs. spent per source, using coefficients from",
        "`references/benchmarks/local-benchmark.json` "
        f"(broad={BENCHMARK_BROAD_TOKENS}, helper={BENCHMARK_HELPER_TOKENS}).",
        "",
        "| Source | Sessions | Helper | Broad | Mixed | Benchmark helper tokens | Benchmark broad tokens | Tokens saved | Tokens spent on broad |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for source in sorted(agg.keys()):
        b = agg[source]
        lines.append(
            f"| {source} | {b['sessions']} | {b['helper_sessions']} | {b['broad_sessions']} | "
            f"{b['mixed_sessions']} | {b['benchmark_helper_tokens']} | {b['benchmark_broad_tokens']} | "
            f"{b['total_estimated_tokens_saved']} | {b['total_estimated_tokens_spent_on_broad']} |"
        )
    return "\n".join(lines) + "\n"
