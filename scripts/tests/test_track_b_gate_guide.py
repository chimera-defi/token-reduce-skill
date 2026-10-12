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

import pytest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from command_rewrites import (  # noqa: E402
    is_catastrophic,
    suggest_rewrite,
)
from token_reduce_state import (  # noqa: E402
    broad_attempt_count,
    record_broad_attempt,
)


# --------------------------------------------------------------------------- #
# B1 — auto-rewrite suggestions
# --------------------------------------------------------------------------- #


def test_suggest_rewrite_find_name_to_rg_glob() -> None:
    # F7: --hidden --no-ignore is mandatory -- rg's defaults silently drop
    # dotfiles/gitignored paths that `find` would have returned (verified
    # live: 0 vs 1454 hits under a dot-directory root), so a bare `rg -g
    # ... --files` rewrite is an unsafe suggestion, not just a style choice.
    s = suggest_rewrite('find . -name "*.py"')
    assert s is not None
    assert "rg --files --hidden --no-ignore -g '*.py'" in s










def test_suggest_rewrite_returns_none_when_no_pattern_matches() -> None:
    assert suggest_rewrite("echo hello") is None
    assert suggest_rewrite("git status") is None


# --------------------------------------------------------------------------- #
# B3 — catastrophic detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("command", ["ls -R /", "ls -lR /", "rg --files .", "rg --files ./"])
def test_is_catastrophic_ls_and_rg_files_at_root(command: str) -> None:
    assert is_catastrophic(command) is True


def test_is_catastrophic_find_root() -> None:
    assert is_catastrophic("find / -name foo") is True
    assert is_catastrophic("find /usr -type f") is True








def test_is_catastrophic_find_deep_scoped_path_not_catastrophic() -> None:
    # A find rooted several levels deep in one specific, named directory
    # (>2 path segments) is scoped, not catastrophic -- regression test for
    # a false positive where `find /home/agents/.claude/skills/token-reduce
    # -maxdepth 2` hard-blocked as "catastrophic scan" even though it's a
    # narrow, bounded scan. It still hits the broad-scan warn-once path via
    # BROAD_BASH_PATTERNS, just not the always-block catastrophic path.
    assert is_catastrophic(
        "find /home/agents/.claude/skills/token-reduce -maxdepth 2"
    ) is False




# --------------------------------------------------------------------------- #
# B3 — broad attempt counter
# --------------------------------------------------------------------------- #










# --------------------------------------------------------------------------- #
# B5 — pre-flight token estimate
# --------------------------------------------------------------------------- #








# --------------------------------------------------------------------------- #
# B2 — block message format (one-liner with rewrite)
# --------------------------------------------------------------------------- #


def test_broad_attempt_counter_is_per_session(tmp_path: Path) -> None:
    record_broad_attempt(tmp_path, "session-a")
    record_broad_attempt(tmp_path, "session-a")
    record_broad_attempt(tmp_path, "session-b")
    assert broad_attempt_count(tmp_path, "session-a") == 2
    assert broad_attempt_count(tmp_path, "session-b") == 1


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
