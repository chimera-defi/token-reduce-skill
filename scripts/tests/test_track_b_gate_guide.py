"""Track B — Gate → Guide tests.

Covers:
- B1 command_rewrites.suggest_rewrite (find/ls → rg, etc.)
- B2 one-line block messages
- B3 broad-attempt counter + catastrophic vs warn vs block policy
- B4 cost-aware telemetry meta fields
- B5 pre-flight estimate annotation
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from command_rewrites import (  # noqa: E402
    estimate_output_tokens,
    is_catastrophic,
    suggest_rewrite,
)
from token_reduce_state import (  # noqa: E402
    broad_attempt_count,
    clear_broad_attempts,
    record_broad_attempt,
)


# --------------------------------------------------------------------------- #
# B1 — auto-rewrite suggestions
# --------------------------------------------------------------------------- #


def test_suggest_rewrite_find_name_to_rg_glob() -> None:
    s = suggest_rewrite('find . -name "*.py"')
    assert s is not None
    assert "rg -g '*.py' --files" in s


def test_suggest_rewrite_find_root_to_helper() -> None:
    s = suggest_rewrite("find / -name foo")
    assert s is not None
    assert "token-reduce" in s.lower() or "qmd" in s.lower()


def test_suggest_rewrite_ls_recursive_to_helper() -> None:
    s = suggest_rewrite("ls -R .")
    assert s is not None
    assert "token-reduce" in s.lower()


def test_suggest_rewrite_grep_recursive_to_rg() -> None:
    s = suggest_rewrite("grep -R pattern .")
    assert s is not None
    assert "rg" in s


def test_suggest_rewrite_rg_files_to_helper() -> None:
    s = suggest_rewrite("rg --files .")
    assert s is not None
    assert "token-reduce" in s.lower()


def test_suggest_rewrite_returns_none_when_no_pattern_matches() -> None:
    assert suggest_rewrite("echo hello") is None
    assert suggest_rewrite("git status") is None


# --------------------------------------------------------------------------- #
# B3 — catastrophic detection
# --------------------------------------------------------------------------- #


def test_is_catastrophic_find_root() -> None:
    assert is_catastrophic("find / -name foo") is True
    assert is_catastrophic("find /usr -type f") is True


def test_is_catastrophic_ls_root() -> None:
    assert is_catastrophic("ls -R /") is True
    assert is_catastrophic("ls -lR /") is True


def test_is_catastrophic_rg_files_at_root() -> None:
    assert is_catastrophic("rg --files .") is True
    assert is_catastrophic("rg --files ./") is True
    # Scoped is not catastrophic
    assert is_catastrophic("rg --files scripts/") is False


def test_is_catastrophic_non_catastrophic_broad() -> None:
    # broad-looking but inside the repo, not at root
    assert is_catastrophic('find . -name "*.py"') is False
    assert is_catastrophic("grep -R pattern .") is False


# --------------------------------------------------------------------------- #
# B3 — broad attempt counter
# --------------------------------------------------------------------------- #


def test_broad_attempt_counter_starts_at_zero(tmp_path: Path) -> None:
    assert broad_attempt_count(tmp_path, "session-x") == 0


def test_broad_attempt_counter_increments_and_persists(tmp_path: Path) -> None:
    assert record_broad_attempt(tmp_path, "session-x") == 1
    assert record_broad_attempt(tmp_path, "session-x") == 2
    assert broad_attempt_count(tmp_path, "session-x") == 2


def test_broad_attempt_counter_is_per_session(tmp_path: Path) -> None:
    record_broad_attempt(tmp_path, "session-a")
    record_broad_attempt(tmp_path, "session-a")
    record_broad_attempt(tmp_path, "session-b")
    assert broad_attempt_count(tmp_path, "session-a") == 2
    assert broad_attempt_count(tmp_path, "session-b") == 1


def test_broad_attempt_counter_clear(tmp_path: Path) -> None:
    record_broad_attempt(tmp_path, "session-c")
    record_broad_attempt(tmp_path, "session-c")
    clear_broad_attempts(tmp_path, "session-c")
    assert broad_attempt_count(tmp_path, "session-c") == 0


# --------------------------------------------------------------------------- #
# B5 — pre-flight token estimate
# --------------------------------------------------------------------------- #


def test_estimate_output_tokens_for_find() -> None:
    # find . -name suggests large output; integer estimate
    e = estimate_output_tokens('find . -name "*.py"')
    assert e is not None
    assert e > 0


def test_estimate_output_tokens_for_rg_files() -> None:
    e = estimate_output_tokens("rg --files .")
    assert e is not None
    assert e > 0


def test_estimate_output_tokens_returns_none_for_safe() -> None:
    assert estimate_output_tokens("echo hi") is None
    assert estimate_output_tokens("git status") is None


# --------------------------------------------------------------------------- #
# B2 — block message format (one-liner with rewrite)
# --------------------------------------------------------------------------- #


def test_block_message_includes_rewrite_one_line() -> None:
    from command_rewrites import format_block_message

    msg = format_block_message(
        reason="broad scan",
        command='find . -name "*.py"',
        helper_hint="token-reduce-paths",
    )
    # one logical line: no double newlines, ends without trailing newline
    assert "\n\n" not in msg
    # includes the rewrite hint
    assert "rg" in msg
    assert "token-reduce" in msg.lower()
    # length sane — under 240 chars to keep block output tight
    assert len(msg) <= 240
