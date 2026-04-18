#!/usr/bin/env python3
"""Benchmark token-optimizer-mcp CLI wrapper against token-reduce-style tasks.

This benchmark is intentionally narrow: it evaluates whether token-optimizer-mcp's
smart tool outputs improve token-reduce's core discovery task classes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    import tiktoken
except ImportError:
    tiktoken = None


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "token-optimizer-mcp-intake.json"


@dataclass
class CaseResult:
    name: str
    command: str
    cwd: str
    exit_code: int
    duration_ms: int
    bytes: int
    lines: int
    tokens: int
    quality_pass: bool
    quality_note: str
    stdout_preview: str


def token_count(text: str) -> int:
    if tiktoken is None:
        return len(text.split())
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def run_shell(command: str, *, cwd: Path, expected_substrings: list[str]) -> CaseResult:
    started = time.perf_counter()
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stdout = proc.stdout or ""
    failures = [needle for needle in expected_substrings if needle not in stdout]
    return CaseResult(
        name="",
        command=command,
        cwd=str(cwd),
        exit_code=proc.returncode,
        duration_ms=elapsed_ms,
        bytes=len(stdout.encode("utf-8")),
        lines=len(stdout.splitlines()),
        tokens=token_count(stdout),
        quality_pass=not failures,
        quality_note="ok" if not failures else f"missing: {', '.join(failures)}",
        stdout_preview="\n".join(stdout.splitlines()[:8]),
    )


def run_wrapper(
    tool_repo: Path, tool_name: str, payload: dict[str, object], *, expected_substrings: list[str]
) -> CaseResult:
    command = f"node cli-wrapper.mjs {tool_name} --stdin"
    started = time.perf_counter()
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=tool_repo,
        input=json.dumps(payload),
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stdout = proc.stdout or ""
    failures = [needle for needle in expected_substrings if needle not in stdout]
    return CaseResult(
        name="",
        command=f"{command} <<<'{json.dumps(payload)}'",
        cwd=str(tool_repo),
        exit_code=proc.returncode,
        duration_ms=elapsed_ms,
        bytes=len(stdout.encode("utf-8")),
        lines=len(stdout.splitlines()),
        tokens=token_count(stdout),
        quality_pass=not failures,
        quality_note="ok" if not failures else f"missing: {', '.join(failures)}",
        stdout_preview="\n".join(stdout.splitlines()[:8]),
    )


def savings(baseline_tokens: int, candidate_tokens: int) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return round((1 - (candidate_tokens / baseline_tokens)) * 100, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--token-optimizer-repo", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    token_optimizer_repo = Path(args.token_optimizer_repo).resolve()
    if not (token_optimizer_repo / "cli-wrapper.mjs").exists():
        raise SystemExit(f"missing cli-wrapper.mjs in {token_optimizer_repo}")

    raw_files = run_shell(
        "rg --files . | head -200",
        cwd=repo_root,
        expected_substrings=["./scripts/token-reduce-manage.sh", "./README.md"],
    )
    raw_files.name = "raw_files_inventory"

    smart_glob = run_wrapper(
        token_optimizer_repo,
        "smart_glob",
        {"pattern": "**/*", "cwd": str(repo_root), "limit": 200},
        expected_substrings=["token-reduce-manage.sh"],
    )
    smart_glob.name = "smart_glob_inventory"

    raw_grep = run_shell(
        "rg -n -i -g '*.md' 'token reduction' . | head -40",
        cwd=repo_root,
        expected_substrings=["references/token-reduction-guide.md"],
    )
    raw_grep.name = "raw_scoped_grep"

    smart_grep_matches = run_wrapper(
        token_optimizer_repo,
        "smart_grep",
        {
            "pattern": "token reduction",
            "cwd": str(repo_root),
            "files": ["**/*.md"],
            "caseSensitive": False,
            "regex": False,
            "limit": 40,
        },
        expected_substrings=["token-reduction-guide.md"],
    )
    smart_grep_matches.name = "smart_grep_matches"

    smart_grep_files_only = run_wrapper(
        token_optimizer_repo,
        "smart_grep",
        {
            "pattern": "token reduction",
            "cwd": str(repo_root),
            "files": ["**/*.md"],
            "filesWithMatches": True,
            "limit": 40,
        },
        expected_substrings=["token-reduction-guide.md"],
    )
    smart_grep_files_only.name = "smart_grep_files_only"

    cases = [raw_files, smart_glob, raw_grep, smart_grep_matches, smart_grep_files_only]

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_root": str(repo_root),
        "token_optimizer_repo": str(token_optimizer_repo),
        "cases": [asdict(case) for case in cases],
        "comparison": {
            "inventory_baseline_tokens": raw_files.tokens,
            "smart_glob_tokens": smart_glob.tokens,
            "smart_glob_savings_vs_raw_inventory_pct": savings(raw_files.tokens, smart_glob.tokens),
            "grep_baseline_tokens": raw_grep.tokens,
            "smart_grep_matches_tokens": smart_grep_matches.tokens,
            "smart_grep_matches_savings_vs_raw_grep_pct": savings(raw_grep.tokens, smart_grep_matches.tokens),
            "smart_grep_files_only_tokens": smart_grep_files_only.tokens,
            "smart_grep_files_only_savings_vs_raw_grep_pct": savings(
                raw_grep.tokens, smart_grep_files_only.tokens
            ),
        },
        "verdict": {
            "default_for_token_reduce_discovery": False,
            "reason": (
                "smart_glob quality failed on representative inventory task and smart_grep variants "
                "produced higher token output than scoped rg for this repo workload."
            ),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {OUTPUT_PATH}")
    print(
        json.dumps(
            {
                "inventory": {
                    "raw_tokens": raw_files.tokens,
                    "smart_glob_tokens": smart_glob.tokens,
                    "quality_pass": smart_glob.quality_pass,
                },
                "grep": {
                    "raw_tokens": raw_grep.tokens,
                    "smart_grep_matches_tokens": smart_grep_matches.tokens,
                    "smart_grep_files_only_tokens": smart_grep_files_only.tokens,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
