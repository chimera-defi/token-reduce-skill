#!/usr/bin/env python3
"""Read-only context evidence. Local token counts are not provider occupancy."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from token_reduce_config import layer_mode


def counter():
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return lambda text: len(encoding.encode(text, disallowed_special=())), "measured_local_cl100k_base"
    except ImportError:
        return lambda text: None, "unmeasured_tokenizer_unavailable"


def text_of(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_of(item) for item in value)
    if isinstance(value, dict):
        return text_of(value.get("text", value.get("content", "")))
    return ""


def server_name(name: str) -> str:
    parts = name.split("__", 2)
    return parts[1] if len(parts) == 3 and parts[0] == "mcp" else "builtin_or_unknown"


def audit(transcript: Path | None, *, budget: int | None = None, max_bytes: int = 64 * 1024 * 1024) -> dict:
    count, method = counter()
    snapshots: dict[str, tuple[str, str | None]] = {}
    instructions = {}
    skills = {}
    definitions = {}
    deferred_lines = {}
    calls = Counter()
    seen_tool_calls = set()
    usages = {}
    latest = None
    errors = 0
    truncated = False
    processed = 0
    if transcript is not None:
        with transcript.open("rb") as stream:
            for raw in stream:
                processed += len(raw)
                if processed > max_bytes:
                    truncated = True
                    break
                try:
                    row = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    errors += 1
                    continue
                if not isinstance(row, dict):
                    errors += 1
                    continue
                stamp = row.get("timestamp")
                attachment = row.get("attachment") or {}
                if not isinstance(attachment, dict):
                    attachment = {}
                kind = attachment.get("type")
                if kind == "prompt_snapshot":
                    snapshots["system_prompt"] = (text_of(attachment.get("systemPrompt")), stamp)
                elif kind == "skill_listing":
                    snapshots["skill_catalog"] = (text_of(attachment.get("content")), stamp)
                elif kind == "instructions":
                    for item in attachment.get("files", []):
                        if isinstance(item, dict):
                            path = str(item.get("path", "unknown"))
                            category = "memory" if "memory" in path.lower() else "rules_claude_md"
                            instructions[path] = (category, text_of(item.get("content")), stamp)
                elif kind == "invoked_skills":
                    for item in attachment.get("skills", []):
                        if isinstance(item, dict):
                            skills[str(item.get("name", "unknown"))] = (text_of(item.get("content")), stamp)
                elif kind == "deferred_tools_record":
                    for tool in attachment.get("entries", []):
                        if isinstance(tool, dict) and isinstance(tool.get("name"), str) and "input_schema" in tool:
                            definitions[tool["name"]] = (tool, stamp)
                elif kind == "deferred_tools_delta":
                    for name in attachment.get("removedNames", []):
                        deferred_lines.pop(name, None)
                        definitions.pop(name, None)
                    for name, line in zip(attachment.get("addedNames", []), attachment.get("addedLines", [])):
                        deferred_lines[str(name)] = (text_of(line), stamp)
                message = row.get("message") or {}
                if not isinstance(message, dict):
                    continue
                if row.get("type") == "assistant":
                    content = message.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                identity = block.get("id") or (row.get("uuid"), str(block.get("name")))
                                if identity not in seen_tool_calls:
                                    seen_tool_calls.add(identity)
                                    calls[str(block.get("name", "unknown"))] += 1
                    usage = message.get("usage")
                    if isinstance(usage, dict):
                        fields = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
                        if all(isinstance(usage.get(k, 0), int) for k in fields):
                            # Provider input occupancy includes cached input, once per response.
                            item = {"timestamp": stamp, "input_tokens": sum(usage.get(k, 0) for k in fields),
                                    "fields": {k: usage.get(k, 0) for k in fields}, "model": message.get("model")}
                            key = message.get("id") or row.get("uuid") or str(len(usages))
                            usages[key] = item
                            latest = item

    def measured(text: str, stamp=None):
        return {"bytes": len(text.encode("utf-8")), "tokens": count(text), "measurement": method,
                "timestamp": stamp, "scope": "observed artifact; not current provider occupancy"}

    categories = {name: {"tokens": None, "measurement": "unobserved", "reason": "not present in selected transcript"}
                  for name in ["system_prompt", "skill_catalog", "invoked_skills", "rules_claude_md", "memory", "deferred_tool_list", "mcp_tool_schemas"]}
    for name, (text, stamp) in snapshots.items():
        categories[name] = measured(text, stamp)
    offenders = []
    for category in ["rules_claude_md", "memory"]:
        entries = [(path, text, stamp) for path, (cat, text, stamp) in instructions.items() if cat == category]
        if entries:
            categories[category] = measured("\n".join(text for _, text, _ in entries))
            for path, text, stamp in entries:
                offenders.append({"category": category, "source": path, **measured(text, stamp)})
    if skills:
        categories["invoked_skills"] = measured("\n".join(text for text, _ in skills.values()))
        for name, (text, stamp) in skills.items():
            offenders.append({"category": "invoked_skills", "source": name, **measured(text, stamp)})
    if deferred_lines:
        categories["deferred_tool_list"] = measured("\n".join(text for text, _ in deferred_lines.values()))
    servers = {}
    for name, (tool, stamp) in definitions.items():
        if not name.startswith("mcp__"):
            continue
        server = server_name(name)
        encoded = json.dumps(tool, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        item = servers.setdefault(server, {"definitions": 0, "bytes": 0, "tokens": 0 if method.startswith("measured") else None,
                                           "deferred_definitions": 0, "observed_tool_calls": 0, "measurement": method})
        metric = measured(encoded, stamp)
        item["definitions"] += 1
        item["bytes"] += metric["bytes"]
        if item["tokens"] is not None:
            item["tokens"] += metric["tokens"]
        item["deferred_definitions"] += bool(tool.get("defer_loading"))
        item["observed_tool_calls"] += calls[name]
    if servers:
        categories["mcp_tool_schemas"] = {"tokens": sum(s["tokens"] for s in servers.values()) if method.startswith("measured") else None,
                                         "bytes": sum(s["bytes"] for s in servers.values()), "measurement": method,
                                         "scope": "observed definition inventory; deferred schemas may not be in prompt"}
    recommendations = []
    for name, item in sorted(servers.items(), key=lambda p: p[1]["bytes"], reverse=True):
        if item["observed_tool_calls"] == 0:
            recommendations.append({"action": f"Review project need for MCP server {name}; disable only after operator approval",
                                    "basis": "zero observed tool calls in selected transcript; not proof unused across projects",
                                    "potential_saved_tokens": None, "operator_approval_required": True})
    if definitions:
        recommendations.append({"action": "Retain deferred loading; review eager tool definitions before reducing schemas",
                                "basis": "observed definition inventory; actual request tools array not captured",
                                "potential_saved_tokens": None, "operator_approval_required": True})
    if instructions or skills:
        recommendations.append({"action": "Review largest rules/skill sources for duplicate guidance and move task details to references",
                                "basis": "observed text bytes/local token counts", "operator_approval_required": True})
    peak = max((u["input_tokens"] for u in usages.values()), default=None)
    return {"schema": "token-reduce-context-audit/v1", "measured_at": datetime.now(timezone.utc).isoformat(),
            "transcript": str(transcript) if transcript else None, "processed_bytes": processed,
            "malformed_records": errors, "scan_truncated": truncated,
            "provider_input": {"latest": latest, "peak_tokens": peak, "responses": len(usages), "measurement": "provider_usage" if latest else "unobserved"},
            "context_budget": {"tokens": budget, "measurement": "assumed_operator_supplied" if budget else "unknown",
                               "latest_utilization_pct": round(100 * latest["input_tokens"] / budget, 2) if latest and budget else None},
            "categories": categories, "mcp_servers": servers,
            "worst_observed_text_sources": sorted(offenders, key=lambda x: x["bytes"], reverse=True)[:10],
            "observed_tool_calls": dict(calls), "recommendations": recommendations,
            "limitations": ["Local cl100k counts measure supplied text, not Anthropic tokens or billed occupancy.",
                            "Snapshots, deltas and definitions may precede compaction or belong to another branch; inventory is not a current request reconstruction.",
                            "Categories overlap, are partial, and must not be summed or subtracted from provider input.",
                            "No global settings, MCP configuration, memory, or transcripts were changed."]}


def hook_text(report: dict) -> str:
    latest = report["provider_input"]["latest"]
    total = latest["input_tokens"] if latest else "unknown"
    schemas = report["categories"]["mcp_tool_schemas"].get("tokens")
    top = sorted(report["mcp_servers"], key=lambda name: report["mcp_servers"][name]["bytes"], reverse=True)[:3]
    return (f"Context audit: provider input={total}; budget={report['context_budget']['tokens'] or 'unknown'} (operator assumption); "
            f"observed MCP definition inventory={schemas if schemas is not None else 'unknown'} local cl100k tokens; largest servers={', '.join(top) or 'unknown'}. "
            "Deferred inventory is not resident prompt cost. Review unused project servers and duplicate rules; changes require operator approval.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hook", action="store_true")
    args = parser.parse_args()
    if args.budget is not None and args.budget <= 0:
        parser.error("budget must be positive")
    if args.hook:
        try:
            if layer_mode("context_audit") != "on":
                return 0
            event = json.load(sys.stdin)
            if not isinstance(event, dict):
                raise ValueError("hook input must be an object")
            report = audit(Path(event["transcript_path"]) if event.get("transcript_path") else None,
                           budget=args.budget, max_bytes=args.max_bytes)
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": hook_text(report)}}))
        except (OSError, ValueError, TypeError):
            # Hook failure never blocks startup and never dumps private contents/errors.
            print("token-reduce: context audit unavailable; run explicit context-audit for evidence", file=sys.stderr)
        return 0
    try:
        report = audit(args.transcript, budget=args.budget, max_bytes=args.max_bytes)
    except OSError:
        parser.error("transcript is unavailable")
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
