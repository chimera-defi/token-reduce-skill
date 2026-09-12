"""Regression tests for the F1-F9 hook-diagnosis fixes (2026-09-12 builder pass).

Root causes fixed (see the task brief this file accompanies):

  RC1 (cold-start block storm): mark_pending() cross-poisoned every session
      in the repo via a duplicate "default.json" write; the pending gate
      then default-blocked almost all Bash regardless of cost; pending
      survived a compliant helper call.
  RC2 (broad-scan counter too aggressive): raw find-root regex ignored
      -maxdepth/specificity; broad patterns matched inside quoted/inert
      text; dual hook-wiring layers double-counted a single tool call.
  RC3 (silent wrong answers): `find <symlink-root>` silently returns
      nothing; the rg-rewrite suggestion silently dropped hidden/ignored
      files.

Fixes, by id:
  F1 - token_reduce_state: no cross-session pending poisoning.
  F2 - pending gate: same broad/catastrophic classification as non-pending,
       not a blanket default-block.
  F3 - quote-aware broad-pattern matching with command-executor recursion.
  F4 - cost-aware `find -maxdepth <=2 <specific-dir>` is not broad.
  F5 - double-run dedup keyed on tool_use_id (not raw command+time alone).
  F6 - find-on-symlink-root guard (fail loud, not silently empty).
  F7 - suggest_rewrite's find->rg rewrite preserves results (--hidden --no-ignore).
  F8 - exit-path / stdout-content audit.
  F9 - TOKEN_REDUCE_ENFORCE_MODE=warn downgrades blocks to telemetry-only.
  Helper-clears-pending: a clean helper call while pending clears state for
       that session so the next Grep/Glob/Read isn't gated again.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

HOOK = SCRIPTS_DIR / "enforce-token-reduce-first.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


enforce = _load("enforce-token-reduce-first")

import command_rewrites as cr  # noqa: E402
import token_reduce_state as trs  # noqa: E402


def _init_git_repo(path: Path) -> None:
    for args in (
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        ["git", "-C", str(path), "config", "user.name", "test"],
    ):
        subprocess.run(args, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def _run_hook(payload: dict, repo_root: Path, *, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("TOKEN_REDUCE_ENFORCE_MODE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(repo_root),
        timeout=30,
    )


def _bash_payload(command: str, session_id: str = "sess-test", tool_use_id: str | None = None) -> dict:
    payload: dict[str, object] = {
        "session_id": session_id,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if tool_use_id:
        payload["tool_use_id"] = tool_use_id
    return payload


def _events(repo_root: Path) -> list[dict]:
    path = repo_root / "artifacts" / "token-reduction" / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --------------------------------------------------------------------------- #
# F1 - no cross-session pending poisoning
# --------------------------------------------------------------------------- #


class TestF1CrossSessionPending:
    def test_session_a_pending_does_not_poison_session_b(self, tmp_path: Path) -> None:
        trs.mark_pending(tmp_path, "session-a", "explore the repo for hooks")
        assert trs.is_pending(tmp_path, "session-a") is True
        assert trs.is_pending(tmp_path, "session-b") is False

    def test_id_less_payload_still_works(self, tmp_path: Path) -> None:
        # A payload with no session identity normalizes to key "default"
        # both when marking and when checking -- so it still works without
        # any cross-session special-casing.
        trs.mark_pending(tmp_path, "default", "explore the repo for hooks")
        assert trs.is_pending(tmp_path, "default") is True

    def test_mark_pending_does_not_write_default_json_for_real_session(self, tmp_path: Path) -> None:
        trs.mark_pending(tmp_path, "session-a", "explore the repo for hooks")
        assert not trs.state_path(tmp_path, "default").exists()

    def test_clear_pending_scoped_to_key_only(self, tmp_path: Path) -> None:
        trs.mark_pending(tmp_path, "session-a", "explore the repo")
        trs.mark_pending(tmp_path, "default", "explore the repo")
        trs.clear_pending(tmp_path, "session-a")
        assert trs.is_pending(tmp_path, "session-a") is False
        # Clearing session-a must not wipe another id-less session's marker.
        assert trs.is_pending(tmp_path, "default") is True

    def test_live_hook_session_a_prompt_does_not_gate_session_b_bash(self, repo: Path) -> None:
        """End-to-end: session A's UserPromptSubmit marks pending; session B's
        PreToolUse for an unrelated Bash command must not be gated by it."""
        trs.mark_pending(repo, "live-session-a", "where is the auth hook defined")
        result = _run_hook(_bash_payload("echo hello", session_id="live-session-b"), repo)
        assert result.returncode == 0, result.stdout
        assert result.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# F2 - pending gate applies the same broad/catastrophic classification
# --------------------------------------------------------------------------- #


class TestF2PendingGateClassification:
    def _make_pending(self, repo: Path, session_id: str) -> None:
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")

    @pytest.mark.parametrize(
        "command",
        [
            "which rg",
            "date",
        ],
    )
    def test_targeted_commands_pass_while_pending(self, repo: Path, command: str) -> None:
        session_id = "sess-f2-targeted"
        self._make_pending(repo, session_id)
        result = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert result.returncode == 0, f"{command!r} should pass while pending, got {result.stdout!r}"
        assert result.stdout.strip() == ""

    def test_ls_specific_dir_passes_while_pending(self, repo: Path) -> None:
        session_id = "sess-f2-ls-dir"
        self._make_pending(repo, session_id)
        (repo / "scripts").mkdir(exist_ok=True)
        result = _run_hook(_bash_payload("ls -la scripts", session_id=session_id), repo)
        assert result.returncode == 0, result.stdout

    def test_cat_specific_file_passes_while_pending(self, repo: Path) -> None:
        session_id = "sess-f2-cat-file"
        self._make_pending(repo, session_id)
        target = repo / "README.md"
        target.write_text("hello\n")
        result = _run_hook(_bash_payload("cat README.md", session_id=session_id), repo)
        assert result.returncode == 0, result.stdout

    def test_stat_specific_file_passes_while_pending(self, repo: Path) -> None:
        session_id = "sess-f2-stat-file"
        self._make_pending(repo, session_id)
        target = repo / "README.md"
        target.write_text("hello\n")
        result = _run_hook(_bash_payload("stat README.md", session_id=session_id), repo)
        assert result.returncode == 0, result.stdout

    def test_catastrophic_find_root_still_blocks_while_pending(self, repo: Path) -> None:
        session_id = "sess-f2-catastrophic"
        self._make_pending(repo, session_id)
        result = _run_hook(_bash_payload("find / -name '*.py'", session_id=session_id), repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"
        events = _events(repo)
        cata = [e for e in events if e.get("event") == "hook_block" and (e.get("meta") or {}).get("policy") == "catastrophic"]
        assert cata, events

    def test_broad_but_noncatastrophic_blocks_immediately_while_pending_no_warn_grace(self, repo: Path) -> None:
        """Unlike the non-pending path, pending gets no warn-once grace --
        the very first broad attempt blocks outright."""
        session_id = "sess-f2-no-grace"
        self._make_pending(repo, session_id)
        result = _run_hook(_bash_payload("tree .", session_id=session_id), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"


# --------------------------------------------------------------------------- #
# Helper-clears-pending
# --------------------------------------------------------------------------- #


class TestHelperClearsPending:
    def test_clean_helper_call_clears_pending_for_session(self, repo: Path) -> None:
        session_id = "sess-helper-clears"
        trs.mark_pending(repo, session_id, "where is the auth hook defined")
        assert trs.is_pending(repo, session_id) is True

        result = _run_hook(
            _bash_payload("./scripts/token-reduce-paths.sh auth hook", session_id=session_id), repo
        )
        assert result.returncode == 0, result.stdout
        assert trs.is_pending(repo, session_id) is False

    def test_next_read_allowed_after_clean_helper_call(self, repo: Path) -> None:
        session_id = "sess-helper-clears-read"
        trs.mark_pending(repo, session_id, "where is the auth hook defined")
        helper_result = _run_hook(
            _bash_payload("./scripts/token-reduce-paths.sh auth hook", session_id=session_id), repo
        )
        assert helper_result.returncode == 0

        target = repo / "auth.py"
        target.write_text("# auth hook\n")
        read_payload = {
            "session_id": session_id,
            "tool_name": "Read",
            "tool_input": {"file_path": str(target)},
        }
        read_result = _run_hook(read_payload, repo)
        assert read_result.returncode == 0, read_result.stdout

        grep_payload = {
            "session_id": session_id,
            "tool_name": "Grep",
            "tool_input": {"pattern": "auth", "path": str(target)},
        }
        grep_result = _run_hook(grep_payload, repo)
        assert grep_result.returncode == 0, grep_result.stdout

    def test_dirty_helper_call_does_not_clear_pending(self, repo: Path) -> None:
        """N2 control: a helper call whose continuation line smuggles a scan
        must still block, and must NOT clear pending."""
        session_id = "sess-helper-dirty"
        trs.mark_pending(repo, session_id, "where is the auth hook defined")
        result = _run_hook(
            _bash_payload(
                "./scripts/token-reduce-paths.sh auth\nfind / -name '*.py'", session_id=session_id
            ),
            repo,
        )
        assert result.returncode == 2
        assert trs.is_pending(repo, session_id) is True


# --------------------------------------------------------------------------- #
# F3 - quote-aware broad-pattern matching with command-executor recursion
# --------------------------------------------------------------------------- #


class TestF3QuoteAwareBroadMatching:
    def test_json_payload_with_embedded_find_is_allowed(self, repo: Path) -> None:
        """The exact live over-block repro: a JSON blob containing the text
        `find /home/...` as inert data, piped through a tool, must not be
        mistaken for a real scan."""
        cmd = (
            'echo \'{"tool_name":"Bash","tool_input":{"command":"find /home/agents/x -name y"}}\''
            " | rtk hook claude"
        )
        result = _run_hook(_bash_payload(cmd), repo)
        assert result.returncode == 0, result.stdout
        assert result.stdout.strip() == ""
        events = _events(repo)
        assert not [e for e in events if e.get("event") in {"hook_block", "hook_warn"}], events

    def test_unquoted_find_root_still_matches(self) -> None:
        assert enforce.matches_broad_bash("find / -name x") is True
        assert cr.is_catastrophic("find / -name x") is True

    def test_bash_dash_c_quoted_find_root_still_matches(self, repo: Path) -> None:
        result = _run_hook(_bash_payload('bash -c "find / -name x"'), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"

    def test_commit_message_with_broad_words_is_not_flagged(self, repo: Path) -> None:
        cmd = 'git commit -m "find . -name broken; fix ls -R usage"'
        result = _run_hook(_bash_payload(cmd), repo)
        assert result.returncode == 0, result.stdout

    def test_python_dash_c_os_walk_recursed_into_quoted_body(self, repo: Path) -> None:
        """python -c is a command-executor too -- its quoted body must be
        recursed into, not stripped (this guards the F3 x F4 combination
        that regressed N1's os.walk detection during development)."""
        cmd = 'python3 -c "import os; [_ for _ in os.walk(\'.\')]"'
        r1 = _run_hook(_bash_payload(cmd, session_id="sess-f3-py-walk"), repo)
        assert r1.returncode == 0
        r2 = _run_hook(_bash_payload(cmd, session_id="sess-f3-py-walk"), repo)
        assert r2.returncode == 2, "repeat python3 -c os.walk must still escalate to block"


# --------------------------------------------------------------------------- #
# F3 follow-up - fd/tree bare-command-name patterns, command-position only
# --------------------------------------------------------------------------- #
# Found in coordinator verification: `\bfd\b(?:\s|$)` and
# `\btree\b(?:\s+\.|\s*$)` matched the token in ARGUMENT position too (e.g.
# `which fd`, `cargo install fd`, `echo tree`), unlike the other
# BROAD_BASH_PATTERNS entries which all need a characteristic flag/arg
# (`ls -R`, `grep -R`, `du -a`, `rg --files`) and so can't false-positive
# the same way. Scoped the fix to fd/tree only, gated on command position
# (leading token of a segment split on ;, &&, ||, |).


class TestF3FollowupFdTreeCommandPosition:
    @pytest.mark.parametrize(
        "command",
        [
            "which fd",
            "which tree",
            "cargo install fd",
            "echo tree",
        ],
    )
    def test_argument_position_is_not_broad(self, command: str) -> None:
        assert enforce.matches_broad_bash(command) is False

    @pytest.mark.parametrize(
        "command",
        [
            "fd pattern",
            "tree .",
            "tree",
            "x | fd",
            "cd y && fd",
        ],
    )
    def test_command_position_is_still_broad(self, command: str) -> None:
        assert enforce.matches_broad_bash(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "which fd",
            "which tree",
            "cargo install fd",
            "echo tree",
        ],
    )
    def test_argument_position_passes_pending_gate_live(self, repo: Path, command: str) -> None:
        session_id = f"sess-f3-followup-{hash(command)}"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert result.returncode == 0, f"{command!r} should pass while pending, got {result.stdout!r}"
        assert result.stdout.strip() == ""
        assert trs.broad_attempt_count(repo, session_id) == 0

    @pytest.mark.parametrize(
        "command",
        [
            "fd pattern",
            "tree .",
            "tree",
            "x | fd",
            "cd y && fd",
        ],
    )
    def test_command_position_still_blocks_pending_gate_live(self, repo: Path, command: str) -> None:
        session_id = f"sess-f3-followup-block-{hash(command)}"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert result.returncode == 2, f"{command!r} should still block while pending, got {result.stdout!r}"


# --------------------------------------------------------------------------- #
# F4 - cost-aware find classification
# --------------------------------------------------------------------------- #


class TestF4CostAwareFind:
    def test_maxdepth_bounded_specific_dir_is_not_broad(self, tmp_path: Path) -> None:
        target = tmp_path / "some" / "specific" / "dir"
        target.mkdir(parents=True)
        assert cr.is_broad_find(f"find {target} -maxdepth 1 -type d") is False

    def test_no_maxdepth_specific_dir_is_still_broad(self, tmp_path: Path) -> None:
        target = tmp_path / "some" / "specific" / "dir"
        assert cr.is_broad_find(f"find {target} -type d") is True

    def test_maxdepth_at_filesystem_root_is_still_broad(self) -> None:
        assert cr.is_broad_find("find / -maxdepth 1") is True

    def test_maxdepth_at_near_top_level_dir_is_still_broad(self) -> None:
        # <=2 path segments -- e.g. /home/agents -- is still catastrophic-root
        # territory regardless of -maxdepth (see _find_targets_broad_root).
        assert cr.is_broad_find("find /home/agents -maxdepth 1") is True

    def test_maxdepth_three_is_still_broad(self, tmp_path: Path) -> None:
        target = tmp_path / "some" / "specific" / "dir"
        assert cr.is_broad_find(f"find {target} -maxdepth 3") is True

    def test_live_shape_sanity_check_passes_cleanly(self, repo: Path) -> None:
        target = repo / "projects_like_dir"
        target.mkdir()
        cmd = f"ls -la {target}; find {target} -maxdepth 1 -type d | wc -l; date"
        result = _run_hook(_bash_payload(cmd), repo)
        assert result.returncode == 0, result.stdout
        assert result.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# F5 - double-run dedup keyed on tool_use_id
# --------------------------------------------------------------------------- #


class TestF5DoubleRunDedup:
    def test_same_tool_use_id_deduped_counter_increments_once(self, repo: Path) -> None:
        """R5: dedup replay is ZERO side effects by design -- no
        hook_dedup_replay telemetry event, no post-block classification, no
        record_block. The only observable proof of dedup is what survives:
        the broad-attempt counter increments exactly once, and the two
        invocations produce byte-identical output."""
        session_id = "sess-f5-dedup"
        payload = _bash_payload("tree .", session_id=session_id, tool_use_id="toolu_same_call_01")

        first = _run_hook(payload, repo)
        second = _run_hook(payload, repo)

        assert first.returncode == 0, first.stdout
        assert second.returncode == 0, second.stdout
        assert first.stdout == second.stdout == ""

        count = trs.broad_attempt_count(repo, session_id)
        assert count == 1, f"counter should increment once across 2 duplicate-wiring invocations, got {count}"

        # R5: dedup replay must record NOTHING -- assert the hook_warn event
        # (from the first, real invocation) fired exactly once, not twice.
        events = _events(repo)
        warns = [e for e in events if e.get("event") == "hook_warn"]
        assert len(warns) == 1, f"hook_warn should fire once (dedup replay records nothing), got {events}"

    def test_same_tool_use_id_deduped_block_decision_identical(self, repo: Path) -> None:
        session_id = "sess-f5-dedup-block"
        payload = _bash_payload("find / -name x", session_id=session_id, tool_use_id="toolu_same_call_02")

        first = _run_hook(payload, repo)
        second = _run_hook(payload, repo)

        assert first.returncode == 2
        assert second.returncode == 2
        assert json.loads(first.stdout) == json.loads(second.stdout)

    def test_different_tool_use_id_is_a_genuine_retry_and_escalates(self, repo: Path) -> None:
        """Same session + same command text but a DIFFERENT tool_use_id is a
        real second attempt (not a duplicate hook wiring) and must still go
        through the warn-once/block-on-repeat escalation, not get deduped
        into a silent allow."""
        session_id = "sess-f5-real-retry"
        cmd = "tree ."

        first = _run_hook(_bash_payload(cmd, session_id=session_id, tool_use_id="toolu_call_A"), repo)
        second = _run_hook(_bash_payload(cmd, session_id=session_id, tool_use_id="toolu_call_B"), repo)

        assert first.returncode == 0, "first attempt should warn-and-allow"
        assert second.returncode == 2, "second attempt (different tool_use_id) must escalate to block"

    def test_no_tool_use_id_skips_dedup_entirely(self, repo: Path) -> None:
        """Payloads without tool_use_id (e.g. other callers/test harnesses)
        must not be silently deduped -- dedup only applies when Claude Code's
        guaranteed per-call id is present."""
        session_id = "sess-f5-no-id"
        cmd = "tree ."
        first = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        second = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert first.returncode == 0
        assert second.returncode == 2


# --------------------------------------------------------------------------- #
# F6 - find-on-symlink-root guard
# --------------------------------------------------------------------------- #


class TestF6SymlinkGuard:
    def test_find_on_symlink_root_is_blocked_loudly(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_target"
        real_dir.mkdir()
        link = tmp_path / "the_link"
        link.symlink_to(real_dir)

        result = _run_hook(_bash_payload(f"find {link}"), repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert "symlink" in decision["reason"].lower()
        assert str(link) in decision["reason"]

    def test_find_on_symlink_root_not_counted_against_broad_counter(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_target2"
        real_dir.mkdir()
        link = tmp_path / "the_link2"
        link.symlink_to(real_dir)
        session_id = "sess-f6-no-count"

        _run_hook(_bash_payload(f"find {link}", session_id=session_id), repo)
        assert trs.broad_attempt_count(repo, session_id) == 0

    def test_find_on_symlink_root_with_trailing_slash_passes_guard(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_target3"
        real_dir.mkdir()
        link = tmp_path / "the_link3"
        link.symlink_to(real_dir)

        # Trailing slash + bounded maxdepth avoids both the symlink guard
        # AND the ordinary broad-find classification (F4), isolating the
        # guard behavior under test.
        cmd = f"find {link}/ -maxdepth 1"
        result = _run_hook(_bash_payload(cmd), repo)
        assert result.returncode == 0, result.stdout
        if result.returncode == 2:
            decision = json.loads(result.stdout)
            assert "symlink" not in decision["reason"].lower()

    def test_find_symlink_guard_function_directly(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real4"
        real_dir.mkdir()
        link = tmp_path / "link4"
        link.symlink_to(real_dir)
        msg = enforce.find_symlink_guard(f"find {link}")
        assert msg is not None
        assert "trailing slash" in msg

        assert enforce.find_symlink_guard(f"find {link}/") is None
        assert enforce.find_symlink_guard(f"find {real_dir}") is None

    def test_symlink_guard_takes_precedence_over_f4_maxdepth_exception(self, tmp_path: Path, repo: Path) -> None:
        """Pins the precedence between F6 and F4: `find <symlink> -maxdepth 1`
        (no trailing slash) is exactly the RC3 shape (e.g. `find
        /home/agents/.claude/projects -maxdepth 1`) -- it must still hit the
        symlink guard, NOT get waved through as a cost-bounded find just
        because -maxdepth <=2 is present. The guard is checked before any
        broad/catastrophic classification runs."""
        real_dir = tmp_path / "real5"
        real_dir.mkdir()
        link = tmp_path / "link5"
        link.symlink_to(real_dir)

        result = _run_hook(_bash_payload(f"find {link} -maxdepth 1"), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert "symlink" in decision["reason"].lower()


# --------------------------------------------------------------------------- #
# F7 - suggest_rewrite preserves results
# --------------------------------------------------------------------------- #


class TestF7RewritePreservesResults:
    def test_find_name_rewrite_includes_hidden_and_no_ignore(self) -> None:
        s = cr.suggest_rewrite('find . -name "*.py"')
        assert s == "rg --files --hidden --no-ignore -g '*.py' ."

    def test_dot_directory_root_rewrite_also_includes_hidden_and_no_ignore(self) -> None:
        s = cr.suggest_rewrite('find .github -name "*.yml"')
        assert s is not None
        assert "--hidden" in s
        assert "--no-ignore" in s


# --------------------------------------------------------------------------- #
# F8 - exit-path / stdout-content audit
# --------------------------------------------------------------------------- #


class TestF8ExitPathStdoutContent:
    def test_warn_and_allow_stdout_is_exactly_empty(self, repo: Path) -> None:
        result = _run_hook(_bash_payload("tree .", session_id="sess-f8-warn"), repo)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_invalid_json_stdin_fails_open_with_empty_stdout(self, repo: Path) -> None:
        env = os.environ.copy()
        env["TOKEN_REDUCE_REPO_ROOT"] = str(repo)
        env["PYTHONPATH"] = str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not valid json{{{",
            text=True,
            capture_output=True,
            env=env,
            cwd=str(repo),
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.parametrize(
        "payload_factory",
        [
            lambda: _bash_payload("find / -name x", session_id="sess-f8-cata"),
            lambda: {"session_id": "sess-f8-glob", "tool_name": "Glob", "tool_input": {"pattern": "**/*.ts"}},
            lambda: {
                "session_id": "sess-f8-grep",
                "tool_name": "Grep",
                "tool_input": {"pattern": "foo"},
            },
        ],
    )
    def test_every_block_branch_emits_valid_json_with_nonempty_reason(self, repo: Path, payload_factory) -> None:
        result = _run_hook(payload_factory(), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"
        assert isinstance(decision["reason"], str) and decision["reason"].strip()

    def test_no_block_path_emits_updated_input(self, repo: Path) -> None:
        """No code path may silently rewrite the tool call -- only ever an
        explicit block decision or a clean allow."""
        for cmd in ["find / -name x", "tree .", "grep -R foo ."]:
            result = _run_hook(_bash_payload(cmd, session_id=f"sess-f8-no-rewrite-{hash(cmd)}"), repo)
            assert "updatedInput" not in result.stdout


# --------------------------------------------------------------------------- #
# F9 - TOKEN_REDUCE_ENFORCE_MODE=warn
# --------------------------------------------------------------------------- #


class TestF9WarnMode:
    def test_warn_mode_downgrades_block_to_exit_zero_empty_stdout(self, repo: Path) -> None:
        result = _run_hook(
            _bash_payload("find / -name x", session_id="sess-f9-warn"),
            repo,
            env_extra={"TOKEN_REDUCE_ENFORCE_MODE": "warn"},
        )
        assert result.returncode == 0, result.stdout
        assert result.stdout == ""

    def test_warn_mode_still_records_would_be_reason_in_telemetry(self, repo: Path) -> None:
        result = _run_hook(
            _bash_payload("find / -name x", session_id="sess-f9-warn-telemetry"),
            repo,
            env_extra={"TOKEN_REDUCE_ENFORCE_MODE": "warn"},
        )
        assert result.returncode == 0

        events = _events(repo)
        blocks = [e for e in events if e.get("event") == "hook_block"]
        assert blocks, events
        # R6: status must say "warn", not "blocked" -- nothing was actually
        # blocked, so a consumer counting status=="blocked" must not be
        # polluted by telemetry-only warn-mode decisions.
        assert blocks[-1].get("status") == "warn", blocks[-1]
        meta = blocks[-1].get("meta") or {}
        assert meta.get("mode") == "warn"
        assert meta.get("reason"), meta

    def test_normal_mode_unaffected_by_default(self, repo: Path) -> None:
        result = _run_hook(_bash_payload("find / -name x", session_id="sess-f9-normal"), repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"

    def test_warn_mode_env_value_other_than_warn_is_normal_mode(self, repo: Path) -> None:
        result = _run_hook(
            _bash_payload("find / -name x", session_id="sess-f9-other-env"),
            repo,
            env_extra={"TOKEN_REDUCE_ENFORCE_MODE": "block"},
        )
        assert result.returncode == 2


# --------------------------------------------------------------------------- #
# Round 3 code review fixes (R1-R8)
# --------------------------------------------------------------------------- #


class TestR1FindGlobalOptions:
    """`find` accepts GNU/POSIX global options (-H/-L/-P, -O<level>, -D
    <opts>) BEFORE its root path. Every find-root regex must tolerate them
    or a command like `find -L / -name '*.py'` silently evades every
    classifier by not looking like `find\\s+(\\.|/)` at all -- confirmed
    live."""

    def test_find_dash_L_root_is_catastrophic_live(self, repo: Path) -> None:
        result = _run_hook(_bash_payload("find -L / -name '*.py'"), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert "catastrophic" in decision["reason"].lower()

    def test_find_dash_H_dot_root_still_detected(self) -> None:
        assert cr.is_broad_find("find -H . -name '*.py'") is True

    def test_find_dash_O_level_root_still_detected(self) -> None:
        assert cr.is_broad_find("find -O3 / -maxdepth 1") is True

    def test_find_dash_D_debugopts_root_still_detected(self) -> None:
        assert cr.is_broad_find("find -D tree / -maxdepth 1") is True

    def test_find_global_opts_maxdepth_exception_still_applies(self, tmp_path: Path) -> None:
        """F4's cost-bounded exception must still work THROUGH the global
        options, not just plain finds."""
        target = tmp_path / "some" / "specific" / "dir"
        target.mkdir(parents=True)
        assert cr.is_broad_find(f"find -L {target} -maxdepth 1") is False

    def test_find_no_root_at_all_unaffected(self) -> None:
        assert cr.is_broad_find("find scripts -maxdepth 1") is False


class TestR2CompoundSegmentClassification:
    """The exact R2 repro: `find /a/b/c -maxdepth 1; find /d/e/f -name
    '*.py'` used to classify as not-broad, because the first find's
    -maxdepth was found ANYWHERE in the line and treated as satisfying the
    whole compound command, masking the second find's genuinely-unbounded
    scan."""

    COMPOUND_CMD = "find /a/b/c -maxdepth 1; find /d/e/f -name '*.py'"

    def test_compound_find_classified_broad_directly(self, repo: Path) -> None:
        _, broad, _, _ = enforce.classify_bash_command([self.COMPOUND_CMD], repo)
        assert broad is True

    def test_compound_find_second_segment_still_broad_live(self, repo: Path) -> None:
        session_id = "sess-r2"
        first = _run_hook(_bash_payload(self.COMPOUND_CMD, session_id=session_id), repo)
        assert first.returncode == 0, "first attempt should warn-and-allow"
        second = _run_hook(_bash_payload(self.COMPOUND_CMD, session_id=session_id), repo)
        assert second.returncode == 2, "repeat attempt must escalate to block"

    def test_compound_find_blocks_immediately_while_pending(self, repo: Path) -> None:
        session_id = "sess-r2-pending"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(_bash_payload(self.COMPOUND_CMD, session_id=session_id), repo)
        assert result.returncode == 2, result.stdout

    def test_both_segments_individually_maxdepth_bounded_is_not_broad(self, tmp_path: Path, repo: Path) -> None:
        """Control: segmentation must not become OVER-eager -- two
        genuinely cost-bounded finds joined by `;` must still pass clean."""
        a = tmp_path / "aaa" / "bbb" / "ccc"
        b = tmp_path / "ddd" / "eee" / "fff"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        cmd = f"find {a} -maxdepth 1; find {b} -maxdepth 1"
        _, broad, _, _ = enforce.classify_bash_command([cmd], repo)
        assert broad is False


class TestR3PendingGateWaitLoopRgSmuggle:
    """The exact R3 repro: `while true; do sleep 5; rg -n foo .; done` used
    to be ALLOWED while pending -- the wait-loop branch matched, and
    is_exploratory_rg only fires on a segment-LEADING rg, which the whole
    (unsegmented) line didn't have (it starts with "while")."""

    def test_wait_loop_smuggled_rg_still_blocks_while_pending(self, repo: Path) -> None:
        session_id = "sess-r3"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        cmd = "while true; do sleep 5; rg -n foo .; done"
        result = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert result.returncode == 2, result.stdout

    def test_wait_loop_smuggled_rg_disqualifies_is_non_discovery_command(self, repo: Path) -> None:
        cmd = "while true; do sleep 5; rg -n foo .; done"
        assert enforce.is_non_discovery_command(cmd, repo) is False

    def test_genuine_wait_loop_without_scan_still_passes_pending_gate(self, repo: Path) -> None:
        """Control: a real wait/poll loop with no embedded scan must still
        bypass the pending gate -- proves R3's fix targets the smuggled
        scan specifically, not wait loops in general."""
        session_id = "sess-r3-control"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        cmd = "while true; do sleep 5; echo waiting; done"
        result = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert result.returncode == 0, result.stdout


class TestR4WrapperStrippedLeadingCommand:
    """`sudo fd .`, `env FOO=1 fd .`, `time fd` decorate the front of a
    segment without changing what actually runs -- must still count fd/tree
    as the leading command, not evade the ^fd/^tree anchor."""

    @pytest.mark.parametrize(
        "command",
        [
            "sudo fd .",
            "env FOO=1 fd .",
            "time fd",
            "sudo env FOO=1 nohup fd .",
        ],
    )
    def test_wrapped_fd_still_counts_as_broad(self, command: str) -> None:
        assert enforce.matches_broad_bash(command) is True

    def test_wrapped_fd_blocks_pending_gate_live(self, repo: Path) -> None:
        session_id = "sess-r4"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(_bash_payload("sudo fd .", session_id=session_id), repo)
        assert result.returncode == 2, result.stdout

    def test_envsubst_not_mistaken_for_env_wrapper(self) -> None:
        """Guard against an over-eager `env` strip: `envsubst` is a
        different binary, not `env` decorating a command."""
        assert enforce.matches_broad_bash("envsubst < template.txt") is False


class TestR5DedupCoversNonBashBlocks:
    """R5: dedup moved to the top of main() and decision-recording into
    block()/warn_and_allow(), so it now covers Glob/Grep/Read/symlink-guard
    blocks too, not just Bash's broad-attempt path."""

    def test_glob_block_deduped_across_dual_wiring(self, repo: Path) -> None:
        payload = {
            "session_id": "sess-r5-glob",
            "tool_use_id": "toolu_glob_dual",
            "tool_name": "Glob",
            "tool_input": {"pattern": "**/*.ts"},
        }
        first = _run_hook(payload, repo)
        second = _run_hook(payload, repo)
        assert first.returncode == 2
        assert second.returncode == 2
        assert first.stdout == second.stdout

        events = _events(repo)
        blocks = [e for e in events if e.get("event") == "hook_block"]
        assert len(blocks) == 1, f"Glob block telemetry must not double-record under dual wiring, got {events}"

    def test_symlink_guard_block_deduped_across_dual_wiring(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_r5"
        real_dir.mkdir()
        link = tmp_path / "link_r5"
        link.symlink_to(real_dir)
        payload = _bash_payload(
            f"find {link}", session_id="sess-r5-symlink", tool_use_id="toolu_symlink_dual"
        )

        first = _run_hook(payload, repo)
        second = _run_hook(payload, repo)
        assert first.returncode == 2
        assert second.returncode == 2
        assert first.stdout == second.stdout

        events = _events(repo)
        blocks = [e for e in events if e.get("event") == "hook_block"]
        assert len(blocks) == 1, f"symlink guard block must not double-record under dual wiring, got {events}"

    def test_dual_wiring_does_not_produce_spurious_post_block_classification(self, repo: Path) -> None:
        """R5(b): a second wiring's consume_block must not eat the marker
        the first wiring's block() just wrote and then spuriously classify
        the SAME blocked call as a post_block_escape/abandon."""
        payload = _bash_payload(
            "find / -name x", session_id="sess-r5-postblock", tool_use_id="toolu_postblock_dual"
        )
        _run_hook(payload, repo)
        _run_hook(payload, repo)

        events = _events(repo)
        post_block_events = [
            e for e in events if e.get("event") in {"post_block_escape", "post_block_abandon"}
        ]
        assert not post_block_events, f"dual-wiring replay must not trigger post-block classification, got {events}"


class TestR7PostBlockClassifierQuoteAware:
    def test_post_block_escape_not_fooled_by_quoted_payload(self, repo: Path) -> None:
        """R7(c): the post-block Bash escape classifier must use
        quote-aware surfaces, not raw lines -- an inert quoted payload
        containing broad-looking text (e.g. an echoed JSON blob) must not
        be misclassified as an escape attempt."""
        session_id = "sess-r7c"
        _run_hook(_bash_payload("find / -name x", session_id=session_id), repo)
        payload = _bash_payload(
            "echo '{\"command\":\"find /x\"}'",
            session_id=session_id,
        )
        result = _run_hook(payload, repo)
        assert result.returncode == 0

        events = _events(repo)
        escapes = [e for e in events if e.get("event") == "post_block_escape"]
        assert not escapes, f"quoted inert text must not be classified as an escape, got {events}"


# --------------------------------------------------------------------------- #
# Round 4 - Codex external review of PR #87 (C1-C3)
# --------------------------------------------------------------------------- #


class TestC1DoubleQuotedCommandSubstitution:
    """Double quotes suppress word-splitting/globbing but NOT command
    substitution -- `echo "$(find / -name x)"` really runs `find / -name x`
    for real. Single quotes suppress ALL expansion and are genuinely inert."""

    def test_command_substitution_is_catastrophic_non_pending(self, repo: Path) -> None:
        cmd = 'echo "$(find / -name x)"'
        result = _run_hook(_bash_payload(cmd, session_id="sess-c1-cata"), repo)
        assert result.returncode == 2, result.stdout
        decision = json.loads(result.stdout)
        assert "catastrophic" in decision["reason"].lower()

    def test_command_substitution_blocks_while_pending(self, repo: Path) -> None:
        session_id = "sess-c1-pending"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        cmd = 'echo "$(find / -name x)"'
        result = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert result.returncode == 2, result.stdout

    def test_ls_dash_R_command_substitution_blocked(self, repo: Path) -> None:
        cmd = 'echo "$(ls -R /)"'
        result = _run_hook(_bash_payload(cmd, session_id="sess-c1-lsr"), repo)
        assert result.returncode == 2, result.stdout

    def test_plain_double_quoted_text_still_allowed(self, repo: Path) -> None:
        result = _run_hook(_bash_payload('echo "plain text"', session_id="sess-c1-plain"), repo)
        assert result.returncode == 0, result.stdout

    def test_single_quoted_dollar_paren_is_inert(self, repo: Path) -> None:
        """Single quotes suppress command substitution entirely -- this is
        literal text `$(find / -name x)`, never executed."""
        result = _run_hook(
            _bash_payload("echo '$(find / -name x)'", session_id="sess-c1-single"), repo
        )
        assert result.returncode == 0, result.stdout

    def test_surfaces_directly(self) -> None:
        surfaces = cr.command_scan_surfaces('echo "$(find / -name x)"')
        assert any(cr.is_catastrophic(s) for s in surfaces)
        surfaces_single = cr.command_scan_surfaces("echo '$(find / -name x)'")
        assert not any(cr.is_catastrophic(s) for s in surfaces_single)


class TestC2HelperMustLeadSegment:
    """HELPER_COMMAND_RE.search() on the whole first line let a helper
    mention ANYWHERE credit compliance, even when the actual scan ran in a
    sibling segment that was never classified."""

    def test_helper_then_scan_via_and_and_blocks(self, repo: Path) -> None:
        session_id = "sess-c2-andand"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        cmd = "token-reduce-paths auth && find / -name x"
        result = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert result.returncode == 2, result.stdout
        assert trs.is_pending(repo, session_id) is True, "pending must NOT be cleared when a scan is present"

    def test_echoed_helper_name_then_scan_via_semicolon_blocks(self, repo: Path) -> None:
        session_id = "sess-c2-semicolon"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        cmd = "echo token-reduce-paths; find / -name x"
        result = _run_hook(_bash_payload(cmd, session_id=session_id), repo)
        assert result.returncode == 2, result.stdout
        assert trs.is_pending(repo, session_id) is True

    def test_plain_helper_invocation_still_allowed_and_clears_pending(self, repo: Path) -> None:
        session_id = "sess-c2-plain"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(
            _bash_payload("./scripts/token-reduce-paths.sh topic", session_id=session_id), repo
        )
        assert result.returncode == 0, result.stdout
        assert trs.is_pending(repo, session_id) is False

    def test_uv_run_wrapped_helper_still_counts(self, repo: Path) -> None:
        session_id = "sess-c2-uvrun"
        trs.mark_pending(repo, session_id, "where is the auth hook defined in this repo")
        result = _run_hook(
            _bash_payload("uv run token-reduce-paths.py topic", session_id=session_id), repo
        )
        assert result.returncode == 0, result.stdout
        assert trs.is_pending(repo, session_id) is False


class TestC3SymlinkGuardHonorsFollowOptions:
    """`find -H`/`find -L` make find follow the symlinked root -- blocking
    them recommends, as the fix, exactly what the caller already did."""

    def test_find_dash_H_symlink_passes_guard(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_c3h"
        real_dir.mkdir()
        link = tmp_path / "link_c3h"
        link.symlink_to(real_dir)
        msg = enforce.find_symlink_guard(f"find -H {link} -name x")
        assert msg is None

    def test_find_dash_L_symlink_passes_guard(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_c3l"
        real_dir.mkdir()
        link = tmp_path / "link_c3l"
        link.symlink_to(real_dir)
        msg = enforce.find_symlink_guard(f"find -L {link} -name x")
        assert msg is None

    def test_bare_find_symlink_still_blocks(self, tmp_path: Path, repo: Path) -> None:
        real_dir = tmp_path / "real_c3bare"
        real_dir.mkdir()
        link = tmp_path / "link_c3bare"
        link.symlink_to(real_dir)
        msg = enforce.find_symlink_guard(f"find {link} -name x")
        assert msg is not None
        assert "symlink" in msg.lower()

    def test_find_dash_H_live_still_subject_to_normal_classification(
        self, tmp_path: Path, repo: Path
    ) -> None:
        """The guard is skipped, but the command is still a `find /...`-
        shaped scan and goes through the ordinary broad/catastrophic path."""
        real_dir = tmp_path / "real_c3live"
        real_dir.mkdir()
        link = tmp_path / "link_c3live"
        link.symlink_to(real_dir)
        result = _run_hook(
            _bash_payload(f"find -H {link} -name x", session_id="sess-c3-live"), repo
        )
        decision = json.loads(result.stdout) if result.stdout.strip() else None
        if decision is not None:
            assert "symlink" not in decision["reason"].lower()
