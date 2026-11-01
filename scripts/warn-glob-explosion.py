#!/usr/bin/env python3
"""Silent PostToolUse Glob hygiene telemetry; always fail open."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from advisory_hygiene import glob_result_advice
        except Exception:
            glob_result_advice = None
        from token_reduce_central import log_call

        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        advice = glob_result_advice(data) if glob_result_advice is not None else None
        if advice is not None:
            # hook_result: annotates the call its PreToolUse hook_call already counted.
            log_call(data, advised=False, rule=advice[0], event="hook_result",
                     extra={"matched": True, "count": advice[1]})
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
