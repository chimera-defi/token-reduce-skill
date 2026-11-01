"""Small, fail-open hygiene classifiers; no telemetry or process side effects."""
from __future__ import annotations

import os
import stat


def read_advice(tool_input: dict) -> str | None:
    """Inspect large regular files only; callers handle explicit Read limits."""
    try:
        path = tool_input.get("file_path")
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 12_000:
            return None
        newlines = 0
        last_byte = b""
        with open(path, "rb") as handle:
            while chunk := handle.read(64 * 1024):
                newlines += chunk.count(b"\n")
                if newlines > 300:
                    return "read_unbounded"
                last_byte = chunk[-1:]
        if newlines + bool(last_byte and last_byte != b"\n") > 300:
            return "read_unbounded"
    except Exception:
        pass
    return None


def grep_advice(tool_input: dict) -> str | None:
    """Flag content output without a positive result bound."""
    try:
        if tool_input.get("output_mode") != "content":
            return None
        limit = tool_input.get("head_limit")
        if isinstance(limit, (int, float)) and limit > 0:
            return None
        return "grep_no_head_limit"
    except Exception:
        return None


def _path_count(result: object) -> int | None:
    if isinstance(result, str):
        return sum(bool(line.strip()) for line in result.splitlines())
    if isinstance(result, list):
        return sum(bool(entry.strip()) if isinstance(entry, str) else bool(entry)
                   for entry in result)
    if isinstance(result, dict):
        for key in ("filenames", "files", "numFiles", "content"):
            value = result.get(key)
            if key == "numFiles":
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
            elif isinstance(value, (str, list)):
                return _path_count(value)
    return None


def glob_result_advice(data: dict) -> tuple[str, int] | None:
    """Count supported Glob response shapes, falling back to tool_result."""
    try:
        count = _path_count(data.get("tool_response"))
        if count is None:
            count = _path_count(data.get("tool_result"))
        if count is not None and count > 50:
            return "glob_explosion", count
    except Exception:
        pass
    return None
