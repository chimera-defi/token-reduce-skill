#!/usr/bin/env python3
"""Optional structural query helper backed by token-savior.

This is an accelerator for exact symbol / impact questions. It does not replace
the repo-agnostic token-reduce helper workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

try:
    from token_reduce_telemetry import record_event
except Exception:  # pragma: no cover - host dependent
    record_event = None

try:
    from token_reduce_state import clear_pending
except Exception:  # pragma: no cover - host dependent
    clear_pending = None


def build_queries(project_root: str):
    try:
        from token_savior.project_indexer import ProjectIndexer
        from token_savior.query_api import create_project_query_functions
    except ImportError as exc:  # pragma: no cover - host dependent
        raise SystemExit(
            "token-savior is not installed. Install it first, then rerun this helper."
        ) from exc

    index = ProjectIndexer(project_root).index()
    return create_project_query_functions(index)


def emit(data) -> None:
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2))


def telemetry_root(project_root: str) -> Path:
    base = Path(project_root).resolve()
    proc = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    candidate = (proc.stdout or "").strip()
    if candidate:
        return Path(candidate).resolve()
    return base


def log_helper_event(
    *,
    project_root: str,
    status: str,
    command: str,
    query: str,
    output: object | None = None,
) -> None:
    if record_event is None:
        return
    if output is None:
        chars = 0
        lines = 0
    elif isinstance(output, str):
        chars = len(output)
        lines = len([line for line in output.splitlines() if line.strip()])
    else:
        text = json.dumps(output, indent=2)
        chars = len(text)
        lines = len([line for line in text.splitlines() if line.strip()])
    record_event(
        telemetry_root(project_root),
        event="helper_invocation",
        source="helper",
        tool="token_reduce_structural",
        status=status,
        query=f"{command}:{query}",
        meta={
            "backend": "token-savior",
            "context": os.environ.get("TOKEN_REDUCE_TELEMETRY_CONTEXT", "runtime"),
            "chars": chars,
            "lines": lines,
        },
    )


def compact_find_symbol(result: dict) -> dict:
    keys = ("name", "file", "line", "end_line", "type", "signature")
    return {key: result.get(key) for key in keys}


def compact_search(results: list[dict], limit: int = 5) -> list[dict]:
    compacted = []
    for item in results[:limit]:
        compacted.append(
            {
                "file": item.get("file"),
                "line_number": item.get("line_number"),
                "content": item.get("content"),
            }
        )
    return compacted


def compact_change_impact(result: dict, limit: int = 5) -> dict:
    direct = result.get("direct", [])
    transitive = result.get("transitive", [])

    def _shrink(items: list[dict]) -> list[dict]:
        out = []
        for item in items[:limit]:
            out.append(
                {
                    "name": item.get("name"),
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "type": item.get("type"),
                    "signature": item.get("signature"),
                }
            )
        return out

    return {
        "direct_count": len(direct),
        "transitive_count": len(transitive),
        "direct_preview": _shrink(direct),
        "transitive_preview": _shrink(transitive),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root to index (defaults to current working directory).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_find = sub.add_parser("find-symbol")
    p_find.add_argument("symbol")

    p_func = sub.add_parser("function-source")
    p_func.add_argument("symbol")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")

    p_impact = sub.add_parser("change-impact")
    p_impact.add_argument("symbol")

    args = parser.parse_args()
    try:
        queries = build_queries(args.project_root)

        result: object
        lookup_value = ""
        if args.command == "find-symbol":
            lookup_value = args.symbol
            result = compact_find_symbol(queries["find_symbol"](args.symbol))
        elif args.command == "function-source":
            lookup_value = args.symbol
            result = queries["get_function_source"](args.symbol)
        elif args.command == "search":
            lookup_value = args.query
            result = compact_search(queries["search_codebase"](args.query))
        elif args.command == "change-impact":
            lookup_value = args.symbol
            result = compact_change_impact(queries["get_change_impact"](args.symbol))
        else:
            return 2

        emit(result)
        log_helper_event(
            project_root=args.project_root,
            status="ok",
            command=args.command,
            query=lookup_value,
            output=result,
        )
        if clear_pending is not None:
            clear_pending(telemetry_root(args.project_root))
        return 0
    except Exception:
        arg_value = getattr(args, "symbol", "") or getattr(args, "query", "")
        log_helper_event(
            project_root=args.project_root,
            status="error",
            command=args.command,
            query=str(arg_value),
            output=None,
        )
        raise

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
