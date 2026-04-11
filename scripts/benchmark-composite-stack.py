#!/usr/bin/env python3
"""Benchmark token-reduce composite stack against single-tool strategies.

Run with:
  uv run --with tiktoken scripts/benchmark-composite-stack.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path

try:
    import tiktoken
except ImportError:
    tiktoken = None


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "composite-benchmark.json"
QMD_COLLECTION = f"repo-{sha1(str(ROOT).encode('utf-8')).hexdigest()[:12]}"


@dataclass
class StepResult:
    label: str
    command: str
    exit_code: int
    duration_ms: int
    bytes: int
    lines: int
    tokens: int
    quality_pass: bool
    quality_note: str
    stdout_preview: str


@dataclass
class StrategyResult:
    name: str
    requires: list[str]
    available: bool
    skipped_reason: str
    exit_code: int
    duration_ms: int
    bytes: int
    lines: int
    tokens: int
    quality_pass: bool
    savings_vs_broad_pct: float
    steps: list[StepResult]


def token_count(text: str) -> int:
    if tiktoken is None:
        return len(text.split())
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def run_cmd(command: str, expected_substrings: list[str]) -> StepResult:
    started = time.perf_counter()
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    stdout = proc.stdout or ""
    preview = "\n".join(stdout.splitlines()[:6])
    quality_failures = [needle for needle in expected_substrings if needle not in stdout]
    quality_pass = len(quality_failures) == 0
    quality_note = "ok" if quality_pass else f"missing: {', '.join(quality_failures)}"
    return StepResult(
        label="",
        command=command,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        bytes=len(stdout.encode("utf-8")),
        lines=len(stdout.splitlines()),
        tokens=token_count(stdout),
        quality_pass=quality_pass,
        quality_note=quality_note,
        stdout_preview=preview,
    )


def ensure_qmd_collection() -> None:
    if shutil.which("qmd") is None:
        return
    subprocess.run(
        [
            "bash",
            "-lc",
            f"qmd collection add {json.dumps(str(ROOT))} --name {QMD_COLLECTION} --mask '**/*.md' >/dev/null 2>&1 || true",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def availability(requirements: list[str]) -> tuple[bool, str]:
    missing = [tool for tool in requirements if shutil.which(tool) is None]
    if missing:
        return False, f"missing tools: {', '.join(missing)}"
    return True, ""


def run_strategy(
    name: str, requirements: list[str], steps: list[tuple[str, str, list[str]]]
) -> StrategyResult:
    ok, reason = availability(requirements)
    if not ok:
        return StrategyResult(
            name=name,
            requires=requirements,
            available=False,
            skipped_reason=reason,
            exit_code=0,
            duration_ms=0,
            bytes=0,
            lines=0,
            tokens=0,
            quality_pass=False,
            savings_vs_broad_pct=0.0,
            steps=[],
        )

    step_results: list[StepResult] = []
    total_exit_code = 0
    quality_pass = True
    for label, command, expected_substrings in steps:
        result = run_cmd(command, expected_substrings)
        result.label = label
        step_results.append(result)
        if result.exit_code != 0 and total_exit_code == 0:
            total_exit_code = result.exit_code
        if not result.quality_pass:
            quality_pass = False

    return StrategyResult(
        name=name,
        requires=requirements,
        available=True,
        skipped_reason="",
        exit_code=total_exit_code,
        duration_ms=sum(step.duration_ms for step in step_results),
        bytes=sum(step.bytes for step in step_results),
        lines=sum(step.lines for step in step_results),
        tokens=sum(step.tokens for step in step_results),
        quality_pass=quality_pass,
        savings_vs_broad_pct=0.0,
        steps=step_results,
    )


def render_table(results: list[StrategyResult]) -> str:
    lines = [
        "| Strategy | Tokens | Savings vs broad | Duration | Status |",
        "|----------|--------|------------------|----------|--------|",
    ]
    for result in results:
        if not result.available:
            lines.append(
                f"| `{result.name}` | `-` | `-` | `-` | skipped ({result.skipped_reason}) |"
            )
            continue
        status = "ok" if result.exit_code == 0 else f"exit {result.exit_code}"
        if result.exit_code == 0 and not result.quality_pass:
            status = "quality-fail"
        lines.append(
            f"| `{result.name}` | `{result.tokens}` | `{result.savings_vs_broad_pct}%` | `{result.duration_ms} ms` | {status} |"
        )
    return "\n".join(lines)


def main() -> int:
    ensure_qmd_collection()

    strategies = [
        (
            "broad_shell",
            ["rg"],
            [
                ("fuzzy_discovery", "rg --files . | head -200", []),
                (
                    "exact_symbol",
                    "rg -n \"prompt_requires_helper\" scripts/*.py | head -40",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rg -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
        (
            "qmd_only",
            ["qmd", "rg"],
            [
                (
                    "fuzzy_discovery",
                    f"qmd search \"hook enforcement system\" -n 8 --files -c {QMD_COLLECTION}",
                    [],
                ),
                (
                    "exact_symbol",
                    f"qmd search \"prompt_requires_helper\" -n 8 --files -c {QMD_COLLECTION}",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rg -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
        (
            "token_reduce_only",
            ["token-reduce-paths", "rg"],
            [
                ("fuzzy_discovery", "token-reduce-paths hook enforcement system | head -40", []),
                (
                    "exact_symbol",
                    "token-reduce-paths prompt requires helper | head -40",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rg -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
        (
            "token_savior_only",
            ["token-reduce-structural", "rg"],
            [
                (
                    "fuzzy_discovery",
                    "token-reduce-structural --project-root . search \"hook enforcement system\" | head -80",
                    [],
                ),
                (
                    "exact_symbol",
                    "token-reduce-structural --project-root . find-symbol prompt_requires_helper | head -80",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rg -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
        (
            "rtk_only",
            ["rtk"],
            [
                ("fuzzy_discovery", "rtk find . -name '*.md' | head -40", []),
                (
                    "exact_symbol",
                    "rtk grep -n \"prompt_requires_helper\" scripts/*.py | head -40",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rtk grep -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
        (
            "composite_stack",
            ["token-reduce-paths", "token-reduce-structural", "rtk"],
            [
                ("fuzzy_discovery", "token-reduce-paths hook enforcement system | head -40", []),
                (
                    "exact_symbol",
                    "token-reduce-structural --project-root . find-symbol prompt_requires_helper | head -80",
                    ["prompt_requires_helper", "scripts/token_reduce_state.py"],
                ),
                (
                    "output_scan",
                    "rtk grep -n -i \"token reduction\" README.md SKILL.md references/*.md | head -80",
                    ["Token Reduction Guide"],
                ),
            ],
        ),
    ]

    results = [run_strategy(name, requires, steps) for name, requires, steps in strategies]

    broad = next((r.tokens for r in results if r.name == "broad_shell" and r.available), 0)
    for result in results:
        if not result.available or broad == 0:
            continue
        result.savings_vs_broad_pct = round((1 - (result.tokens / broad)) * 100, 1)

    singles = [
        r
        for r in results
        if r.name in {"qmd_only", "token_reduce_only", "token_savior_only", "rtk_only", "broad_shell"}
        and r.available
        and r.exit_code == 0
        and r.quality_pass
    ]
    composite = next((r for r in results if r.name == "composite_stack"), None)
    beats = {}
    if composite and composite.available and composite.exit_code == 0 and composite.quality_pass:
        beats = {single.name: (composite.tokens < single.tokens) for single in singles}

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cwd": str(ROOT),
        "qmd_collection": QMD_COLLECTION,
        "benchmarks": [asdict(result) for result in results],
        "table": render_table(results),
        "composite_vs_single": {
            "composite_tokens": composite.tokens if composite else None,
            "composite_quality_pass": composite.quality_pass if composite else False,
            "single_tool_candidates": [single.name for single in singles],
            "beats": beats,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Wrote {OUTPUT_PATH}")
    print()
    print(payload["table"])
    if beats:
        print()
        print("Composite vs single-tool token wins:")
        for strategy_name, won in beats.items():
            print(f"- {strategy_name}: {'win' if won else 'loss'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
