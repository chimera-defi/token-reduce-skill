#!/usr/bin/env python3
"""Shared repo-local state for Claude token-reduce enforcement."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from token_reduce_config import load_config


def discovery_hint() -> str:
    """Return the appropriate first-move discovery command for the current repo."""
    env_override = os.environ.get("TOKEN_REDUCE_ADAPTIVE_HINT")
    if env_override is not None:
        adaptive_enabled = env_override != "0"
    else:
        config = load_config()
        routing = config.get("routing", {}) if isinstance(config.get("routing"), dict) else {}
        adaptive_enabled = bool(routing.get("adaptive_hint", True))
    if adaptive_enabled and shutil.which("token-reduce-adaptive"):
        return "token-reduce-adaptive <topic words>"
    adaptive_helper = Path.cwd() / "scripts" / "token-reduce-adaptive.sh"
    if adaptive_enabled and adaptive_helper.exists():
        return "./scripts/token-reduce-adaptive.sh <topic words>"
    if shutil.which("token-reduce-paths"):
        return "token-reduce-paths <topic words>"
    helper = Path.cwd() / "scripts" / "token-reduce-paths.sh"
    if helper.exists():
        return "./scripts/token-reduce-paths.sh <topic words>"
    return "qmd search '<topic words>' -n 5 --files  (or scoped: rg --files -g '*.ext' | head -20)"


BLOCK_TTL_SECONDS = 5 * 60
STATE_DIR = ".claude/token-reduce-state"


def repo_root() -> Path:
    base_dir = os.environ.get("TOKEN_REDUCE_REPO_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    base = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return base
    candidate = (proc.stdout or "").strip()
    if candidate:
        return Path(candidate).resolve()
    return base


def normalize_session_key(raw: str | None) -> str:
    if not raw:
        return "default"
    key = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")
    return key or "default"


def session_key(data: dict) -> str:
    for field in (
        "session_id",
        "sessionId",
        "conversation_id",
        "conversationId",
        "chat_id",
        "chatId",
        "transcript_path",
        "transcriptPath",
        "uuid",
    ):
        value = data.get(field)
        if isinstance(value, str) and value:
            return normalize_session_key(value)
    return "default"


def state_dir(repo: Path) -> Path:
    return repo / STATE_DIR


def broad_attempt_path(repo: Path, key: str) -> Path:
    safe_key = normalize_session_key(key)
    return state_dir(repo) / f"broad_attempt_{safe_key}.json"


def broad_attempt_count(repo: Path, key: str) -> int:
    """Return current broad-attempt counter for the session (0 if unset)."""
    path = broad_attempt_path(repo, key)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    count = data.get("count")
    if isinstance(count, int):
        return count
    return 0


def record_broad_attempt(repo: Path, key: str) -> int:
    """Increment the per-session broad-attempt counter and return new value."""
    root = state_dir(repo)
    root.mkdir(parents=True, exist_ok=True)
    path = broad_attempt_path(repo, key)
    count = broad_attempt_count(repo, key) + 1
    payload = json.dumps({"count": count, "updated_at": time.time()}) + "\n"
    path.write_text(payload)
    return count


def clear_broad_attempts(repo: Path, key: str | None = None) -> None:
    root = state_dir(repo)
    if not root.exists():
        return
    if key is None:
        for path in root.glob("broad_attempt_*.json"):
            try:
                path.unlink()
            except OSError:
                continue
        return
    try:
        broad_attempt_path(repo, key).unlink()
    except FileNotFoundError:
        pass


def block_state_path(repo: Path) -> Path:
    return state_dir(repo) / "last_block.json"


def record_block(repo: Path, tool: str, reason: str, command: str | None = None) -> None:
    root = state_dir(repo)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "blocked_at": time.time(),
        "tool": tool,
        "reason": reason,
        "command": command,
    }
    block_state_path(repo).write_text(json.dumps(payload) + "\n")


def consume_block(repo: Path) -> dict | None:
    """Read and clear the last block state, returning it if still fresh."""
    path = block_state_path(repo)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        path.unlink()
    except OSError:
        pass
    blocked_at = data.get("blocked_at")
    if not isinstance(blocked_at, (int, float)):
        return None
    if time.time() - float(blocked_at) > BLOCK_TTL_SECONDS:
        return None
    return data


DECISION_DEDUP_SECONDS = 5


def decision_cache_path(repo: Path, key: str) -> Path:
    safe_key = normalize_session_key(key)
    return state_dir(repo) / f"decision_{safe_key}.json"


def _decision_fingerprint(fingerprint_source: str) -> str:
    return hashlib.sha256(fingerprint_source.encode("utf-8", "replace")).hexdigest()[:16]


def recent_decision(repo: Path, key: str, tool_use_id: str, fingerprint_source: str) -> dict | None:
    """F5: return a still-fresh cached decision for (key, tool_use_id), or None.

    Two settings layers can wire the same hook onto one PreToolUse matcher
    (repo .claude/settings.json + a global/deployed copy), so Claude Code
    invokes enforce-token-reduce-first.py's logic twice for the SAME tool
    call -- but both invocations receive an identical ``tool_use_id``
    (confirmed against Claude Code's hooks docs: it's a stable per-tool-call
    id, unique across genuinely separate calls even with identical command
    text). Without this cache the second invocation recomputes the
    broad-attempt counter from scratch -- already bumped by the first
    invocation -- and double-increments it (observed live: x2 then x4).

    Keying on ``tool_use_id`` rather than (session, fingerprint, time)
    alone is deliberate: a bare hash+time key can't tell "the same tool
    call checked twice" apart from "the agent genuinely retried the exact
    same broad command a few seconds later" -- and the latter must still
    escalate through the warn-once/block-on-repeat policy, not get silently
    deduped into an allow. ``tool_use_id`` is the one field guaranteed
    identical for the former and different for the latter. ``fingerprint_source``
    (R5: tool-agnostic -- ``tool_name`` + a stable JSON dump of
    ``tool_input``, not just Bash's ``command`` string, since dedup now
    covers Glob/Grep/Read/symlink-guard too) is a belt-and-suspenders check
    against a theoretical ``tool_use_id`` collision.

    R5 note: this file-marker approach only works because the two hook-
    wiring layers run SEQUENTIALLY for one tool call (layer 1 writes the
    marker before layer 2 reads it) -- the observed live x2/x4 counter
    doubling is evidence of that ordering. There is no lock; if Claude Code
    ever ran same-matcher hooks in parallel, both could miss the marker and
    the race would return. Acceptable given the confirmed sequential
    behavior, but worth naming.
    """
    path = decision_cache_path(repo, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("tool_use_id") != tool_use_id:
        return None
    if data.get("fingerprint") != _decision_fingerprint(fingerprint_source):
        return None
    decided_at = data.get("decided_at")
    if not isinstance(decided_at, (int, float)):
        return None
    if time.time() - float(decided_at) > DECISION_DEDUP_SECONDS:
        return None
    return data


def record_decision(
    repo: Path,
    key: str,
    tool_use_id: str,
    fingerprint_source: str,
    *,
    blocked: bool,
    stdout: str,
) -> None:
    """Store this invocation's decision for replay. ``stdout`` is the EXACT
    bytes the caller wrote (or "" for an allow/warn) so a replay can
    reproduce it verbatim -- storing just a "reason" string wouldn't work
    once dedup covers Glob/Grep/Read blocks too, whose messages aren't all
    built the same way Bash's are.
    """
    root = state_dir(repo)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool_use_id": tool_use_id,
        "fingerprint": _decision_fingerprint(fingerprint_source),
        "decided_at": time.time(),
        "blocked": blocked,
        "stdout": stdout,
    }
    decision_cache_path(repo, key).write_text(json.dumps(payload) + "\n")
