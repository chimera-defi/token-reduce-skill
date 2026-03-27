#!/usr/bin/env python3
"""Shared repo-local state for Claude token-reduce enforcement."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path


TRIGGERS = (
    r"\bexplor(e|ing|ation)\b.{0,60}\b(repo|codebase|files?|code)\b",
    r"\b(find|locate|where)\b.{0,60}\b(file|class|function|hook|script|lives?|defined|lives?)\b",
    r"\b(read|load|gather)\b.{0,60}\bcontext\b",
    r"\bsearch\b.{0,60}\b(repo|codebase|files?)\b",
    r"\breview\b.{0,60}\b(repo|codebase|entire|whole)\b",
    r"\bwhere\s+(is|are|does|do)\b",
    r"\bwhere.{0,20}\blive[s]?\b",
)
STATE_TTL_SECONDS = 20 * 60
STATE_DIR = ".claude/token-reduce-state"


def repo_root() -> Path:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir).resolve()
    return Path.cwd().resolve()


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


def state_path(repo: Path, key: str) -> Path:
    return state_dir(repo) / f"{key}.json"


def prompt_requires_helper(prompt: str) -> bool:
    return any(re.search(pattern, prompt, re.IGNORECASE) for pattern in TRIGGERS)


def prune(repo: Path) -> None:
    root = state_dir(repo)
    if not root.exists():
        return
    cutoff = time.time() - STATE_TTL_SECONDS
    for path in root.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def mark_pending(repo: Path, key: str, prompt: str) -> None:
    root = state_dir(repo)
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"prompt": prompt, "created_at": time.time()}) + "\n"
    state_path(repo, key).write_text(payload)
    if key != "default":
        state_path(repo, "default").write_text(payload)


def clear_pending(repo: Path, key: str | None = None) -> None:
    root = state_dir(repo)
    if not root.exists():
        return
    if key:
        for candidate in {key, "default"}:
            try:
                state_path(repo, candidate).unlink()
            except FileNotFoundError:
                pass
        return
    for path in root.glob("*.json"):
        try:
            path.unlink()
        except OSError:
            continue


def is_pending(repo: Path, key: str) -> bool:
    prune(repo)
    return state_path(repo, key).exists() or state_path(repo, "default").exists()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    clear_parser = subparsers.add_parser("clear")
    clear_parser.add_argument("--all", action="store_true")
    clear_parser.add_argument("--session-key")

    args = parser.parse_args()
    repo = repo_root()

    if args.command == "clear":
        if args.all:
            clear_pending(repo)
        else:
            clear_pending(repo, args.session_key or "default")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
