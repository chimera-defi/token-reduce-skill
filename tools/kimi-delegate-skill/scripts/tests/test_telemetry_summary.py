#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import importlib.util


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("telemetry_mod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_summary_shape() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = load_module(root / "scripts" / "kimi_delegate_telemetry.py")
    data = mod.summarize(
        [
            {
                "event": "delegate_invocation",
                "status": "ok",
                "task_class": "summarize",
                "model_used": "k2p6",
                "estimated_tokens_saved": 100,
                "parent_context_tokens": 200,
                "latency_ms": 50,
            }
        ]
    )
    assert data["delegate_calls"] == 1
    assert "estimated_savings_pct" in data
