#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_plan_prompt_returns_required_keys() -> None:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [str(root / "scripts" / "plan_prompt.py"), "--task", "summarize failing CI run"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    for key in ("goal", "task_class", "constraints", "acceptance", "output_schema"):
        assert key in payload
