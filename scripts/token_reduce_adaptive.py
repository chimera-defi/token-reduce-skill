#!/usr/bin/env python3
"""Adaptive tier router for token-reduce discovery helpers.

This controller promotes or demotes helper tiers based on:
1) query intent (symbol/impact/output-heavy),
2) recent helper behavior (rapid repeats / repeated calls),
3) local tool availability and repo scale.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from token_reduce_config import load_config
from token_reduce_state import clear_pending
from token_reduce_telemetry import load_events, record_event, summarize_events


OUTPUT_HEAVY_TERMS = {
    "log",
    "logs",
    "stacktrace",
    "traceback",
    "playwright",
    "console",
    "screenshot",
    "response",
    "payload",
    "stderr",
    "stdout",
    "tool_result",
    "tool-result",
    "tool-results",
    "transcript",
    "long-session",
    "long-sessions",
}

# Track D2 — widened trigger matrix via multi-word phrases. Bare tokens like
# "api" or "dump" produced too many false positives on innocent queries
# ("where is the api client defined"), so we require a co-occurring noun
# that signals "large tool payload".
OUTPUT_HEAVY_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bapi\s+(response|payload|dump|output|result)s?\b", re.IGNORECASE),
    re.compile(r"\bpytest\s+(output|log|results?|failures?|traceback)\b", re.IGNORECASE),
    re.compile(r"\b(log|json|trace|stack|response|payload|console)\s+dumps?\b", re.IGNORECASE),
    re.compile(r"\bpaste(d)?\s+(log|output|trace|response|payload|json)\b", re.IGNORECASE),
    re.compile(r"\blarge\s+(tool|api)?\s*(output|payload|response|result)s?\b", re.IGNORECASE),
)

# Track D1 — actionable, copy-pasteable commands. Router emits these literal
# strings instead of prose so the caller can run them without translation.
HEADROOM_ACTION_COMMANDS = (
    "headroom install status",
    "curl -fsS http://127.0.0.1:8787/readyz",
    "headroom_compress  # MCP action for >20k-token tool results",
)

# Track E — subagent + gstack integration ----------------------------------- #

# Cues that mean "fan out across the codebase" — even with a small initial
# candidate set, those queries blow up downstream and are cheaper to delegate
# to an Explore subagent than to keep stuffing into the parent context.
BROAD_SCOPE_TERMS = {
    "everywhere",
    "everything",
    "all-files",
    "all_files",
    "across",
    "workspace",
    "repository",
    "repositories",
    "monorepo",
    "codebase-wide",
}

# Cues that imply work spans sibling repos/workspaces — triggers the
# /create-session escalation when gstack-session-spawn is available.
MULTI_REPO_TERMS = {
    "sibling",
    "siblings",
    "monorepo",
    "workspaces",
    "workspace",
    "across",
    "repos",
    "multi-repo",
}

# Track E1 — subagent threshold. Above this candidate count the router
# recommends fanning out via Agent(subagent_type=Explore).
SUBAGENT_CANDIDATE_THRESHOLD = 5

# Track E4 — sibling-skill intent map. (regex, /skill) pairs. First match wins.
SIBLING_SKILL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\breview\b.{0,30}\b(pr|pull\s*request|patch|diff|cl|change)\b", re.IGNORECASE), "/review"),
    (re.compile(r"\b(fix|debug|investigate|root\s*cause|why\s+does|why\s+is)\b", re.IGNORECASE), "/investigate"),
    (re.compile(r"\b(brainstorm|design|architect|propose)\b", re.IGNORECASE), "/brainstorm"),
)


def brain_hint_line(query: str) -> str | None:
    """Return a one-line brain-first hint when qmd or gbrain is on PATH.

    The hint nudges the caller to check semantic memory before doing a
    filesystem scan. Returns ``None`` when neither CLI is available, so
    callers can prepend conditionally without extra checks.
    """
    have_qmd = shutil.which("qmd") is not None
    have_gbrain = shutil.which("gbrain") is not None
    if not (have_qmd or have_gbrain):
        return None
    safe = query.replace('"', '\\"').strip() or "<query>"
    if have_qmd and have_gbrain:
        cmd = f'qmd search "{safe}" -n 5 --files  # or: gbrain search "{safe}"'
    elif have_qmd:
        cmd = f'qmd search "{safe}" -n 5 --files'
    else:
        cmd = f'gbrain search "{safe}"'
    return f"brain hits available — run `{cmd}` before filesystem scan"


def sibling_skill_for_query(query: str) -> str | None:
    """Return a sibling skill name (e.g. ``/review``) when the query
    matches a known intent. Returns ``None`` for plain discovery queries.
    """
    if not query:
        return None
    for pattern, skill in SIBLING_SKILL_PATTERNS:
        if pattern.search(query):
            return skill
    return None


def _subagent_snippet(query: str) -> str:
    """Return a ready-to-copy ``Agent(...)`` snippet for the Explore agent."""
    safe = (query or "").replace('"', '\\"').strip() or "<query>"
    return (
        f'Agent(subagent_type="Explore", description="discover {safe}", '
        f'prompt="Find files and symbols matching: {safe}. '
        'Report a ranked list with paths and 1-line summaries.")'
    )
IMPACT_TERMS = {
    "impact",
    "blast",
    "dependency",
    "dependencies",
    "caller",
    "callee",
    "upstream",
    "downstream",
    "affected",
    "change-impact",
}
SNIPPET_HINT_TERMS = {
    "why",
    "how",
    "explain",
    "debug",
    "reason",
    "trace",
}
SYMBOL_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:.]*")


@dataclass
class BehaviorProfile:
    helper_calls: int
    repeated_ratio: float
    rapid_repeat_ratio: float


@dataclass
class Availability:
    paths: bool
    snippet: bool
    structural: bool
    context_mode: bool
    headroom: bool
    code_review_graph: bool


@dataclass
class Decision:
    tier: str
    command: list[str]
    rationale: list[str]
    context_mode_recommended: bool
    headroom_recommended: bool
    code_review_graph_recommended: bool
    symbol: str
    behavior: BehaviorProfile
    repo_file_count: int
    headroom_commands: list[str] = field(default_factory=list)
    subagent_recommended: bool = False
    subagent_snippet: str = ""
    session_spawn_recommended: bool = False
    sibling_skill: str = ""


@dataclass
class RoutingPolicy:
    behavior_days: int
    rapid_repeat_snippet_threshold: float
    enable_structural: bool
    enable_context_mode_recommendations: bool
    enable_headroom_recommendations: bool
    enable_code_review_graph_recommendations: bool


def repo_root() -> Path:
    base = Path(os.environ.get("TOKEN_REDUCE_REPO_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    proc = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        capture_output=True,
    )
    root = (proc.stdout or "").strip()
    return Path(root).resolve() if root else base.resolve()


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def count_repo_files(root: Path) -> int:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode == 0 and proc.stdout:
        return len([line for line in proc.stdout.splitlines() if line.strip()])
    fallback = subprocess.run(
        ["rg", "--files", str(root)],
        check=False,
        text=True,
        capture_output=True,
    )
    if fallback.returncode == 0:
        return len([line for line in fallback.stdout.splitlines() if line.strip()])
    return 0


def collect_availability() -> Availability:
    sdir = script_dir()
    structural_backend_available = importlib.util.find_spec("token_savior") is not None
    return Availability(
        paths=(sdir / "token-reduce-paths.sh").exists() or shutil.which("token-reduce-paths") is not None,
        snippet=(sdir / "token-reduce-snippet.sh").exists() or shutil.which("token-reduce-snippet") is not None,
        structural=structural_backend_available
        and (shutil.which("token-reduce-structural") is not None or (sdir / "token-reduce-structural.py").exists()),
        context_mode=shutil.which("context-mode") is not None,
        headroom=shutil.which("headroom") is not None,
        code_review_graph=shutil.which("code-review-graph") is not None,
    )


def structural_command() -> str:
    installed = shutil.which("token-reduce-structural")
    if installed:
        return installed
    return str(script_dir() / "token-reduce-structural.py")


def load_behavior_profile(root: Path, *, days: int = 3) -> BehaviorProfile:
    if days <= 0:
        return BehaviorProfile(helper_calls=0, repeated_ratio=0.0, rapid_repeat_ratio=0.0)
    summary = summarize_events(load_events(root, days=days))
    efficiency = summary.get("efficiency", {})
    helper_calls = int(efficiency.get("helper_calls", 0) or 0)
    repeated = int(efficiency.get("repeated_helper_calls", 0) or 0)
    rapid = int(efficiency.get("rapid_repeat_calls", 0) or 0)
    if helper_calls <= 0:
        return BehaviorProfile(helper_calls=0, repeated_ratio=0.0, rapid_repeat_ratio=0.0)
    return BehaviorProfile(
        helper_calls=helper_calls,
        repeated_ratio=round(repeated / helper_calls, 3),
        rapid_repeat_ratio=round(rapid / helper_calls, 3),
    )


def query_terms(query: str) -> set[str]:
    return {tok.lower() for tok in re.findall(r"[A-Za-z0-9_:-]+", query)}


def extract_symbol(query: str) -> str:
    candidates = SYMBOL_TOKEN_RE.findall(query)
    preferred = [
        token
        for token in candidates
        if "_" in token or "::" in token or (any(char.isupper() for char in token[1:]) and token[0].islower())
    ]
    if preferred:
        return preferred[0]
    if len(candidates) == 1:
        return candidates[0]
    return ""


def decide(
    query: str,
    *,
    behavior: BehaviorProfile,
    availability: Availability,
    policy: RoutingPolicy,
    root: Path,
    repo_file_count: int,
    candidate_count: int = 0,
    gstack_skill_available: bool = False,
) -> Decision:
    terms = query_terms(query)
    symbol = extract_symbol(query)
    output_heavy = bool(terms & OUTPUT_HEAVY_TERMS) or any(
        pat.search(query) for pat in OUTPUT_HEAVY_PHRASE_PATTERNS
    )
    impact_like = bool(terms & IMPACT_TERMS)
    snippet_hint = bool(terms & SNIPPET_HINT_TERMS)

    rationale: list[str] = []
    tier = "core_paths"
    command: list[str] = [str(script_dir() / "token-reduce-paths.sh"), query]

    structural_enabled = availability.structural and policy.enable_structural

    if symbol and structural_enabled:
        if impact_like:
            tier = "structural_impact"
            command = [structural_command(), "--project-root", str(root), "change-impact", symbol]
            rationale.append("symbol+impact query promoted to structural impact tier")
        else:
            tier = "structural_symbol"
            command = [structural_command(), "--project-root", str(root), "find-symbol", symbol]
            rationale.append("symbol-like query promoted to structural symbol tier")
    elif impact_like and structural_enabled:
        tier = "structural_search"
        command = [structural_command(), "--project-root", str(root), "search", query]
        rationale.append("impact query promoted to structural search tier")
    elif availability.snippet and (
        snippet_hint or behavior.rapid_repeat_ratio >= policy.rapid_repeat_snippet_threshold
    ):
        tier = "core_snippet"
        command = [str(script_dir() / "token-reduce-snippet.sh"), query]
        if snippet_hint:
            rationale.append("debug/explain style query promoted to snippet tier")
        else:
            rationale.append("rapid repeat behavior promoted to snippet tier")
    else:
        rationale.append("defaulting to path-only tier")

    if not structural_enabled and tier.startswith("structural"):
        tier = "core_paths"
        command = [str(script_dir() / "token-reduce-paths.sh"), query]
        rationale.append("structural helper unavailable; demoted to path-only tier")

    context_mode_recommended = (
        policy.enable_context_mode_recommendations and output_heavy and availability.context_mode
    )
    headroom_recommended = (
        policy.enable_headroom_recommendations and output_heavy and availability.headroom
    )
    code_review_graph_recommended = (
        policy.enable_code_review_graph_recommendations
        and impact_like
        and availability.code_review_graph
        and repo_file_count >= 2000
    )
    if context_mode_recommended:
        rationale.append("output-heavy terms detected; context-mode recommended for follow-up tool output")
    headroom_commands: list[str] = []
    if headroom_recommended:
        headroom_commands = list(HEADROOM_ACTION_COMMANDS)
        # D1: emit copy-pasteable commands instead of prose
        rationale.append(
            "headroom recommended; run: "
            + " ; ".join(headroom_commands)
        )
    if code_review_graph_recommended:
        rationale.append("large repo impact task detected; code-review-graph recommended")

    # Track E1 — subagent recommendation
    broad_scope_hit = bool(terms & BROAD_SCOPE_TERMS)
    subagent_recommended = (
        candidate_count > SUBAGENT_CANDIDATE_THRESHOLD or broad_scope_hit
    )
    subagent_snippet = _subagent_snippet(query) if subagent_recommended else ""
    if subagent_recommended:
        rationale.append(
            f"candidate set or scope wide; delegate via {subagent_snippet}"
        )

    # Track E3 — session-spawn escalation
    multi_repo_hit = bool(terms & MULTI_REPO_TERMS)
    session_spawn_recommended = bool(gstack_skill_available and multi_repo_hit)
    if session_spawn_recommended:
        rationale.append(
            "multi-repo scope detected; run `/create-session` to fan out per sibling repo"
        )

    # Track E4 — sibling-skill routing
    sibling_skill = sibling_skill_for_query(query) or ""
    if sibling_skill:
        rationale.append(f"query intent matches {sibling_skill}; consider that skill")

    return Decision(
        tier=tier,
        command=command,
        rationale=rationale,
        context_mode_recommended=context_mode_recommended,
        headroom_recommended=headroom_recommended,
        code_review_graph_recommended=code_review_graph_recommended,
        symbol=symbol,
        behavior=behavior,
        repo_file_count=repo_file_count,
        headroom_commands=headroom_commands,
        subagent_recommended=subagent_recommended,
        subagent_snippet=subagent_snippet,
        session_spawn_recommended=session_spawn_recommended,
        sibling_skill=sibling_skill,
    )


def run_command(command: Sequence[str], *, cwd: Path) -> tuple[int, str, str, int]:
    start = time.perf_counter()
    proc = subprocess.run(
        list(command),
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    return proc.returncode, proc.stdout or "", proc.stderr or "", duration_ms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    parser.add_argument("--behavior-days", type=int, default=None)
    parser.add_argument("query", nargs="+")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve() if args.repo_root else repo_root()
    query = " ".join(args.query).strip()
    config = load_config()
    routing = config.get("routing", {}) if isinstance(config.get("routing"), dict) else {}
    configured_behavior_days = int(routing.get("behavior_days", 3) or 3)
    behavior_days = args.behavior_days if args.behavior_days is not None else configured_behavior_days
    policy = RoutingPolicy(
        behavior_days=int(behavior_days),
        rapid_repeat_snippet_threshold=float(
            routing.get("rapid_repeat_snippet_threshold", 0.35) or 0.35
        ),
        enable_structural=bool(routing.get("enable_structural", True)),
        enable_context_mode_recommendations=bool(
            routing.get("enable_context_mode_recommendations", True)
        ),
        enable_headroom_recommendations=bool(
            routing.get("enable_headroom_recommendations", True)
        ),
        enable_code_review_graph_recommendations=bool(
            routing.get("enable_code_review_graph_recommendations", True)
        ),
    )
    availability = collect_availability()
    behavior = load_behavior_profile(root, days=policy.behavior_days)
    file_count = count_repo_files(root)
    decision = decide(
        query,
        behavior=behavior,
        availability=availability,
        policy=policy,
        root=root,
        repo_file_count=file_count,
    )

    payload = asdict(decision)
    payload["query"] = query
    payload["repo_root"] = str(root)

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    exit_code, stdout, stderr, duration_ms = run_command(decision.command, cwd=root)
    if stdout:
        print(stdout.rstrip("\n"))
    if stderr:
        print(stderr.rstrip("\n"), file=sys.stderr)

    lines = len([line for line in stdout.splitlines() if line.strip()])
    chars = len(stdout)

    # Track E1 — re-evaluate subagent recommendation with the actual candidate
    # count from helper output. Path-only helper emits one path per non-comment
    # line; if that crosses the threshold, surface the subagent snippet so the
    # caller can fan out instead of stuffing N reads into the parent context.
    candidate_lines = [
        line for line in stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    candidate_count = len(candidate_lines)
    if (
        candidate_count > SUBAGENT_CANDIDATE_THRESHOLD
        and not decision.subagent_recommended
    ):
        snippet = _subagent_snippet(query)
        print(
            f"# token-reduce: candidate set is {candidate_count} (> "
            f"{SUBAGENT_CANDIDATE_THRESHOLD}); delegate via {snippet}",
            file=sys.stderr,
        )
    record_event(
        root,
        event="helper_invocation",
        source="helper",
        tool="token_reduce_adaptive",
        status="ok" if exit_code == 0 else "error",
        query=query,
        meta={
            "context": os.environ.get("TOKEN_REDUCE_TELEMETRY_CONTEXT", "runtime"),
            "backend": "adaptive",
            "tier": decision.tier,
            "command": " ".join(decision.command),
            "latency_ms": duration_ms,
            "exit_code": exit_code,
            "lines": lines,
            "chars": chars,
            "behavior_repeated_ratio": decision.behavior.repeated_ratio,
            "behavior_rapid_repeat_ratio": decision.behavior.rapid_repeat_ratio,
            "context_mode_recommended": decision.context_mode_recommended,
            "headroom_recommended": decision.headroom_recommended,
            "code_review_graph_recommended": decision.code_review_graph_recommended,
        },
    )

    if args.emit_json:
        print(json.dumps(payload, indent=2))
    if exit_code == 0:
        # Clear pending first-move state on successful adaptive helper kickoff.
        clear_pending(root)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
