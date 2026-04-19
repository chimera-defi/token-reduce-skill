#!/usr/bin/env python3
"""UserPromptSubmit hook: require token-reduce for matching repo-discovery prompts."""
import json
import re
import shlex
import sys

from token_reduce_state import clear_pending, discovery_hint, mark_pending, prompt_requires_helper, repo_root, session_key
from token_reduce_telemetry import record_event

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "let",
    "me",
    "now",
    "of",
    "on",
    "or",
    "our",
    "please",
    "so",
    "that",
    "the",
    "them",
    "then",
    "this",
    "to",
    "up",
    "use",
    "we",
    "with",
    "you",
}


def extract_prompt(data: dict) -> str:
    for key in ("user_prompt", "prompt", "text", "input"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    message = data.get("message")
    if isinstance(message, dict):
        for key in ("text", "content", "prompt"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value

    return ""


def topic_words(prompt: str, limit: int = 8) -> str:
    candidates: list[str] = []

    for chunk in re.findall(r"`([^`]+)`", prompt):
        candidates.extend(re.findall(r"[A-Za-z0-9_.-]+", chunk))

    candidates.extend(re.findall(r"[A-Za-z0-9_.-]+", prompt))

    selected: list[str] = []
    seen: set[str] = set()
    for token in candidates:
        lowered = token.lower()
        if lowered in STOPWORDS:
            continue
        if len(token) < 2:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        selected.append(token)
        if len(selected) >= limit:
            break

    return " ".join(selected)


def suggested_discovery_command(prompt: str, hint: str) -> str:
    words = topic_words(prompt) or "topic words"
    quoted_words = shlex.quote(words)
    if "<topic words>" in hint:
        return hint.replace("<topic words>", quoted_words)
    if "<query words...>" in hint:
        return hint.replace("<query words...>", quoted_words)
    if "qmd search" in hint:
        return hint.replace("<topic words>", quoted_words)
    return f"{hint} {quoted_words}"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        repo = repo_root()
        record_event(
            repo,
            event="hook_error",
            source="hook",
            tool="remind-token-reduce",
            status="error",
            meta={"stage": "stdin_json", "error": str(exc)[:240]},
        )
        return 0

    try:
        prompt = extract_prompt(data)
        repo = repo_root()
        key = session_key(data)
        if not prompt_requires_helper(prompt):
            clear_pending(repo, key)
            record_event(repo, event="pending_cleared", source="hook", tool="remind-token-reduce")
            return 0

        mark_pending(repo, key, prompt)
        record_event(
            repo,
            event="pending_marked",
            source="hook",
            tool="remind-token-reduce",
            meta={"session_key": key},
        )
        record_event(
            repo,
            event="reminder_emitted",
            source="hook",
            tool="remind-token-reduce",
            query=prompt[:240],
            meta={"session_key": key},
        )

        hint = discovery_hint()
        suggested = suggested_discovery_command(prompt, hint)
        json.dump(
            {
                "continue": True,
                "systemMessage": (
                    "TOKEN-REDUCE ENFORCEMENT ACTIVE. "
                    f"Your FIRST tool call MUST be a Bash discovery call: {hint}. "
                    f"Suggested kickoff for this prompt: {suggested}. "
                    "The hooks will block any Grep, Glob, Read, or broad Bash scan until discovery runs. "
                    "This applies even for skill maintenance tasks — if you do not know the exact file path already, run discovery first. "
                    "Use the user's literal filenames, identifiers, or key nouns as query words; "
                    "do not use generic synonyms or omit qualifiers like Bash, Glob, hook, or token reduction. "
                    "After discovery runs, use targeted Grep or Read for narrowing — do not switch back to broad Bash search commands."
                ),
            },
            sys.stdout,
        )
        print()
        return 0
    except Exception as exc:
        repo = repo_root()
        record_event(
            repo,
            event="hook_error",
            source="hook",
            tool="remind-token-reduce",
            status="error",
            meta={"stage": "runtime", "error": str(exc)[:240]},
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
