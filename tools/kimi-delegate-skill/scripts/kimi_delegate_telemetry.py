#!/usr/bin/env python3
"""Telemetry store and summaries for kimi-delegate."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def repo_root_from_script() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path(__file__).resolve().parents[3]


def events_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "kimi-delegate" / "events.jsonl"


def record_event(repo_root: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    path = events_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_events(repo_root: Path, days: int | None = None) -> list[dict[str, Any]]:
    path = events_path(repo_root)
    if not path.exists():
        return []

    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    events: list[dict[str, Any]] = []
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


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter()
    by_task_class = Counter()
    by_model = Counter()
    fallback_reasons = Counter()

    calls = 0
    fallback_count = 0
    total_latency = 0.0
    latency_count = 0
    total_saved = 0
    total_parent_tokens = 0

    for ev in events:
        if ev.get("event") != "delegate_invocation":
            continue
        calls += 1
        by_status[str(ev.get("status", "unknown"))] += 1
        by_task_class[str(ev.get("task_class", "unknown"))] += 1
        by_model[str(ev.get("model_used", "unknown"))] += 1

        if ev.get("fallback_used"):
            fallback_count += 1
            fallback_reasons[str(ev.get("fallback_reason", "unknown"))] += 1

        latency = ev.get("latency_ms")
        if isinstance(latency, (int, float)) and float(latency) >= 0:
            total_latency += float(latency)
            latency_count += 1

        saved = ev.get("estimated_tokens_saved")
        if isinstance(saved, int):
            total_saved += saved

        parent_tokens = ev.get("parent_context_tokens")
        if isinstance(parent_tokens, int) and parent_tokens > 0:
            total_parent_tokens += parent_tokens

    savings_pct = round((total_saved * 100.0 / total_parent_tokens), 2) if total_parent_tokens else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "delegate_calls": calls,
        "status": dict(by_status),
        "task_classes": dict(by_task_class),
        "models": dict(by_model),
        "fallback_rate_pct": round((fallback_count * 100.0 / calls), 2) if calls else 0.0,
        "fallback_reasons": dict(fallback_reasons),
        "avg_latency_ms": round(total_latency / latency_count, 2) if latency_count else 0.0,
        "estimated_tokens_saved": total_saved,
        "estimated_savings_pct": savings_pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record")
    record.add_argument("--event", default="delegate_invocation")
    record.add_argument("--status", default="ok")
    record.add_argument("--task-class", default="unknown")
    record.add_argument("--model-used", default="unknown")
    record.add_argument("--fallback-used", action="store_true")
    record.add_argument("--fallback-reason", default="")
    record.add_argument("--parent-context-tokens", type=int, default=0)
    record.add_argument("--delegate-input-tokens", type=int, default=0)
    record.add_argument("--delegate-output-tokens", type=int, default=0)
    record.add_argument("--estimated-tokens-saved", type=int, default=0)
    record.add_argument("--latency-ms", type=float, default=0.0)
    record.add_argument("--meta", default="")

    summary = sub.add_parser("summary")
    summary.add_argument("--days", type=int, default=14)

    args = parser.parse_args()
    root = repo_root_from_script()

    if args.command == "record":
        meta: dict[str, Any] = {}
        if args.meta:
            try:
                meta = json.loads(args.meta)
            except json.JSONDecodeError:
                meta = {"raw": args.meta}

        payload = {
            "event": args.event,
            "status": args.status,
            "task_class": args.task_class,
            "model_used": args.model_used,
            "fallback_used": bool(args.fallback_used),
            "fallback_reason": args.fallback_reason,
            "parent_context_tokens": args.parent_context_tokens,
            "delegate_input_tokens": args.delegate_input_tokens,
            "delegate_output_tokens": args.delegate_output_tokens,
            "estimated_tokens_saved": args.estimated_tokens_saved,
            "latency_ms": args.latency_ms,
            "meta": meta,
        }
        record_event(root, payload)
        print(json.dumps({"ok": True, "path": str(events_path(root))}, indent=2))
        return 0

    events = load_events(root, days=args.days)
    print(json.dumps(summarize(events), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
