#!/usr/bin/env python3
"""Run context-mode intake validation and benchmark, emit JSON artifact."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "context-mode-intake.json"


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return proc.returncode, proc.stdout or "", proc.stderr or "", duration_ms


def parse_vitest_summary(output: str) -> dict[str, int]:
    files_passed = 0
    tests_passed = 0
    tests_skipped = 0

    files_match = re.search(r"Test Files\s+(\d+)\s+passed", output)
    tests_match = re.search(r"Tests\s+(\d+)\s+passed\s+\|\s+(\d+)\s+skipped", output)
    if files_match:
        files_passed = int(files_match.group(1))
    if tests_match:
        tests_passed = int(tests_match.group(1))
        tests_skipped = int(tests_match.group(2))
    return {
        "test_files_passed": files_passed,
        "tests_passed": tests_passed,
        "tests_skipped": tests_skipped,
    }


def parse_compare_summary(output: str) -> dict[str, object]:
    total_match = re.search(
        r"\|\s*TOTAL\s*\|\s*([0-9.]+KB)\s*\|\s*([0-9A-Za-z.]+)\s*\|\s*(\d+)%\s*\|", output
    )
    token_match = re.search(
        r"WITHOUT context-mode:\s*\n\s*([0-9,]+)\s+tokens consumed.*?\n\s*WITH context-mode:\s*\n\s*([0-9,]+)\s+tokens consumed",
        output,
        re.DOTALL,
    )
    saved_match = re.search(r"Tokens saved:\s*([0-9,]+)", output)
    multiplier_match = re.search(r"Multiplier:\s*([0-9xA-Za-z ]+)", output)

    out: dict[str, object] = {}
    if total_match:
        out["total_without_raw"] = total_match.group(1)
        out["total_with_context_mode"] = total_match.group(2)
        out["savings_percent"] = int(total_match.group(3))
    if token_match:
        out["estimated_tokens_without"] = int(token_match.group(1).replace(",", ""))
        out["estimated_tokens_with"] = int(token_match.group(2).replace(",", ""))
    if saved_match:
        out["estimated_tokens_saved"] = int(saved_match.group(1).replace(",", ""))
    if multiplier_match:
        out["estimated_context_multiplier"] = multiplier_match.group(1).strip()
    return out


def read_git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=False,
        text=True,
        capture_output=True,
    )
    return (proc.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context-mode-repo", required=True)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    repo = Path(args.context_mode_repo).resolve()
    if not (repo / "package.json").exists():
        raise SystemExit(f"not a context-mode repo: {repo}")

    install_result = {"command": "pnpm install --no-frozen-lockfile", "status": "skipped"}
    if not args.skip_install:
        code, out, err, ms = run(["pnpm", "install", "--no-frozen-lockfile"], repo)
        install_result = {
            "command": "pnpm install --no-frozen-lockfile",
            "exit_code": code,
            "duration_ms": ms,
            "status": "ok" if code == 0 else "failed",
        }
        if code != 0:
            raise SystemExit((out + "\n" + err).strip())

    code, out, err, build_ms = run(["pnpm", "build"], repo)
    if code != 0:
        raise SystemExit((out + "\n" + err).strip())

    code, out, err, test_ms = run(["pnpm", "test"], repo)
    if code != 0:
        raise SystemExit((out + "\n" + err).strip())
    test_summary = parse_vitest_summary(out + "\n" + err)

    code, out, err, compare_ms = run(["pnpm", "test:compare"], repo)
    if code != 0:
        raise SystemExit((out + "\n" + err).strip())
    compare_summary = parse_compare_summary(out + "\n" + err)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_repo": "https://github.com/mksglu/context-mode",
        "commit": read_git_head(repo),
        "validation": {
            "install": install_result,
            "build": {"command": "pnpm build", "exit_code": 0, "duration_ms": build_ms},
            "test": {
                "command": "pnpm test",
                "exit_code": 0,
                "duration_ms": test_ms,
                "test_result": test_summary,
            },
        },
        "comparison_benchmark": {
            "runner": "pnpm test:compare",
            "duration_ms": compare_ms,
            **compare_summary,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(json.dumps(payload["comparison_benchmark"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
