#!/usr/bin/env python3
"""Summarize runtime usage from the central token-reduce JSONL sink only."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from token_reduce_central import central_path

NON_RUNTIME = {"test", "benchmark", "synthetic"}


def summarize(path: Path | None, days: int = 14) -> dict:
    by_tool, by_model, by_lane, by_project, by_rule = (Counter() for _ in range(5))
    advised, matched = Counter(), Counter()
    seen_calls = set()
    matrix = defaultdict(Counter)
    considered = skipped = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        handle = path.open(encoding="utf-8", errors="replace") if path is not None else None
    except OSError:
        handle = None
    if handle is not None:
        with handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("not an event")
                    meta = row.get("meta")
                    contexts = (row.get("source"), row.get("context"),
                                meta.get("context") if isinstance(meta, dict) else None)
                    if any(str(value).strip().lower() in NON_RUNTIME for value in contexts):
                        raise ValueError("non-runtime")
                    # hook_warn/block/error are auxiliary events, already represented
                    # by the one hook_call row for that invocation.
                    if row.get("source") == "hook" and row.get("event") != "hook_call":
                        raise ValueError("auxiliary hook event")
                    ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        raise ValueError("outside window")
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                    skipped += 1
                    continue
                call_id = (row.get("session"), row.get("call")) if row.get("call") else None
                if call_id in seen_calls:
                    skipped += 1  # same tool call seen by a second hook layer
                    continue
                if call_id:
                    seen_calls.add(call_id)
                considered += 1
                tool = str(row.get("tool") or "unknown")
                model = str(row.get("model") or "unknown")
                by_tool[tool] += 1
                by_model[model] += 1
                by_lane[str(row.get("lane") or "unknown")] += 1
                by_project[str(row.get("project") or "unknown")] += 1
                matrix[model][tool] += 1
                if row.get("advised") is True:
                    advised[tool] += 1
                if row.get("matched") is True or row.get("advised") is True:
                    matched[tool] += 1
                    by_rule[str(row.get("rule") or "unknown")] += 1
    return {
        "events_considered": considered, "events_skipped": skipped,
        "by_tool": dict(by_tool.most_common()), "by_model": dict(by_model.most_common()),
        "by_lane": dict(by_lane.most_common()), "by_project": dict(by_project.most_common(10)),
        "advice_rate_by_tool": {
            tool: {"advised": advised[tool], "total": count, "rate": advised[tool] / count}
            for tool, count in by_tool.items()
        },
        "rule_match_rate_by_tool": {
            tool: {"matched": matched[tool], "total": count, "rate": matched[tool] / count}
            for tool, count in by_tool.items()
        },
        "advice_by_rule": dict(by_rule.most_common()),
        "model_tool_matrix": {model: dict(counts) for model, counts in matrix.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, help="override the central sink path")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days must be nonnegative")
    report = summarize(args.events if args.events is not None else central_path(), args.days)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"Events considered: {report['events_considered']} / Events skipped: {report['events_skipped']}")
    if not report["events_considered"]:
        print("No events in the selected window (central sink empty, missing, disabled, or unreadable).")
        return 0
    for key, label in (("by_tool", "Calls by tool"), ("by_model", "Calls by model"),
                       ("by_lane", "Calls by lane"), ("by_project", "Calls by project (top 10)"),
                       ("advice_by_rule", "Rule matches by rule")):
        print(f"\n{label}:")
        for name, count in report[key].items():
            print(f"  {name}: {count}")
    print("\nAdvice emitted to the model by tool:")
    for tool, counts in report["advice_rate_by_tool"].items():
        print(f"  {tool}: {counts['advised']}/{counts['total']} ({counts['rate']:.1%})")
    print("\nRule matched (advice or telemetry-only) by tool:")
    for tool, counts in report["rule_match_rate_by_tool"].items():
        print(f"  {tool}: {counts['matched']}/{counts['total']} ({counts['rate']:.1%})")
    print("\nModel x tool matrix:")
    tools = sorted(report["by_tool"])
    print("  model\t" + "\t".join(tools))
    for model, counts in sorted(report["model_tool_matrix"].items()):
        print("  " + model + "\t" + "\t".join(str(counts.get(tool, 0)) for tool in tools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
