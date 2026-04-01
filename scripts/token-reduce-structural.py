#!/usr/bin/env python3
"""Optional structural query helper backed by token-savior.

This is an accelerator for exact symbol / impact questions. It does not replace
the repo-agnostic token-reduce helper workflow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


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
    queries = build_queries(args.project_root)

    if args.command == "find-symbol":
        emit(compact_find_symbol(queries["find_symbol"](args.symbol)))
        return 0
    if args.command == "function-source":
        emit(queries["get_function_source"](args.symbol))
        return 0
    if args.command == "search":
        emit(compact_search(queries["search_codebase"](args.query)))
        return 0
    if args.command == "change-impact":
        emit(compact_change_impact(queries["get_change_impact"](args.symbol)))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
