"""Regression tests for the F1-F9 hook-diagnosis fixes (2026-09-12 builder pass).

Root causes fixed (see the task brief this file accompanies):

  RC1 (cold-start block storm, historical): mark_pending() cross-poisoned
      every session in the repo via a duplicate "default.json" write; the
      pending gate then default-blocked almost all Bash regardless of cost;
      pending survived a compliant helper call.
  RC2 (broad-scan counter too aggressive): raw find-root regex ignored
      -maxdepth/specificity; broad patterns matched inside quoted/inert
      text; dual hook-wiring layers double-counted a single tool call.
  RC3 (silent wrong answers): `find <symlink-root>` silently returns
      nothing; the rg-rewrite suggestion silently dropped hidden/ignored
      files.

Fixes, by id:
  F1 - (removed 2026-09-28 along with the pending gate itself -- was
       token_reduce_state: no cross-session pending poisoning.)
  F2 - broad/catastrophic classification for targeted vs. exploratory Bash.
       (Originally "the pending gate applies the same classification as
       non-pending, not a blanket default-block" -- the pending gate was
       removed 2026-09-28 as dead code once nothing set the marker, see
       references/worktree-deploy-sync.md, so this classification is now
       simply the hook's only behavior.)
  F3 - quote-aware broad-pattern matching with command-executor recursion.
  F4 - cost-aware `find -maxdepth <=2 <specific-dir>` is not broad.
  F5 - double-run dedup keyed on tool_use_id (not raw command+time alone).
  F6 - find-on-symlink-root guard (fail loud, not silently empty).
  F7 - suggest_rewrite's find->rg rewrite preserves results (--hidden --no-ignore).
  F8 - exit-path / stdout-content audit.
  F9 - TOKEN_REDUCE_ENFORCE_MODE=warn downgrades blocks to telemetry-only.
  (Helper-clears-pending, C2's "helper must lead segment", and R3's
  wait-loop-smuggle guard were all pending-gate-only mechanisms, removed
  2026-09-28 along with the gate; their non-pending assertions, where any
  existed, are preserved above and in TestF3QuoteAwareBroadMatching /
  TestR2CompoundSegmentClassification.)
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
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
# F2 - broad/catastrophic classification (targeted vs. genuine scans)
# --------------------------------------------------------------------------- #
#
# F1 (no cross-session pending poisoning) and the "helper clears pending"
# behavior were retired along with the PreToolUse enforcer's "pending"
# first-move discovery gate itself (removed 2026-09-28 as dead code once
# nothing set the marker -- see references/worktree-deploy-sync.md). F2's
# classification -- targeted commands (which/date/ls <dir>/cat <file>/stat
# <file>) pass, catastrophic scans still block -- is unconditional today, so
# the tests below simply drop the pending setup and assert the same
# outcomes with no state at all.


class TestF2BashClassification:
    @pytest.mark.parametrize(
        "command",
        [
            "which rg",
            "date",
        ],
    )
    def test_targeted_commands_pass(self, repo: Path, command: str) -> None:
        session_id = "sess-f2-targeted"
        result = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert result.returncode == 0, f"{command!r} should pass, got {result.stdout!r}"
        assert result.stdout.strip() == ""




    def test_catastrophic_find_root_still_blocks(self, repo: Path) -> None:
        session_id = "sess-f2-catastrophic"
        result = _run_hook(_bash_payload("find / -name '*.py'", session_id=session_id), repo)
        assert result.returncode == 2
        decision = json.loads(result.stdout)
        assert decision["decision"] == "block"
        events = _events(repo)
        cata = [e for e in events if e.get("event") == "hook_block" and (e.get("meta") or {}).get("policy") == "catastrophic"]
        assert cata, events


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
    def test_argument_position_passes_live(self, repo: Path, command: str) -> None:
        session_id = f"sess-f3-followup-{hash(command)}"
        result = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert result.returncode == 0, f"{command!r} should pass, got {result.stdout!r}"
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
    def test_command_position_still_blocks_after_repeat_live(self, repo: Path, command: str) -> None:
        session_id = f"sess-f3-followup-block-{hash(command)}"
        first = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert first.returncode == 0, f"{command!r} first attempt should warn-and-allow, got {first.stdout!r}"
        second = _run_hook(_bash_payload(command, session_id=session_id), repo)
        assert second.returncode == 2, f"{command!r} repeat attempt should block, got {second.stdout!r}"


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

    def test_maxdepth_three_is_still_broad(self, tmp_path: Path) -> None:
        target = tmp_path / "some" / "specific" / "dir"
        assert cr.is_broad_find(f"find {target} -maxdepth 3") is True






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



# --------------------------------------------------------------------------- #
# F8 - exit-path / stdout-content audit
# --------------------------------------------------------------------------- #


class TestF8ExitPathStdoutContent:

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









class TestR4WrapperStrippedLeadingCommand:
    """`sudo fd .`, `env FOO=1 fd .`, `time fd` decorate the front of a
    segment without changing what actually runs -- must still count fd/tree
    as the leading command, not evade the ^fd/^tree anchor."""


    def test_wrapped_fd_blocks_after_repeat_live(self, repo: Path) -> None:
        session_id = "sess-r4"
        first = _run_hook(_bash_payload("sudo fd .", session_id=session_id), repo)
        assert first.returncode == 0, f"first attempt should warn-and-allow, got {first.stdout!r}"
        second = _run_hook(_bash_payload("sudo fd .", session_id=session_id), repo)
        assert second.returncode == 2, second.stdout







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


class TestR5DedupCoversNonBashBlocks:
    """R5: dedup moved to the top of main() and decision-recording into
    block()/warn_and_allow(), so it now covers Glob/Grep/Read/symlink-guard
    blocks too, not just Bash's broad-attempt path."""

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
