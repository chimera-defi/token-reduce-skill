from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import caliper_summary


def test_fetch_complete_aggregate_restarts_and_polls_until_done(monkeypatch) -> None:
    urls: list[str] = []
    responses = [
        {"done": False, "progress": {"scannedSessions": 1, "totalSessions": 2}, "totals": {"sessions": 1}},
        {"done": True, "progress": {"scannedSessions": 2, "totalSessions": 2}, "totals": {"sessions": 2}},
    ]

    def fake_fetch(url: str, timeout: float) -> dict:
        urls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(caliper_summary, "_fetch_json", fake_fetch)

    aggregate = caliper_summary.fetch_complete_aggregate(
        "http://127.0.0.1:49123",
        timeout=0.1,
        budget_ms=4000,
        max_polls=5,
    )

    assert aggregate["done"] is True
    assert aggregate["_token_reduce_complete"] is True
    assert aggregate["_token_reduce_polls"] == 2
    assert urls[0].endswith("/v1/aggregate?budgetMs=4000&restart=1")
    assert urls[1].endswith("/v1/aggregate?budgetMs=4000")


def test_normalize_reads_current_caliper_nested_token_buckets() -> None:
    summary = caliper_summary.normalize_caliper_summary(
        {
            "health": {"ok": True, "lensVersion": "0.1.0"},
            "aggregate": {
                "done": True,
                "_token_reduce_polls": 3,
                "_token_reduce_complete": True,
                "progress": {"scannedSessions": 4, "totalSessions": 4},
                "totals": {
                    "sessions": 4,
                    "folders": 2,
                    "costUsd": 12.5,
                    "tokens": {"in": 100, "out": 25, "cacheWr": 50, "cacheRd": 10},
                },
                "byRepo": [{"repo": "token-reduce-skill", "costUsd": 12.5, "sessions": 4}],
                "byTier": [{"tier": "opus", "costUsd": 9.0}, {"tier": "sonnet", "costUsd": 3.5}],
                "byDay": [{"day": "2026-07-05", "costUsd": 12.5, "sessions": 4}],
            },
        },
        "http://127.0.0.1:49123",
    )

    assert summary["aggregate"]["complete"] is True
    assert summary["aggregate"]["polls"] == 3
    assert summary["summary"]["input_tokens"] == 100
    assert summary["summary"]["output_tokens"] == 25
    assert summary["summary"]["cache_write_tokens"] == 50
    assert summary["summary"]["cache_read_tokens"] == 10
    assert summary["summary"]["cache_write_token_pct"] == 27.0
    assert summary["summary"]["cache_read_token_pct"] == 5.4


def test_spend_findings_warn_when_aggregate_is_incomplete() -> None:
    findings = caliper_summary.build_spend_findings(
        {
            "aggregate": {"complete": False, "polls": 1},
            "summary": {"estimated_cost_usd": 1.0, "sessions": 1},
            "by_tier": [],
            "by_repo": [],
        }
    )

    assert findings[0]["area"] == "caliper_aggregate_incomplete"
