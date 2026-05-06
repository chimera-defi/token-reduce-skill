#!/usr/bin/env python3
"""Extract file paths from token-reduce helper output and emit metadata.

Reads raw helper output from stdin (one path per line), handles qmd:// URLs,
rg file:line output, and plain paths. Writes compact JSON to stdout.
"""
from __future__ import annotations

import json
import sys


def extract_paths(raw: str) -> tuple[int, list[str]]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    paths: list[str] = []
    for line in lines:
        if line.startswith("qmd://"):
            parts = line.split("/", 3)
            if len(parts) >= 4:
                paths.append(parts[3])
        elif ":" in line and not line.startswith("/"):
            # rg -n style "file:line_number:content" or "file:content"
            paths.append(line.split(":", 1)[0])
        else:
            paths.append(line)
    return len(lines), paths[:5]


def main() -> int:
    raw = sys.stdin.read()
    count, top_paths = extract_paths(raw)
    print(json.dumps({"files_returned_count": count, "top_returned_paths": top_paths}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
