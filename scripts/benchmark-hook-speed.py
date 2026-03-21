#!/usr/bin/env python3
"""Benchmark hook startup overhead and helper runtime in this repo."""
from __future__ import annotations

import json
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "script-speed.json"
RUNS = 10

COMMANDS = {
    "bash_true": ["bash", "-lc", "true"],
    "uv_python_true": ["uv", "run", "python", "-c", "pass"],
    "hook_remind_py": [
        "bash",
        "-lc",
        "printf '%s\\n' '{\"user_prompt\":\"Find the Python script that measures token reduction adoption for this repo. Use the minimum context possible and return only the path.\"}' | uv run scripts/remind-token-reduce.py >/dev/null",
    ],
    "hook_enforce_py": [
        "bash",
        "-lc",
        "printf '%s\\n' '{\"tool_name\":\"Glob\",\"tool_input\":{\"pattern\":\"scripts/*token*reduce*.py\"}}' | uv run scripts/enforce-token-reduce-first.py >/dev/null || true",
    ],
    "paths_helper": ["bash", "-lc", "./scripts/token-reduce-paths.sh 'token reduction' >/dev/null"],
    "snippet_helper": ["bash", "-lc", "./scripts/token-reduce-snippet.sh 'token reduction' >/dev/null"],
}


def benchmark(cmd: list[str]) -> dict[str, float]:
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
        times.append((time.perf_counter() - start) * 1000)
    return {
        "mean_ms": round(statistics.mean(times), 1),
        "median_ms": round(statistics.median(times), 1),
        "min_ms": round(min(times), 1),
        "max_ms": round(max(times), 1),
    }


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "runs": RUNS,
        "results": {name: benchmark(cmd) for name, cmd in COMMANDS.items()},
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
