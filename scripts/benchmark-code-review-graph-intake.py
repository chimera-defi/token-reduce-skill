#!/usr/bin/env python3
"""Run code-review-graph intake validation and token-efficiency eval."""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "code-review-graph-intake.json"


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


def parse_pytest_summary(output: str) -> dict[str, int]:
    match = re.search(
        r"(\d+)\s+passed,\s+(\d+)\s+skipped,\s+(\d+)\s+xpassed", output
    )
    if not match:
        return {"passed": 0, "skipped": 0, "xpassed": 0}
    return {
        "passed": int(match.group(1)),
        "skipped": int(match.group(2)),
        "xpassed": int(match.group(3)),
    }


def read_eval_rows(csv_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                {
                    "commit": row["commit"],
                    "naive_tokens": int(row["naive_tokens"]),
                    "graph_tokens": int(row["graph_tokens"]),
                    "naive_to_graph_ratio": float(row["naive_to_graph_ratio"]),
                }
            )
    return rows


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
    parser.add_argument("--code-review-graph-repo", required=True)
    parser.add_argument("--repos", default="express,fastapi")
    args = parser.parse_args()

    repo = Path(args.code_review_graph_repo).resolve()
    if not (repo / "pyproject.toml").exists():
        raise SystemExit(f"not a code-review-graph repo: {repo}")

    code, out, err, test_ms = run(
        ["uv", "run", "--with", "pytest", "--with", "pytest-asyncio", "pytest", "-q"],
        repo,
    )
    if code != 0:
        raise SystemExit((out + "\n" + err).strip())
    test_summary = parse_pytest_summary(out + "\n" + err)

    repos = [item.strip() for item in args.repos.split(",") if item.strip()]
    eval_output: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="crg-eval-") as tmp_dir:
        tmp = Path(tmp_dir)
        for repo_name in repos:
            code, out, err, ms = run(
                [
                    "uv",
                    "run",
                    "code-review-graph",
                    "eval",
                    "--benchmark",
                    "token_efficiency",
                    "--repo",
                    repo_name,
                    "--output-dir",
                    str(tmp),
                ],
                repo,
            )
            if code != 0:
                raise SystemExit((out + "\n" + err).strip())

            expected = next(tmp.glob(f"{repo_name}_token_efficiency_*.csv"), None)
            if expected is None:
                raise SystemExit(f"missing eval csv for repo '{repo_name}' in {tmp}")
            eval_output.append(
                {
                    "repo": repo_name,
                    "duration_ms": ms,
                    "rows": read_eval_rows(expected),
                }
            )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_repo": "https://github.com/tirth8205/code-review-graph",
        "commit": read_git_head(repo),
        "validation": {
            "test_command": "uv run --with pytest --with pytest-asyncio pytest -q",
            "duration_ms": test_ms,
            "test_result": test_summary,
        },
        "token_efficiency_eval": {
            "runner": "uv run code-review-graph eval --benchmark token_efficiency --repo <repo>",
            "repos": eval_output,
        },
        "verdict": {
            "default_for_token_reduce_first_move": False,
            "recommended_usage": "optional structural review companion for larger dependency-rich repos",
            "caveat": "can lose on tiny single-file diffs due graph metadata overhead",
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(json.dumps(payload["validation"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
