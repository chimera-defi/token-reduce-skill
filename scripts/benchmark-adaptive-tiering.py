#!/usr/bin/env python3
"""Benchmark adaptive tier routing vs baseline token-reduce paths helper."""
from __future__ import annotations

import json
import argparse
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "adaptive-tier-benchmark.json"


@dataclass
class RunResult:
    task: str
    strategy: str
    command: str
    exit_code: int
    duration_ms: int
    bytes: int
    lines: int
    tokens: int
    quality_pass: bool
    quality_note: str
    stdout_preview: str


TASKS = [
    {
        "name": "exact_symbol",
        "query": "prompt_requires_helper",
        "expected": ["token_reduce_state.py", "prompt_requires_helper"],
    },
    {
        "name": "hook_discovery",
        "query": "hook enforcement system",
        "expected": ["enforce-token-reduce-first.py"],
    },
    {
        "name": "token_reduction_docs",
        "query": "token reduction guide",
        "expected": ["token-reduction-guide.md"],
    },
]


def token_count(text: str) -> int:
    if tiktoken is None:
        return len(text.split())
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def run(command: str, expected: list[str], *, cwd: Path, strategy: str, task: str) -> RunResult:
    started = time.perf_counter()
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stdout = proc.stdout or ""
    missing = [needle for needle in expected if needle not in stdout]
    return RunResult(
        task=task,
        strategy=strategy,
        command=command,
        exit_code=proc.returncode,
        duration_ms=elapsed_ms,
        bytes=len(stdout.encode("utf-8")),
        lines=len(stdout.splitlines()),
        tokens=token_count(stdout),
        quality_pass=not missing and proc.returncode == 0,
        quality_note="ok" if not missing else f"missing: {', '.join(missing)}",
        stdout_preview="\n".join(stdout.splitlines()[:8]),
    )


def savings(baseline: int, candidate: int) -> float:
    if baseline <= 0:
        return 0.0
    return round((1 - (candidate / baseline)) * 100, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    output_path = Path(args.output).resolve()

    results: list[RunResult] = []
    for task in TASKS:
        query = task["query"]
        expected = task["expected"]
        baseline_cmd = f"./scripts/token-reduce-paths.sh {json.dumps(query)} | head -80"
        adaptive_cmd = f"./scripts/token-reduce-adaptive.sh {json.dumps(query)} | head -80"
        results.append(run(baseline_cmd, expected, cwd=ROOT, strategy="baseline_paths", task=task["name"]))
        results.append(run(adaptive_cmd, expected, cwd=ROOT, strategy="adaptive_tier", task=task["name"]))

    baseline_runs = [item for item in results if item.strategy == "baseline_paths"]
    adaptive_runs = [item for item in results if item.strategy == "adaptive_tier"]
    baseline_tokens = sum(item.tokens for item in baseline_runs)
    adaptive_tokens = sum(item.tokens for item in adaptive_runs)
    baseline_quality_pass = all(item.quality_pass for item in baseline_runs)
    adaptive_quality_pass = all(item.quality_pass for item in adaptive_runs)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "active_profile": os_profile_name(),
        "tasks": TASKS,
        "runs": [asdict(item) for item in results],
        "summary": {
            "baseline_tokens": baseline_tokens,
            "adaptive_tokens": adaptive_tokens,
            "adaptive_savings_vs_baseline_pct": savings(baseline_tokens, adaptive_tokens),
            "baseline_quality_pass": baseline_quality_pass,
            "adaptive_quality_pass": adaptive_quality_pass,
        },
        "verdict": {
            "promote_adaptive_default": adaptive_quality_pass and adaptive_tokens <= baseline_tokens,
            "reason": (
                "Adaptive default is safe when quality is preserved and token usage is not worse "
                "than baseline path-only discovery on representative tasks."
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    print(json.dumps(payload["summary"], indent=2))
    return 0


def os_profile_name() -> str:
    config_path = Path(os.environ.get("TOKEN_REDUCE_CONFIG_PATH", "")).expanduser()
    if config_path and config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            routing = raw.get("routing", {}) if isinstance(raw, dict) else {}
            value = routing.get("profile")
            if isinstance(value, str) and value:
                return value
        except Exception:
            pass
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
