from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_telemetry import summarize_events


def test_headroom_recommendations_are_counted_from_adaptive_telemetry() -> None:
    summary = summarize_events(
        [
            {
                "event": "helper_invocation",
                "source": "helper",
                "tool": "token_reduce_adaptive",
                "status": "ok",
                "query": "large tool_result payload",
                "meta": {
                    "context": "runtime",
                    "backend": "adaptive",
                    "latency_ms": 10,
                    "chars": 10,
                    "lines": 1,
                    "exit_code": 0,
                    "headroom_recommended": True,
                },
            }
        ]
    )

    assert summary["companion_recommendations"]["headroom_recommended_events"] == 1
