#!/usr/bin/env python3
"""PreToolUse hook: require token-reduce helper before exploratory Grep/Glob/Read/Bash."""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from command_rewrites import (
    estimate_output_tokens,
    format_block_message,
    is_catastrophic,
    suggest_rewrite,
)
from coverage_patterns import matches_any_broad_pattern
from token_reduce_state import (
    broad_attempt_count,
    consume_block,
    discovery_hint,
    is_pending,
    record_block,
    record_broad_attempt,
    repo_root,
    session_key,
)
from token_reduce_telemetry import record_event


BROAD_BASH_PATTERNS = [
    r"\bfind\s+(\.|/)",
    r"\bls\s+-R\b",
    r"\bgrep\s+-R\b",
    r"\bgrep\s+--recursive\b",
    r"\bdu\s+-a\b",
    r"\brg\b.*\s--files\b",
    r"\bfd\b(?:\s|$)",
    r"\btree\b(?:\s+\.|\s*$)",
]
# Commands that are safe orchestrators — they may have broad-looking args in --body/--message,
# but are never themselves filesystem scanners.
_SAFE_TOOL_RE = re.compile(
    r"^\s*(gh|git|npm|bun|node|uv|curl|wget|python3?|ruby|perl|cargo|go\s+run)\b"
)
HELPER_COMMAND_RE = re.compile(
    r"token-reduce-(?:adaptive|paths|snippet|structural)(?:\.(?:sh|py))?\b|qmd\s+search\b"
)
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


def block(
    reason: str,
    data: dict[str, object] | None = None,
    *,
    extra_meta: dict[str, object] | None = None,
) -> int:
    if data is not None:
        repo = repo_root()
        tool_name = str(data.get("tool_name", "unknown"))
        tool_input = data.get("tool_input", {}) or {}
        meta: dict[str, object] = {}
        if isinstance(tool_input, dict):
            for key in ("command", "pattern", "path", "glob"):
                value = str(tool_input.get(key, "") or "")[:240]
                if value:
                    meta[key] = value
        meta["session_key"] = session_key(data)
        if extra_meta:
            meta.update(extra_meta)
        # B4: cost-aware telemetry — log estimated tokens this block prevented
        command = str(meta.get("command", ""))
        if command:
            est = estimate_output_tokens(command)
            if est is not None:
                meta["estimated_output_tokens"] = est
        record_block(repo, tool_name, reason, meta.get("command"))  # type: ignore[arg-type]
        record_event(
            repo,
            event="hook_block",
            source="hook",
            tool=tool_name,
            status="blocked",
            meta=meta or None,
        )
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    print()
    return 2


def warn_and_allow(
    data: dict[str, object],
    *,
    command: str,
    reason: str,
    attempt_count: int,
) -> int:
    """B3 first-attempt path: emit a warn event but allow the command through.

    The block message would have cost tokens on a failed attempt; we trade
    that for a single advisory event and trust the agent to switch to the
    helper next time. Repeat attempts then hit the hard-block branch.
    """
    repo = repo_root()
    est = estimate_output_tokens(command)
    rewrite = suggest_rewrite(command) or ""
    record_event(
        repo,
        event="hook_warn",
        source="hook",
        tool=str(data.get("tool_name", "unknown")),
        status="warn",
        meta={
            "command": command[:240],
            "reason": reason,
            "attempt_count": attempt_count,
            "estimated_output_tokens": est,
            "rewrite": rewrite[:200],
            "session_key": session_key(data),
        },
    )
    return 0


def is_broad_glob(pattern: str) -> bool:
    if not pattern:
        return False
    p = pattern.lstrip("./")
    if p.startswith("**/"):
        return True
    if p.count("*") >= 2:
        return True
    if p.endswith("/**") or p.endswith("/**/*"):
        return True
    parts = p.split("/")
    return len(parts) > 1 and all(seg.startswith("*") for seg in parts[:2])


def is_exploratory_glob(pattern: str) -> bool:
    if not pattern:
        return False
    return any(char in pattern for char in "*?[")


def is_exploratory_grep(tool_input: dict[str, object], repo: Path) -> bool:
    path_value = str(tool_input.get("path", "") or "")
    glob_value = str(tool_input.get("glob", "") or "")

    # Broad glob filter always exploratory
    if any(char in glob_value for char in "*?["):
        return True

    # No path or root path = exploratory
    if not path_value or path_value in {".", "./"}:
        return True

    candidate = (repo / path_value).resolve()
    if candidate.exists():
        if candidate.is_dir():
            return True
        # It's a specific file — allow files_with_matches on exact files
        return False

    # Unknown path: exploratory if no extension (likely a dir name)
    return "." not in Path(path_value).name


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


def is_exploratory_rg(command: str, repo: Path) -> bool:
    first = command.strip()
    if not first.startswith("rg "):
        return False
    if re.search(r"(?:^|\s)(?:-g|--glob)(?:\s|=)", first):
        return False
    if re.search(r"(?:^|\s)(?:--files|--files-with-matches|--files-without-match)\b", first):
        return True

    paths = rg_paths(first)
    if not paths:
        return True

    for raw_path in paths:
        if raw_path in {".", "./"}:
            return True
        if any(ch in raw_path for ch in "*?["):
            return True

        candidate = (repo / raw_path).resolve()
        if candidate.exists():
            if candidate.is_dir():
                return True
            continue

        if "." not in Path(raw_path).name:
            return True

    return False


def helper_required_reason() -> str:
    hint = discovery_hint()
    return (
        f"token-reduce helper required for this prompt. "
        f"Run {hint} first. "
        f"After discovery runs, targeted Grep, Glob, and Read follow-ups are allowed."
    )


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        repo = repo_root()
        record_event(
            repo,
            event="hook_error",
            source="hook",
            tool="enforce-token-reduce-first",
            status="error",
            meta={"stage": "stdin_json", "error": str(exc)[:240]},
        )
        return 0

    # Post-block compliance tracking
    repo = repo_root()
    last_block = consume_block(repo)
    if last_block is not None:
        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {}) or {}
        command = ""
        if tool_name == "Bash" and isinstance(tool_input, dict):
            command = str(tool_input.get("command", "")).split("\n")[0]
        is_helper = bool(HELPER_COMMAND_RE.search(command)) if command else False
        if is_helper:
            record_event(
                repo,
                event="post_block_compliance",
                source="hook",
                tool="enforce-token-reduce-first",
                status="ok",
                meta={
                    "blocked_tool": last_block.get("tool"),
                    "blocked_reason": last_block.get("reason"),
                    "next_tool": tool_name,
                    "session_key": session_key(data),
                },
            )
        else:
            # If the agent is attempting another broad-ish tool right after a block,
            # classify as escape. If it's an innocent tool (Read on a known file,
            # Edit, etc.), classify as abandon/non_discovery.
            is_broad_attempt = False
            if tool_name == "Bash" and isinstance(tool_input, dict):
                cmd = str(tool_input.get("command", ""))
                lines = [l.rstrip("\\").strip() for l in cmd.split("\n") if l.strip() and l.strip() != "\\"]
                is_broad_attempt = any(
                    re.search(pattern, line)
                    for line in lines
                    for pattern in BROAD_BASH_PATTERNS
                ) or any(is_exploratory_rg(line, repo) for line in lines)
            if tool_name == "Glob" and isinstance(tool_input, dict):
                pattern = str(tool_input.get("pattern", ""))
                is_broad_attempt = is_broad_glob(pattern) or is_exploratory_glob(pattern)
            if tool_name == "Grep" and isinstance(tool_input, dict):
                is_broad_attempt = is_exploratory_grep(tool_input, repo)

            event_type = "post_block_escape" if is_broad_attempt else "post_block_abandon"
            record_event(
                repo,
                event=event_type,
                source="hook",
                tool="enforce-token-reduce-first",
                status="ok" if not is_broad_attempt else "blocked",
                meta={
                    "blocked_tool": last_block.get("tool"),
                    "blocked_reason": last_block.get("reason"),
                    "next_tool": tool_name,
                    "session_key": session_key(data),
                },
            )

    try:
        tool_name = data.get("tool_name")
        tool_input = data.get("tool_input", {}) or {}
        repo = repo_root()
        pending = is_pending(repo, session_key(data))

        if pending:
            if tool_name == "Bash":
                command = tool_input.get("command", "") or ""
                first_line = command.split("\n")[0]
                if HELPER_COMMAND_RE.search(first_line):
                    # N2 fix: check continuation lines for broad patterns before allowing
                    rest_lines = [l.strip() for l in command.split("\n")[1:] if l.strip() and l.strip() != "\\"]
                    if any(
                        re.search(p, line) for line in rest_lines for p in BROAD_BASH_PATTERNS
                    ) or any(is_exploratory_rg(line, repo) for line in rest_lines):
                        return block(helper_required_reason(), data)
                    return 0
                return block(helper_required_reason(), data)
            if tool_name in {"Glob", "Grep", "Read"}:
                # Read on an absolute path is targeted, not exploratory — always allow
                if tool_name == "Read":
                    file_path = str(tool_input.get("file_path", "") or "")
                    if file_path.startswith("/") and not any(c in file_path for c in "*?["):
                        return 0
                return block(helper_required_reason(), data)
            return 0

        if tool_name == "Bash":
            command = tool_input.get("command", "") or ""
            first_line = command.split("\n")[0]
            # Safe orchestrators: may carry broad-looking strings as arguments.
            # N1 fix: python3 -c/-m must fall through to coverage checks; only
            # plain `python3 script.py` is safe.
            if re.match(r"^\s*python3?\s+(-c|-m)\b", first_line):
                pass  # fall through to broad-pattern checks below
            elif _SAFE_TOOL_RE.match(first_line):
                return 0
            # Check all lines — broad scans may be on continuation lines
            lines = [l.rstrip("\\").strip() for l in command.split("\n") if l.strip() and l.strip() != "\\"]
            broad_hit = any(
                re.search(pattern, line)
                for line in lines
                for pattern in BROAD_BASH_PATTERNS
            )
            rg_hit = any(is_exploratory_rg(line, repo) for line in lines)
            # Track C: extra advisory patterns (unscoped rg, whole-dir cat,
            # python glob.glob/os.walk, xargs cat). Fold into broad_hit so
            # the warn-first/block-on-repeat policy applies uniformly.
            coverage_hit = any(matches_any_broad_pattern(line) for line in lines)
            if broad_hit or rg_hit or coverage_hit:
                # B3 catastrophic patterns → always hard block
                if any(is_catastrophic(line) for line in lines):
                    msg = format_block_message(
                        reason="catastrophic scan",
                        command=first_line,
                        helper_hint=discovery_hint(),
                    )
                    return block(msg, data, extra_meta={"policy": "catastrophic"})
                # B3 first attempt → warn + measure, allow
                # B3 repeat → block
                sk = session_key(data)
                count = broad_attempt_count(repo, sk)
                if count == 0:
                    record_broad_attempt(repo, sk)
                    return warn_and_allow(
                        data,
                        command=first_line,
                        reason=(
                            "broad bash scan" if broad_hit else "exploratory rg scan"
                        ),
                        attempt_count=1,
                    )
                # Repeat broad attempt
                record_broad_attempt(repo, sk)
                msg = format_block_message(
                    reason=(
                        f"broad scan x{count + 1} this session"
                    ),
                    command=first_line,
                    helper_hint=discovery_hint(),
                )
                return block(
                    msg,
                    data,
                    extra_meta={"policy": "repeat_broad", "attempt_count": count + 1},
                )
            return 0

        if tool_name == "Glob":
            pattern = tool_input.get("pattern", "") or ""
            if is_broad_glob(pattern) or is_exploratory_glob(pattern):
                return block(
                    f"Blocked exploratory Glob pattern. Use {discovery_hint()} for path-only kickoff, then switch to Read on an exact file path.",
                    data,
                )
            return 0

        if tool_name == "Grep" and is_exploratory_grep(tool_input, repo):
            return block(
                f"Blocked exploratory Grep before helper kickoff. Run {discovery_hint()} first, then use Grep on an exact file path or a much narrower scope.",
                data,
            )

        return 0
    except Exception as exc:
        repo = repo_root()
        record_event(
            repo,
            event="hook_error",
            source="hook",
            tool="enforce-token-reduce-first",
            status="error",
            meta={"stage": "runtime", "error": str(exc)[:240], "session_key": session_key(data)},
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
