#!/usr/bin/env python3
"""UserPromptSubmit hook: require token-reduce for matching repo-discovery prompts."""
import json
import re
import shlex
import sys

try:
    from token_reduce_state import clear_pending, discovery_hint, mark_pending, prompt_requires_helper, repo_root, session_key
    from token_reduce_telemetry import record_event
except Exception:
    # Fail-open: a UserPromptSubmit hook must never hard-fail on a partial deploy
    # (entrypoint present, helper modules missing) or any other import-time error.
    try:
        sys.stdin.read()
    except Exception:
        pass
    sys.exit(0)

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


# Turns the harness (not a human) injects as a "user" prompt: background task
# notifications, system reminders, slash-command wrappers and their stdout,
# compaction summaries, /loop wakeups. These are never repo-discovery requests,
# and their embedded task descriptions/results used to trip the classifier and
# set the pending gate on every notification.
HARNESS_TURN_RE = re.compile(
    r"^\s*(?:"
    r"<task-notification\b"
    r"|<system-reminder\b"
    r"|\[SYSTEM NOTIFICATION\b"
    r"|<command-(?:name|message|args)\b"
    r"|<local-command-"
    r"|This session is being continued from a previous conversation"
    r"|\[\d+ prior /loop wakeup"
    r"|\[Image: "
    r")",
    re.IGNORECASE,
)

# Machine-generated blocks that can be embedded in (or wrap) a human prompt.
# Only the text outside them is classified.
EMBEDDED_BLOCK_RE = re.compile(
    r"<(system-reminder|task-notification|pasted_content)\b[^>]*>.*?</\1\b[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
RELAY_WRAPPER_RE = re.compile(r"^\s*User:\s*<turn>|</turn>\s*$", re.IGNORECASE)

# Beyond this, the remaining text is a brief or handoff, not a question; a
# regex cannot tell broad discovery from targeted work in it, so stay silent.
MAX_CLASSIFIABLE_CHARS = 500
# Raw prompts beyond this are never classifiable; skip before the block regexes,
# whose worst case (many unclosed openers) is quadratic.
MAX_RAW_PROMPT_CHARS = 50_000

# Tokens that are identifiers (task ids, tool-use ids, hashes, dates), not topics.
NOISE_TOKEN_RE = re.compile(r"^(?:toolu_\w+|[0-9a-f]{7,}|\S*\d{4,}\S*)$", re.IGNORECASE)


def is_harness_turn(prompt: str) -> bool:
    return bool(HARNESS_TURN_RE.match(prompt))


def human_text(prompt: str) -> str:
    """The part of the prompt a human plausibly typed: harness blocks stripped."""
    text = EMBEDDED_BLOCK_RE.sub(" ", prompt)
    text = RELAY_WRAPPER_RE.sub(" ", text)
    return text.strip()


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
        if NOISE_TOKEN_RE.match(token):
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


def _record_hook_error(stage: str, exc: Exception) -> None:
    """Best-effort fail-open telemetry; must NEVER raise (repo_root()/record_event()
    can themselves throw during a partial/broken deploy)."""
    try:
        record_event(
            repo_root(),
            event="hook_error",
            source="hook",
            tool="remind-token-reduce",
            status="error",
            meta={"stage": stage, "error": str(exc)[:240]},
        )
    except Exception:
        pass


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        _record_hook_error("stdin_json", exc)
        return 0

    try:
        raw_prompt = extract_prompt(data)
        repo = repo_root()
        key = session_key(data)
        if is_harness_turn(raw_prompt):
            prompt = ""
        elif len(raw_prompt) > MAX_RAW_PROMPT_CHARS:
            prompt = raw_prompt  # rejected by the length check below
        else:
            prompt = human_text(raw_prompt)
        if not prompt:
            # Harness-generated turn: no human input arrived, so neither emit a
            # reminder nor touch the pending marker the real prompt set.
            record_event(repo, event="harness_turn_skipped", source="hook", tool="remind-token-reduce")
            return 0
        if len(prompt) > MAX_CLASSIFIABLE_CHARS or not prompt_requires_helper(prompt):
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
                    "TOKEN-REDUCE: this prompt looks like repo discovery. "
                    f"For a quick, narrow lookup: run {hint} (suggested: {suggested}). "
                    "For a broad sweep -- an audit, a repo-wide search, tracing something "
                    "across many files -- delegate instead of scanning it yourself: "
                    'Agent(subagent_type="Explore", ...) for read-only search, or '
                    'subagent_type="builder" / model="sonnet" for implementation and deep '
                    "research, and use the conclusions + evidence it returns. "
                    "Targeted work you already know the path for -- a known file, a specific "
                    "grep, git/gh commands, running tests -- is not gated by this reminder."
                ),
            },
            sys.stdout,
        )
        print()
        return 0
    except Exception as exc:
        _record_hook_error("runtime", exc)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        # Absolute last resort: a UserPromptSubmit hook must never hard-fail.
        try:
            sys.stdin.read()
        except Exception:
            pass
        raise SystemExit(0)
