#!/usr/bin/env python3
"""Benchmark token-reduction helper output against broader discovery commands.

Run with:
  uv run --with tiktoken scripts/benchmark-token-reduce.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import tiktoken


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "local-benchmark.json"
ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class BenchmarkResult:
    name: str
    command: str
    exit_code: int
    duration_ms: int
    bytes: int
    lines: int
    tokens: int
    stdout_preview: str


BENCHMARKS = (
    (
        "broad_inventory",
        "rg --files -g '!scripts/__pycache__/**' -g '!references/benchmarks/local-benchmark.json' . | head -200",
    ),
    (
        "scoped_rg",
        "rg --files -g '!scripts/__pycache__/**' -g '!references/benchmarks/local-benchmark.json' . | rg -i -e 'hook|bash|exploratory|scans|token-reduce' | head -20",
    ),
    (
        "token_reduce_paths",
        "./scripts/token-reduce-paths.sh \"hook broad exploratory bash scans\"",
    ),
    (
        "token_reduce_snippet",
        "./scripts/token-reduce-snippet.sh \"token reduction\"",
    ),
)


def run_command(command: str) -> BenchmarkResult:
    start = time.perf_counter()
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    stdout = completed.stdout
    preview_lines = stdout.strip().splitlines()[:6]
    return BenchmarkResult(
        name="",
        command=command,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        bytes=len(stdout.encode("utf-8")),
        lines=len(stdout.splitlines()),
        tokens=len(ENCODING.encode(stdout)),
        stdout_preview="\n".join(preview_lines),
    )


def compute_savings(results: list[BenchmarkResult]) -> dict[str, float]:
    baseline = next(result for result in results if result.name == "broad_inventory").tokens
    savings = {}
    for result in results:
        if result.name == "broad_inventory":
            savings[result.name] = 0.0
            continue
        savings[result.name] = round((1 - (result.tokens / baseline)) * 100, 1)
    return savings


def render_table(results: list[BenchmarkResult], savings: dict[str, float]) -> str:
    lines = [
        "| Strategy | Tokens | Savings vs broad inventory | Duration |",
        "|----------|--------|----------------------------|----------|",
    ]
    for result in results:
        saving = "baseline" if result.name == "broad_inventory" else f"{savings[result.name]}%"
        lines.append(
            f"| `{result.name}` | `{result.tokens}` | {saving} | `{result.duration_ms} ms` |"
        )
    return "\n".join(lines)


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    results: list[BenchmarkResult] = []
    for name, command in BENCHMARKS:
        result = run_command(command)
        result.name = name
        results.append(result)

    savings = compute_savings(results)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cwd": str(ROOT),
        "qmd_available": shutil.which("qmd") is not None,
        "benchmarks": [asdict(result) for result in results],
        "savings_vs_broad_inventory": savings,
        "table": render_table(results, savings),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Wrote {OUTPUT_PATH}")
    print()
    print(payload["table"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
