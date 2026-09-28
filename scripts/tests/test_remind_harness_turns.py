"""Regression tests: the UserPromptSubmit reminder must stay silent on
harness-generated turns and unclassifiable briefs.

Background task notifications arrive as a "user" prompt. Their embedded task
descriptions and agent results used to match the discovery regexes, so every
notification produced a TOKEN-REDUCE reminder whose suggested query was built
from task ids and tmp paths -- and set the pending marker that tightens the
PreToolUse gate. The fixture is a real notification envelope (captured from a
live session, result body scrubbed) that still matches the triggers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REMIND_HOOK = SCRIPTS_DIR / "remind-token-reduce.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hook_payloads"
sys.path.insert(0, str(SCRIPTS_DIR))

from token_reduce_state import is_pending, mark_pending, prompt_requires_helper, session_key  # noqa: E402

NOTIFICATION = (FIXTURES / "task_notification_agent_result.txt").read_text()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def _run(prompt: str, repo: Path, session_id: str = "sess-harness") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    payload = {
        "session_id": session_id,
        "transcript_path": str(repo / "t.jsonl"),
        "cwd": str(repo),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }
    return subprocess.run(
        [sys.executable, str(REMIND_HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(repo),
        timeout=30,
    )


def _events(repo: Path) -> str:
    path = repo / "artifacts" / "token-reduction" / "events.jsonl"
    return path.read_text() if path.exists() else ""


def test_huge_pathological_prompt_is_fast_and_silent(repo: Path) -> None:
    prompt = "where is the auth hook defined " + '<pasted_content id="1">' * 20_000
    result = _run(prompt, repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "hook_error" not in _events(repo)


def test_fixture_would_match_the_classifier() -> None:
    # Guard: the fixture must exercise the bug, i.e. match a discovery trigger
    # on its own -- so silence below comes from harness detection.
    assert prompt_requires_helper(NOTIFICATION)


@pytest.mark.parametrize(
    "prompt",
    [
        NOTIFICATION,
        "<system-reminder>\n[SYSTEM NOTIFICATION - NOT USER INPUT]\n" + NOTIFICATION + "\n</system-reminder>",
        "[SYSTEM NOTIFICATION - NOT USER INPUT]\nwhere is the auth hook defined in this repo",
        "This session is being continued from a previous conversation that ran out of context. "
        "The summary below covers the earlier portion. Where is the auth hook defined in the repo?",
        "<local-command-stdout>where is the auth hook defined</local-command-stdout>",
    ],
    ids=["task-notification", "system-reminder-wrapped", "system-notification", "compaction-summary", "local-command"],
)
def test_harness_turn_emits_nothing_and_keeps_pending(repo: Path, prompt: str) -> None:
    key = session_key({"session_id": "sess-harness"})
    mark_pending(repo, key, "where is the auth hook defined in this repo")

    result = _run(prompt, repo)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    # The real prompt's marker survives an interleaved harness turn.
    assert is_pending(repo, key)
    # Silence came from the harness-skip path, not a fail-open crash.
    assert "harness_turn_skipped" in _events(repo)


def test_harness_turn_does_not_set_pending(repo: Path) -> None:
    result = _run(NOTIFICATION, repo, session_id="sess-fresh")
    assert result.stdout == ""
    assert not is_pending(repo, session_key({"session_id": "sess-fresh"}))


def test_pasted_block_is_not_classified_but_human_text_is(repo: Path) -> None:
    pasted = '<pasted_content id="ab12">\nsearch the repo for every hook file\n</pasted_content id="ab12">'
    assert _run(pasted + "\nthanks, looks good", repo).stdout == ""

    result = _run(pasted + "\nwhere is the auth hook defined in this repo?", repo)
    message = json.loads(result.stdout)["systemMessage"]
    assert "auth hook defined" in message
    assert "pasted_content" not in message and "every" not in message


def test_long_brief_is_not_classified(repo: Path) -> None:
    brief = "User: <turn>\nYou are the owner session. " + ("Fix the deploy step and verify it. " * 20) + (
        "Search the repo for the config file.\n</turn>"
    )
    key = session_key({"session_id": "sess-harness"})
    result = _run(brief, repo)
    assert result.stdout == ""
    assert not is_pending(repo, key)
    assert "pending_cleared" in _events(repo) and "hook_error" not in _events(repo)


@pytest.mark.parametrize(
    "prompt",
    [
        "validate the hook script",
        "fix the enforcement hook in scripts/remind-token-reduce.py",
        "check the file and update the skill so it's actually being used",
    ],
)
def test_targeted_maintenance_prompts_are_not_discovery(repo: Path, prompt: str) -> None:
    assert _run(prompt, repo).stdout == ""


def test_real_discovery_prompt_still_reminds_with_clean_query(repo: Path) -> None:
    result = _run("where is the session_key helper defined? toolu_01ABC a6645869bd2a1a517", repo)
    message = json.loads(result.stdout)["systemMessage"]
    assert message.startswith("TOKEN-REDUCE:")
    assert "toolu_" not in message
    assert "a6645869bd2a1a517" not in message
