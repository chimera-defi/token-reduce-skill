#!/usr/bin/env python3
"""Measure token-reduction adoption from Claude and Codex session logs."""
from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from token_reduce_telemetry import load_events, summarize_events


QMD_RE = re.compile(r"\bqmd\s+search\b")
TOKEN_REDUCE_SEARCH_RE = re.compile(
    r"(?:^|/)(?:\.claude/)?token-reduce-(?:search|paths|snippet|adaptive)(?:\.sh)?\b|\btoken-reduce-(?:search|paths|snippet|adaptive)(?:\.sh)?\b"
)
TOKEN_REDUCE_STRUCTURAL_RE = re.compile(
    r"(?:^|/)(?:\.claude/)?token-reduce-structural(?:\.py)?\b|\btoken-reduce-structural(?:\.py)?\b"
)
SCOPED_RG_RE = re.compile(r"\brg\b(?=.*(?:\s-g\s|\s--glob\s))(?!.*\s--files\b)")
RG_FILES_BROAD_RE = re.compile(r"\brg\b.*\s--files(?:\s+\.|\s*$)")
TARGETED_BASH_RE = re.compile(r"\b(head|tail)\b|\bsed\s+-n\b|\bqmd\s+get\b")
BROAD_SCAN_RE = re.compile(r"\bfind\s+(\.|/)|\bls\s+-R\b|\bgrep\s+-R\b|\bgrep\s+--recursive\b")
TOKEN_REDUCE_RE = re.compile(r"token-reduce|/token-reduce", re.IGNORECASE)
CAVEMAN_RE = re.compile(r"(?:^|[^a-z])(?:caveman|/caveman|\$caveman)(?:[^a-z]|$)", re.IGNORECASE)
HEADROOM_RE = re.compile(r"(?:^|[^a-z])headroom(?:[^a-z]|$)", re.IGNORECASE)
GH_AXI_RE = re.compile(r"\bgh-axi\b")
CHROME_DEVTOOLS_AXI_RE = re.compile(r"\bchrome-devtools-axi\b")
CAVEMAN_COMMAND_RE = re.compile(
    r"(?:(?:/|\$)caveman(?:-cn|-es)?(?:\s+\w+|:compress)?|caveman:compress)",
    re.IGNORECASE,
)
HEADROOM_COMMAND_RE = re.compile(
    r"(?:^|\s)(?:uvx\s+.*?\s)?headroom(?:\s+--[\w-]+(?:=\S+)?)*\s+(?:install|proxy|wrap|compress|retrieve)\b|(?:^|\s)headroom\s+(?:--version|--help)\b",
    re.IGNORECASE,
)
HEADROOM_TOOL_RE = re.compile(r"(?:^|__)headroom(?:__|_|-)?(?:compress|retrieve|stats)?\b", re.IGNORECASE)
RG_OPTIONS_WITH_VALUE = {
    "-e",
    "--regexp",
    "-f",
    "--file",
    "-g",
    "--glob",
    "-t",
    "--type",
    "-T",
    "--type-not",
    "-m",
    "--max-count",
    "-A",
    "-B",
    "-C",
    "--max-filesize",
    "--max-columns",
    "--max-depth",
    "--threads",
    "--sort",
    "--sortr",
}
RG_PATTERN_OPTIONS_WITH_VALUE = {"-e", "--regexp", "-f", "--file"}


def repo_session_roots(scope: str, repo_root: str) -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    if scope == "global":
        return [base]
    repo_slug = "-" + Path(repo_root).resolve().as_posix().lstrip("/").replace("/", "-")
    return sorted(
        p for p in base.glob(f"{repo_slug}*") if p.exists()
    )


def top_level_session_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.glob("*.jsonl")
        if p.is_file()
    )


def session_related_files(session_file: Path) -> list[Path]:
    files = [session_file]
    subagent_dir = session_file.with_suffix("") / "subagents"
    if subagent_dir.exists():
        files.extend(sorted(subagent_dir.glob("*.jsonl")))
    return files


def codex_session_roots() -> list[Path]:
    root = Path.home() / ".codex" / "sessions"
    return [root] if root.exists() else []


def codex_session_files(scope: str, repo_root: str) -> list[Path]:
    roots = codex_session_roots()
    if not roots:
        return []

    repo_prefix = Path(repo_root).resolve().as_posix()
    matches: list[Path] = []
    for root in roots:
        for session_file in root.rglob("*.jsonl"):
            try:
                if codex_session_matches_repo(session_file, scope, repo_prefix):
                    matches.append(session_file)
            except OSError:
                continue
    return sorted(matches)


def codex_session_matches_repo(session_file: Path, scope: str, repo_prefix: str) -> bool:
    if scope == "global":
        return True

    try:
        lines = session_file.read_text(errors="ignore").splitlines()
    except OSError:
        return False

    for line in lines[:40]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload", {})
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.startswith(repo_prefix):
            return True
    return False


def fresh_metrics(source: str) -> dict:
    return {
        "source": source,
        "qmd_search": False,
        "token_reduce_search": False,
        "scoped_rg": False,
        "targeted_reads": False,
        "structural_helper": False,
        "subagents": False,
        "token_reduce_mention": False,
        "caveman_mention": False,
        "caveman_command": False,
        "headroom_mention": False,
        "headroom_command": False,
        "axi_tool": False,
        "gh_axi_tool": False,
        "chrome_devtools_axi_tool": False,
        "broad_scan_violation": False,
        "first_discovery_compliant": False,
        "first_discovery_seen": False,
        "first_discovery_kind": "unknown",
        "discovery_outcome": "none",
        "helper_used_before_broad_scan": False,
    }


def note_first_discovery(metrics: dict, compliant: bool, kind: str) -> None:
    if not metrics["first_discovery_seen"]:
        metrics["first_discovery_seen"] = True
        metrics["first_discovery_compliant"] = compliant
        metrics["first_discovery_kind"] = kind


def apply_text_metrics(metrics: dict, text: str) -> None:
    if TOKEN_REDUCE_RE.search(text):
        metrics["token_reduce_mention"] = True
    if CAVEMAN_RE.search(text):
        metrics["caveman_mention"] = True
    if CAVEMAN_COMMAND_RE.search(text):
        metrics["caveman_command"] = True
    if HEADROOM_RE.search(text):
        metrics["headroom_mention"] = True


def classify_discovery_outcome(metrics: dict) -> None:
    """Classify what happened after a helper invocation in a session."""
    helper = helper_used(metrics)
    broad = metrics["broad_scan_violation"]
    targeted = metrics["targeted_reads"]
    if helper:
        if broad and not targeted:
            metrics["discovery_outcome"] = "miss"
        elif broad and targeted:
            metrics["discovery_outcome"] = "indirect_hit"
        elif targeted:
            metrics["discovery_outcome"] = "direct_hit"
        else:
            metrics["discovery_outcome"] = "standoff"
    else:
        if broad:
            metrics["discovery_outcome"] = "bypass"
        elif targeted:
            metrics["discovery_outcome"] = "direct"
        else:
            metrics["discovery_outcome"] = "none"


def apply_command_metrics(metrics: dict, command: str) -> None:
    if QMD_RE.search(command):
        metrics["qmd_search"] = True
        note_first_discovery(metrics, True, "qmd_search")
    if TOKEN_REDUCE_SEARCH_RE.search(command):
        metrics["token_reduce_search"] = True
        note_first_discovery(metrics, True, "token_reduce_search")
    if TOKEN_REDUCE_STRUCTURAL_RE.search(command):
        metrics["structural_helper"] = True
        note_first_discovery(metrics, True, "structural_helper")
    if GH_AXI_RE.search(command):
        metrics["axi_tool"] = True
        metrics["gh_axi_tool"] = True
    if CHROME_DEVTOOLS_AXI_RE.search(command):
        metrics["axi_tool"] = True
        metrics["chrome_devtools_axi_tool"] = True
    if CAVEMAN_COMMAND_RE.search(command):
        metrics["caveman_command"] = True
    if HEADROOM_COMMAND_RE.search(command):
        metrics["headroom_command"] = True
    if SCOPED_RG_RE.search(command):
        metrics["scoped_rg"] = True
        note_first_discovery(metrics, True, "scoped_rg")
    if TARGETED_BASH_RE.search(command):
        metrics["targeted_reads"] = True
    if BROAD_SCAN_RE.search(command) or RG_FILES_BROAD_RE.search(command) or is_exploratory_rg(command):
        metrics["broad_scan_violation"] = True
        note_first_discovery(metrics, False, "broad_scan")
    # Track C: additional advisory broad patterns (kept in sync with enforce hook).
    from coverage_patterns import matches_any_broad_pattern
    if matches_any_broad_pattern(command):
        metrics["broad_scan_violation"] = True
        note_first_discovery(metrics, False, "broad_scan")


def apply_tool_name_metrics(metrics: dict, tool_name: str) -> None:
    if HEADROOM_TOOL_RE.search(tool_name):
        metrics["headroom_command"] = True


def helper_used(metrics: dict) -> bool:
    return bool(metrics.get("token_reduce_search") or metrics.get("structural_helper"))


def rg_paths(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if not tokens or tokens[0] != "rg":
        return []

    paths: list[str] = []
    saw_pattern = False
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            tail = tokens[i + 1 :]
            if not saw_pattern and tail:
                saw_pattern = True
                tail = tail[1:]
            paths.extend(tail)
            break

        if token.startswith("-"):
            if token in RG_OPTIONS_WITH_VALUE:
                if token in RG_PATTERN_OPTIONS_WITH_VALUE:
                    saw_pattern = True
                i += 2
                continue
            if (
                token.startswith("--glob=")
                or token.startswith("--regexp=")
                or token.startswith("--type=")
                or token.startswith("--type-not=")
                or token.startswith("--file=")
                or token.startswith("-g")
                or token.startswith("-e")
            ):
                if token.startswith("--regexp=") or token.startswith("--file=") or token.startswith("-e") or token.startswith("-f"):
                    saw_pattern = True
                i += 1
                continue
            i += 1
            continue

        if not saw_pattern:
            saw_pattern = True
        else:
            paths.append(token)
        i += 1

    return paths


def is_exploratory_rg(command: str) -> bool:
    text = command.strip()
    if not text.startswith("rg "):
        return False
    if re.search(r"(?:^|\s)(?:-g|--glob)(?:\s|=)", text):
        return False
    if re.search(r"(?:^|\s)(?:--files|--files-with-matches|--files-without-match)\b", text):
        return True

    paths = rg_paths(text)
    if not paths:
        return True

    for raw_path in paths:
        if raw_path in {".", "./"}:
            return True
        if any(ch in raw_path for ch in "*?["):
            return True
        if "." not in Path(raw_path).name:
            return True

    return False


def parse_claude_session(session_file: Path) -> dict:
    metrics = fresh_metrics("claude")

    for path in session_related_files(session_file):
        if path != session_file:
            metrics["subagents"] = True
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = event.get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                apply_text_metrics(metrics, content)

            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        apply_text_metrics(metrics, item.get("text", ""))
                    if item.get("type") != "tool_use":
                        continue

                    name = item.get("name")
                    tool_input = item.get("input", {})
                    if isinstance(name, str):
                        apply_tool_name_metrics(metrics, name)

                    if name == "Read":
                        if tool_input.get("limit") is not None or tool_input.get("offset") is not None:
                            metrics["targeted_reads"] = True
                        note_first_discovery(metrics, True, "targeted_read")

                    if name == "Bash":
                        command = tool_input.get("command", "")
                        apply_command_metrics(metrics, command)

                    if name == "Glob":
                        pattern = tool_input.get("pattern", "")
                        if "**/*" in pattern or pattern.startswith("**/"):
                            note_first_discovery(metrics, False, "broad_scan")
                            metrics["broad_scan_violation"] = True

    classify_discovery_outcome(metrics)
    return metrics


def parse_codex_session(session_file: Path) -> dict:
    metrics = fresh_metrics("codex")
    try:
        lines = session_file.read_text(errors="ignore").splitlines()
    except OSError:
        return metrics

    for line in lines:
        apply_text_metrics(metrics, line)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = event.get("payload", {})
        event_type = payload.get("type")

        if event_type == "function_call" and payload.get("name") == "exec_command":
            apply_tool_name_metrics(metrics, str(payload.get("name", "")))
            arguments_raw = payload.get("arguments", "{}")
            try:
                arguments = json.loads(arguments_raw)
            except json.JSONDecodeError:
                arguments = {}
            command = arguments.get("cmd", "")
            apply_command_metrics(metrics, command)
        elif event_type == "function_call":
            apply_tool_name_metrics(metrics, str(payload.get("name", "")))

    classify_discovery_outcome(metrics)
    return metrics


def measure(scope: str, repo_root: str) -> dict:
    claude_session_files: list[Path] = []
    for root in repo_session_roots(scope, repo_root):
        claude_session_files.extend(top_level_session_files(root))
    codex_files = codex_session_files(scope, repo_root)

    parsed = [parse_claude_session(p) for p in claude_session_files]
    parsed.extend(parse_codex_session(p) for p in codex_files)
    session_count = len(parsed)

    adoption = defaultdict(int)
    for key in (
        "qmd_search_sessions",
        "token_reduce_search_sessions",
        "scoped_rg_sessions",
        "targeted_read_sessions",
        "subagent_sessions",
        "token_reduce_mentions",
        "caveman_mentions",
        "caveman_command_sessions",
        "headroom_mentions",
        "headroom_command_sessions",
        "axi_tool_sessions",
        "gh_axi_sessions",
        "chrome_devtools_axi_sessions",
        "helper_sessions",
        "structural_helper_sessions",
        "mention_without_helper_sessions",
        "mention_without_helper_sessions_observed",
        "discovery_outcome_direct_hit_sessions",
        "discovery_outcome_indirect_hit_sessions",
        "discovery_outcome_miss_sessions",
        "discovery_outcome_standoff_sessions",
        "discovery_outcome_bypass_sessions",
        "discovery_outcome_direct_sessions",
    ):
        adoption[key] = 0
    per_source = defaultdict(lambda: defaultdict(int))
    discovery_kinds = defaultdict(int)
    compliant_sessions = 0
    broad_violation_sessions = 0
    broad_violation_count = 0
    observed_discovery_sessions = 0
    for item in parsed:
        adoption["qmd_search_sessions"] += int(item["qmd_search"])
        adoption["token_reduce_search_sessions"] += int(item["token_reduce_search"])
        adoption["scoped_rg_sessions"] += int(item["scoped_rg"])
        adoption["targeted_read_sessions"] += int(item["targeted_reads"])
        adoption["subagent_sessions"] += int(item["subagents"])
        adoption["token_reduce_mentions"] += int(item["token_reduce_mention"])
        adoption["caveman_mentions"] += int(item["caveman_mention"])
        adoption["caveman_command_sessions"] += int(item["caveman_command"])
        adoption["headroom_mentions"] += int(item["headroom_mention"])
        adoption["headroom_command_sessions"] += int(item["headroom_command"])
        adoption["axi_tool_sessions"] += int(item["axi_tool"])
        adoption["gh_axi_sessions"] += int(item["gh_axi_tool"])
        adoption["chrome_devtools_axi_sessions"] += int(item["chrome_devtools_axi_tool"])
        helper_session = helper_used(item)
        adoption["helper_sessions"] += int(helper_session)
        adoption["structural_helper_sessions"] += int(item["structural_helper"])
        adoption["mention_without_helper_sessions"] += int(
            item["token_reduce_mention"] and not helper_session
        )
        adoption["mention_without_helper_sessions_observed"] += int(
            item["token_reduce_mention"] and item["first_discovery_seen"] and not helper_session
        )
        adoption["discovery_outcome_direct_hit_sessions"] += int(item["discovery_outcome"] == "direct_hit")
        adoption["discovery_outcome_indirect_hit_sessions"] += int(item["discovery_outcome"] == "indirect_hit")
        adoption["discovery_outcome_miss_sessions"] += int(item["discovery_outcome"] == "miss")
        adoption["discovery_outcome_standoff_sessions"] += int(item["discovery_outcome"] == "standoff")
        adoption["discovery_outcome_bypass_sessions"] += int(item["discovery_outcome"] == "bypass")
        adoption["discovery_outcome_direct_sessions"] += int(item["discovery_outcome"] == "direct")
        observed_discovery_sessions += int(item["first_discovery_seen"])
        compliant_sessions += int(item["first_discovery_compliant"])
        broad_violation_sessions += int(item["broad_scan_violation"])
        broad_violation_count += int(item["broad_scan_violation"])
        discovery_kinds[item["first_discovery_kind"]] += 1

        source = str(item["source"])
        per_source[source]["sessions"] += 1
        per_source[source]["helper_sessions"] += int(helper_session)
        per_source[source]["compliant_sessions"] += int(item["first_discovery_compliant"])
        per_source[source]["broad_scan_sessions"] += int(item["broad_scan_violation"])
        per_source[source]["caveman_command_sessions"] += int(item["caveman_command"])
        per_source[source]["headroom_command_sessions"] += int(item["headroom_command"])
        per_source[source]["axi_tool_sessions"] += int(item["axi_tool"])

    pct = lambda n: round((n * 100.0 / session_count), 1) if session_count else 0.0
    pct_observed = (
        lambda n: round((n * 100.0 / observed_discovery_sessions), 1)
        if observed_discovery_sessions
        else 0.0
    )
    telemetry = summarize_events(load_events(Path(repo_root).resolve(), days=14))
    telemetry_1d = summarize_events(load_events(Path(repo_root).resolve(), days=1))

    def telemetry_window_snapshot(summary: dict) -> dict:
        efficiency = summary.get("efficiency", {})
        logging = summary.get("logging", {})
        return {
            "event_count": int(summary.get("event_count", 0) or 0),
            "helper_calls": int(efficiency.get("helper_calls", 0) or 0),
            "helper_latency_p95_ms": float(efficiency.get("helper_latency_p95_ms", 0.0) or 0.0),
            "failure_overhead_pct": float(efficiency.get("failure_overhead_pct", 0.0) or 0.0),
            "logging_quality_score": float(logging.get("logging_quality_score", 0.0) or 0.0),
            "logging_quality_tier": str(logging.get("logging_quality_tier", "no_data")),
        }

    by_source_payload = {}
    for source, counts in sorted(per_source.items()):
        source_sessions = counts["sessions"]
        by_source_payload[source] = {
            "sessions": source_sessions,
            "helper_first_or_helper_any_pct": round(
                (counts["helper_sessions"] * 100.0 / source_sessions), 1
            )
            if source_sessions
            else 0.0,
            "discovery_compliance_pct": round(
                (counts["compliant_sessions"] * 100.0 / source_sessions), 1
            )
            if source_sessions
            else 0.0,
            "broad_scan_pct": round((counts["broad_scan_sessions"] * 100.0 / source_sessions), 1)
            if source_sessions
            else 0.0,
            "caveman_command_pct": round(
                (counts["caveman_command_sessions"] * 100.0 / source_sessions), 1
            )
            if source_sessions
            else 0.0,
            "headroom_command_pct": round(
                (counts["headroom_command_sessions"] * 100.0 / source_sessions), 1
            )
            if source_sessions
            else 0.0,
            "axi_tool_pct": round((counts["axi_tool_sessions"] * 100.0 / source_sessions), 1)
            if source_sessions
            else 0.0,
        }

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "repo_root": repo_root,
        "session_count": session_count,
        "sources": {
            "claude_sessions": len(claude_session_files),
            "codex_sessions": len(codex_files),
        },
        "adoption": {
            **adoption,
            "qmd_search_pct": pct(adoption["qmd_search_sessions"]),
            "token_reduce_search_pct": pct(adoption["token_reduce_search_sessions"]),
            "scoped_rg_pct": pct(adoption["scoped_rg_sessions"]),
            "targeted_read_pct": pct(adoption["targeted_read_sessions"]),
            "subagent_pct": pct(adoption["subagent_sessions"]),
            "token_reduce_mention_pct": pct(adoption["token_reduce_mentions"]),
            "caveman_mention_pct": pct(adoption["caveman_mentions"]),
            "caveman_command_pct": pct(adoption["caveman_command_sessions"]),
            "headroom_mention_pct": pct(adoption["headroom_mentions"]),
            "headroom_command_pct": pct(adoption["headroom_command_sessions"]),
            "axi_tool_sessions_pct": pct(adoption["axi_tool_sessions"]),
            "gh_axi_sessions_pct": pct(adoption["gh_axi_sessions"]),
            "chrome_devtools_axi_sessions_pct": pct(adoption["chrome_devtools_axi_sessions"]),
            "helper_sessions_pct": pct(adoption["helper_sessions"]),
            "helper_sessions_pct_observed_discovery": pct_observed(adoption["helper_sessions"]),
            "structural_helper_sessions_pct": pct(adoption["structural_helper_sessions"]),
            "mention_without_helper_pct": pct(adoption["mention_without_helper_sessions"]),
            "mention_without_helper_pct_observed_discovery": pct_observed(
                adoption["mention_without_helper_sessions_observed"]
            ),
            "discovery_outcome_direct_hit_pct": pct(adoption["discovery_outcome_direct_hit_sessions"]),
            "discovery_outcome_indirect_hit_pct": pct(adoption["discovery_outcome_indirect_hit_sessions"]),
            "discovery_outcome_miss_pct": pct(adoption["discovery_outcome_miss_sessions"]),
            "discovery_outcome_standoff_pct": pct(adoption["discovery_outcome_standoff_sessions"]),
            "discovery_outcome_bypass_pct": pct(adoption["discovery_outcome_bypass_sessions"]),
            "discovery_outcome_direct_pct": pct(adoption["discovery_outcome_direct_sessions"]),
        },
        "compliance": {
            "sessions_with_compliant_first_discovery": compliant_sessions,
            "sessions_with_first_discovery_observed": observed_discovery_sessions,
            "sessions_without_first_discovery_observed": max(0, session_count - observed_discovery_sessions),
            "sessions_with_broad_scan_violation": broad_violation_sessions,
            "broad_scan_violations": broad_violation_count,
            "discovery_compliance_pct": pct(compliant_sessions),
            "discovery_compliance_pct_observed": pct_observed(compliant_sessions),
        },
        "routing": {
            "first_discovery_kind_counts": dict(sorted(discovery_kinds.items())),
            "helper_first_or_helper_any_pct": pct(adoption["helper_sessions"]),
            "observed_discovery_sessions_pct": pct(observed_discovery_sessions),
        },
        "by_source": by_source_payload,
        "telemetry": telemetry,
        "telemetry_windows": {
            "1d": telemetry_window_snapshot(telemetry_1d),
            "14d": telemetry_window_snapshot(telemetry),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["repo", "global"], default="repo")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = measure(args.scope, args.repo_root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
