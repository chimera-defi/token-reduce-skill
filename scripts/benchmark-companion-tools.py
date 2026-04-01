#!/usr/bin/env python3
"""Benchmark token-savior against token-reduce helper flows."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

try:
    import tiktoken
except ImportError:
    print("tiktoken required: uv run --with tiktoken scripts/benchmark-companion-tools.py")
    raise


ENCODER = tiktoken.get_encoding("cl100k_base")


TASKS = [
    {
        "name": "exact_symbol_lookup",
        "token_reduce": [
            ["./scripts/token-reduce-paths.sh", "discovery", "hint"],
            ["./scripts/token-reduce-snippet.sh", "discovery", "hint"],
        ],
        "token_savior": ["find-symbol", "discovery_hint"],
    },
    {
        "name": "constant_lookup",
        "token_reduce": [
            ["./scripts/token-reduce-paths.sh", "state", "ttl", "seconds"],
        ],
        "token_savior": ["search", "STATE_TTL_SECONDS"],
    },
    {
        "name": "impact_analysis",
        "token_reduce": [
            ["./scripts/token-reduce-paths.sh", "prompt", "requires", "helper"],
        ],
        "token_savior": ["change-impact", "prompt_requires_helper"],
    },
    {
        "name": "broad_topic_search",
        "token_reduce": [
            ["./scripts/token-reduce-paths.sh", "hook", "enforcement", "system"],
            ["./scripts/token-reduce-snippet.sh", "hook", "enforcement", "system"],
        ],
        "token_savior": ["search", "hook enforcement system"],
    },
]


def run_cmd(cmd: list[str], cwd: Path) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    output = (proc.stdout or "") + ((("\n" + proc.stderr) if proc.stderr else ""))
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "chars": len(output),
        "tokens": len(ENCODER.encode(output)),
        "elapsed_ms": round(elapsed_ms, 2),
        "output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--token-savior-repo", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    token_savior_repo = Path(args.token_savior_repo).resolve()

    results = {"repo_root": str(repo_root), "token_savior_repo": str(token_savior_repo), "tasks": []}

    for task in TASKS:
        tr_runs = [run_cmd(cmd, repo_root) for cmd in task["token_reduce"]]
        token_savior_python = token_savior_repo / ".venv" / "bin" / "python"
        if token_savior_python.exists():
            ts_cmd = [
                str(token_savior_python),
                str(repo_root / "scripts" / "token-reduce-structural.py"),
                "--project-root",
                str(repo_root),
                *task["token_savior"],
            ]
        else:
            ts_cmd = [
                "uv",
                "run",
                "python",
                str(repo_root / "scripts" / "token-reduce-structural.py"),
                "--project-root",
                str(repo_root),
                *task["token_savior"],
            ]
        ts_run = run_cmd(ts_cmd, token_savior_repo)
        results["tasks"].append(
            {
                "name": task["name"],
                "token_reduce_total_chars": sum(run["chars"] for run in tr_runs),
                "token_reduce_total_tokens": sum(run["tokens"] for run in tr_runs),
                "token_reduce_total_elapsed_ms": round(sum(run["elapsed_ms"] for run in tr_runs), 2),
                "token_reduce_runs": tr_runs,
                "token_savior": ts_run,
            }
        )

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
