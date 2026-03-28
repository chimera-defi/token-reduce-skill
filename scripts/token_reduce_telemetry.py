#!/usr/bin/env python3
"""Repo-local telemetry for token-reduce helper and hook events."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def default_repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    try:
        root = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return script_dir.parents[1]
    return Path(root)


def events_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "token-reduction" / "events.jsonl"


def record_event(
    repo_root: Path,
    *,
    event: str,
    source: str,
    tool: str | None = None,
    status: str = "ok",
    query: str | None = None,
    meta: dict | None = None,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "source": source,
        "status": status,
    }
    if tool:
        payload["tool"] = tool
    if query:
        payload["query"] = query
    if meta:
        payload["meta"] = meta

    path = events_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_events(repo_root: Path, *, days: int | None = None) -> list[dict]:
    path = events_path(repo_root)
    if not path.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff is not None:
            raw_ts = event.get("timestamp")
            if isinstance(raw_ts, str):
                try:
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = None
                if ts is not None and ts < cutoff:
                    continue
        events.append(event)
    return events


def summarize_events(events: list[dict]) -> dict:
    by_event = Counter()
    by_tool = Counter()
    by_status = Counter()
    tool_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "chars_total": 0, "lines_total": 0}
    )

    for event in events:
        by_event[str(event.get("event", "unknown"))] += 1
        if tool := event.get("tool"):
            by_tool[str(tool)] += 1
        by_status[str(event.get("status", "unknown"))] += 1

        meta = event.get("meta", {})
        if tool and isinstance(meta, dict):
            stats = tool_stats[str(tool)]
            stats["count"] += 1
            stats["chars_total"] += int(meta.get("chars", 0) or 0)
            stats["lines_total"] += int(meta.get("lines", 0) or 0)

    helper_stats = {}
    for tool, stats in sorted(tool_stats.items()):
        count = int(stats["count"])
        helper_stats[tool] = {
            "count": count,
            "avg_chars": round(stats["chars_total"] / count, 1) if count else 0.0,
            "avg_lines": round(stats["lines_total"] / count, 1) if count else 0.0,
        }

    return {
        "event_count": len(events),
        "by_event": dict(sorted(by_event.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "by_status": dict(sorted(by_status.items())),
        "tool_stats": helper_stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    subparsers = parser.add_subparsers(dest="command", required=True)

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--event", required=True)
    log_parser.add_argument("--source", required=True)
    log_parser.add_argument("--tool")
    log_parser.add_argument("--status", default="ok")
    log_parser.add_argument("--query")
    log_parser.add_argument("--meta-json")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--days", type=int, default=14)

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    if args.command == "log":
        meta = None
        if args.meta_json:
            try:
                meta = json.loads(args.meta_json)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid --meta-json: {exc}")
        record_event(
            repo_root,
            event=args.event,
            source=args.source,
            tool=args.tool,
            status=args.status,
            query=args.query,
            meta=meta,
        )
        return 0

    if args.command == "summary":
        print(json.dumps(summarize_events(load_events(repo_root, days=args.days)), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
