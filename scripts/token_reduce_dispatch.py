#!/usr/bin/env python3
"""Single Python dispatch for token-reduce helpers.

Consolidates rank_paths, brain_hint, and telemetry error logging into
one subprocess call — eliminates 3 separate `uv run python3` spawns.

Usage (from paths.sh):
  search_results | uv run python3 scripts/token_reduce_dispatch.py \
      --mode paths --query "..." [--repo-root DIR] [--rank-args ARG...]
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))


def _try_record_error(event: str, query: str, repo_root: Path) -> None:
    try:
        from token_reduce_telemetry import record_event
        record_event(
            repo_root=repo_root,
            event=event,
            source="helper",
            tool="token_reduce_dispatch",
            status="error",
            query=query,
        )
    except Exception:
        pass


def _run_rank(search_results: str, query: str, repo_root: Path, rank_args: list[str]) -> str:
    rank_script = _SCRIPTS_DIR / "rank_paths.py"
    if os.environ.get("TOKEN_REDUCE_DISABLE_RANK") or not rank_script.exists():
        return search_results
    try:
        from rank_paths import _cli

        saved_stdin, saved_stdout = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(search_results)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            argv = ["--query", query, "--repo-root", str(repo_root)] + rank_args
            rc = _cli(argv)
        finally:
            sys.stdin, sys.stdout = saved_stdin, saved_stdout

        if rc == 0 and captured.getvalue().strip():
            return captured.getvalue()
        if rc != 0:
            print(f"token-reduce: rank_paths returned rc={rc}", file=sys.stderr)
            _try_record_error("rank_paths_error", query, repo_root)
    except Exception as exc:
        print(f"token-reduce: rank_paths failed: {exc}", file=sys.stderr)
        _try_record_error("rank_paths_error", query, repo_root)
    return search_results


def _run_brain_hint(query: str, repo_root: Path) -> None:
    brain_script = _SCRIPTS_DIR / "brain_hint.py"
    if os.environ.get("TOKEN_REDUCE_DISABLE_BRAIN_HINT") or not brain_script.exists():
        return
    try:
        from brain_hint import hint_line
        hint = hint_line(query)
        if hint:
            print(f"# brain-hint: {hint}", file=sys.stderr)
    except Exception as exc:
        print(f"token-reduce: brain_hint failed: {exc}", file=sys.stderr)
        _try_record_error("brain_hint_error", query, repo_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="token-reduce Python dispatch")
    parser.add_argument("--mode", choices=["paths", "snippet"], required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--rank-args", nargs="*", default=[])
    args = parser.parse_args()

    search_results = sys.stdin.read()

    if args.mode == "paths":
        output = _run_rank(search_results, args.query, args.repo_root, args.rank_args)
        _run_brain_hint(args.query, args.repo_root)
    else:
        output = search_results

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
