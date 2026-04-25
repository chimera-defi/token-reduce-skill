from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from composite_token_telemetry import realized_outcomes_summary
from token_reduce_telemetry import summarize_events


def _helper_event(*, status: str, latency_ms: int, exit_code: int, backend: str = "qmd") -> dict:
    return {
        "timestamp": "2026-04-25T00:00:00+00:00",
        "event": "helper_invocation",
        "source": "helper",
        "tool": "token_reduce_paths",
        "status": status,
        "query": "hook enforcement",
        "meta": {
            "context": "runtime",
            "backend": backend,
            "lines": 4,
            "chars": 120,
            "latency_ms": latency_ms,
            "exit_code": exit_code,
        },
    }


def test_summarize_events_reports_high_logging_coverage() -> None:
    summary = summarize_events(
        [
            _helper_event(status="ok", latency_ms=120, exit_code=0, backend="qmd_files"),
            _helper_event(status="ok", latency_ms=180, exit_code=0, backend="qmd_files"),
        ]
    )
    logging = summary["logging"]
    assert logging["helper_latency_coverage_pct"] == 100.0
    assert logging["helper_exit_code_coverage_pct"] == 100.0
    assert logging["helper_backend_coverage_pct"] == 100.0
    assert logging["logging_quality_tier"] == "high"


def test_summarize_events_detects_status_exit_mismatch() -> None:
    summary = summarize_events(
        [
            _helper_event(status="ok", latency_ms=120, exit_code=1, backend="qmd_files"),
            _helper_event(status="error", latency_ms=300, exit_code=2, backend="rg_qmd_error_fallback"),
        ]
    )
    logging = summary["logging"]
    assert logging["helper_status_exit_mismatch_count"] == 1
    assert summary["efficiency"]["helper_status_exit_mismatch_count"] == 1


def test_realized_outcomes_discount_potential_by_runtime_factors() -> None:
    token_reduce = {
        "session_count": 8,
        "adoption": {
            "helper_sessions_pct": 55.0,
            "helper_sessions_pct_observed_discovery": 50.0,
        },
        "compliance": {
            "discovery_compliance_pct": 60.0,
            "discovery_compliance_pct_observed": 50.0,
            "sessions_with_first_discovery_observed": 6,
        },
        "telemetry": {
            "event_count": 14,
            "efficiency": {
                "helper_calls": 20,
                "helper_error_rate_pct": 5.0,
                "failure_overhead_pct": 10.0,
                "helper_latency_p95_ms": 9000.0,
            },
            "logging": {
                "logging_quality_score": 82.0,
                "logging_quality_tier": "medium",
            },
        },
    }
    benchmark = {
        "available": True,
        "quality_pass": True,
        "potential_savings_pct": 86.6,
    }

    realized = realized_outcomes_summary(token_reduce, benchmark, dependency_overhead={})
    assert realized["realized_savings_estimate_pct"] < benchmark["potential_savings_pct"]
    assert realized["realized_savings_conservative_pct"] <= realized["realized_savings_estimate_pct"]
    assert "low_confidence_sample" in realized["honesty"]["flags"]
