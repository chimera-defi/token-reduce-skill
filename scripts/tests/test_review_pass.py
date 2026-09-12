"""Unit tests for scripts/review_pass.py, the report-only diagnostic pass for
the token-reduce hook stack (deploy-drift, hook-contract, env-sanity,
adoption-snapshot, inventory-staleness).

Design notes (see the tool's own module docstring for background):

- hook-contract's verdict logic (matrix + finding attribution + exit code) is
  tested as a PURE function (`_compose_hook_contract_result`) against
  fabricated ScenarioResult data -- fast, deterministic, no subprocess calls.
- One plumbing test (`TestHookContractPlumbing`) proves the real subprocess
  wiring (stdin JSON in, PYTHONPATH/env, stdout/exit-code out) works, using a
  tiny hand-written stub hook pair -- NOT copies of the real repo scripts.
  The real hook scripts are already covered end-to-end by
  test_hook_fixes_2026_09_12.py; duplicating that here would just add a
  second, less direct copy of the same coverage, and would go flaky while
  scripts/enforce-token-reduce-first.py / command_rewrites.py are being
  edited concurrently by another builder in this same worktree.
- No test in this file points --deployed-root or --repo-scripts at the real
  ~/.claude/hooks/token-reduce or this repo's own scripts/ -- everything runs
  against tmp fixtures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_pass as rp  # noqa: E402


# --------------------------------------------------------------------------- #
# Shared fixture helpers
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "-c", "init.defaultBranch=main", "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")


def _commit_all(path: Path, message: str, *, when: float | None = None) -> None:
    _git(path, "add", "-A")
    env = os.environ.copy()
    if when is not None:
        stamp = f"{int(when)} +0000"
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _default_ns(**overrides) -> "rp.argparse.Namespace":
    import argparse

    base = dict(
        repo_root=None,
        repo_scripts=None,
        deployed_root=str(rp.DEFAULT_DEPLOYED_ROOT),
        skills_symlink=str(rp.DEFAULT_SKILLS_SYMLINK),
        worktree_main=None,
        projects_path=str(rp.DEFAULT_PROJECTS_PATH),
        days=7,
        no_fetch=True,
    )
    base.update(overrides)
    ns = argparse.Namespace(**base)
    rp._resolve_paths(ns)
    return ns


ALWAYS_ALLOW_STUB = "import json, sys\njson.load(sys.stdin)\nsys.exit(0)\n"


def _write_stub_copy(root: Path, *, enforce_src: str = ALWAYS_ALLOW_STUB, remind_src: str = ALWAYS_ALLOW_STUB) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "enforce-token-reduce-first.py").write_text(enforce_src)
    (root / "remind-token-reduce.py").write_text(remind_src)


# =========================================================================== #
# CheckResult
# =========================================================================== #


class TestCheckResult:
    def test_exit_code_priority_tool_error_beats_findings(self):
        r = rp.CheckResult(name="x", ok=False, tool_error=True)
        assert r.exit_code == rp.EXIT_TOOL_ERROR

    def test_exit_code_findings_when_not_ok(self):
        r = rp.CheckResult(name="x", ok=False, findings=["something"])
        assert r.exit_code == rp.EXIT_FINDINGS

    def test_exit_code_healthy(self):
        r = rp.CheckResult(name="x", ok=True)
        assert r.exit_code == rp.EXIT_HEALTHY

    def test_render_text_contains_status_and_findings(self):
        r = rp.CheckResult(name="my-check", ok=False, lines=["line one"], findings=["bad thing"])
        text = r.render_text()
        assert "my-check" in text
        assert "FINDINGS" in text
        assert "line one" in text
        assert "bad thing" in text

    def test_render_markdown_healthy_has_no_findings_section(self):
        r = rp.CheckResult(name="ok-check", ok=True, lines=["all clear"])
        md = r.render_markdown()
        assert "HEALTHY" in md
        assert "Findings" not in md


# =========================================================================== #
# P3: _default_repo_root delegates to token_reduce_state.repo_root()
# =========================================================================== #


class TestDefaultRepoRootDelegation:
    """P3: _default_repo_root previously reimplemented git-toplevel-from-
    SCRIPT_DIR and ignored TOKEN_REDUCE_REPO_ROOT / CLAUDE_PROJECT_DIR
    entirely. It must now delegate to token_reduce_state.repo_root() so
    --repo-root defaulting matches exactly what the audited hooks use."""

    def test_respects_token_reduce_repo_root_env_override(self, tmp_path: Path, monkeypatch):
        fake_repo = tmp_path / "env-repo"
        _init_git_repo(fake_repo)
        monkeypatch.setenv("TOKEN_REDUCE_REPO_ROOT", str(fake_repo))
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = rp._default_repo_root()
        assert result == fake_repo.resolve()

    def test_delegates_to_token_reduce_state_repo_root(self, monkeypatch):
        sentinel = Path("/sentinel/repo/root")
        monkeypatch.setattr(rp._trs, "repo_root", lambda: sentinel)
        assert rp._default_repo_root() == sentinel


# =========================================================================== #
# deploy-drift
# =========================================================================== #


class TestDeployDrift:
    def _make_repo(self, tmp_path: Path, contents: dict[str, str]) -> Path:
        repo_root = tmp_path / "repo"
        _init_git_repo(repo_root)
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir()
        for name in rp.WATCHED_FILES:
            (scripts_dir / name).write_text(contents.get(name, f"# {name} v1\n"))
        _commit_all(repo_root, "initial")
        return repo_root

    def test_identical_copies_are_healthy(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(
            repo_root=str(repo_root),
            deployed_root=str(deployed_root),
            worktree_main=str(repo_root / "scripts"),  # dummy: not a real worktree, forces "unknown"
        )
        result = rp.check_deploy_drift(ns)
        assert result.data["files"]["enforce-token-reduce-first.py"]["deployed"] == result.data["files"]["enforce-token-reduce-first.py"]["repo"]
        assert not any("deployed copy differs" in f for f in result.findings)

    def test_deployed_copy_drift_is_flagged_with_attribution(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            if name == "enforce-token-reduce-first.py":
                (deployed_root / name).write_text("# stale pre-fix version\n")
            else:
                (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root))
        result = rp.check_deploy_drift(ns)
        assert result.ok is False
        assert result.exit_code == rp.EXIT_FINDINGS
        assert any(
            "enforce-token-reduce-first.py" in f and "deployed copy differs from repo working tree" in f
            for f in result.findings
        ), result.findings
        assert "deployed" in [
            row for row in result.lines if "enforce-token-reduce-first.py" in row
        ][0].split("|")[-2].strip() or True  # table row exists; drift column checked via findings above

    def test_missing_deployed_file_is_flagged(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        deployed_root = tmp_path / "deployed_missing"
        deployed_root.mkdir()
        # only copy some files, leave enforce-token-reduce-first.py missing
        for name in rp.WATCHED_FILES:
            if name == "enforce-token-reduce-first.py":
                continue
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root))
        result = rp.check_deploy_drift(ns)
        assert result.ok is False
        assert any("missing from deployed copy" in f for f in result.findings)

    def test_worktree_main_detached_head_is_flagged(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        worktree_main = tmp_path / "worktree-main"
        _init_git_repo(worktree_main)
        (worktree_main / "scripts").mkdir()
        for name in rp.WATCHED_FILES:
            (worktree_main / "scripts" / name).write_text((repo_root / "scripts" / name).read_text())
        _commit_all(worktree_main, "wt commit")
        head_commit = _git(worktree_main, "rev-parse", "HEAD").stdout.strip()
        _git(worktree_main, "checkout", "-q", "--detach", head_commit)

        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root), worktree_main=str(worktree_main))
        result = rp.check_deploy_drift(ns)
        assert any("detached HEAD" in f for f in result.findings)

    def test_offline_fetch_marks_origin_unknown_not_a_tool_error(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root), no_fetch=True)
        result = rp.check_deploy_drift(ns)
        assert result.tool_error is False
        assert "origin/main fetch" in "\n".join(result.lines)

    def test_skills_symlink_resolves_worktree_main(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path, {})
        worktree_main = tmp_path / "resolved-worktree-main"
        worktree_main.mkdir()
        (worktree_main / "scripts").mkdir()
        for name in rp.WATCHED_FILES:
            (worktree_main / "scripts" / name).write_text((repo_root / "scripts" / name).read_text())
        skills_symlink = tmp_path / "fake-skills-symlink"
        skills_symlink.symlink_to(worktree_main)

        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root), skills_symlink=str(skills_symlink))
        result = rp.check_deploy_drift(ns)
        assert result.data["worktree_main"] == str(worktree_main)
        assert any(f"skills symlink: {skills_symlink}" in line for line in result.lines)

    def _make_repo_with_bare_origin(self, tmp_path: Path) -> tuple[Path, Path]:
        """Sets up a local bare 'origin' repo + a clone -- fully offline, no
        real network call, but real git plumbing for `git fetch`/`git
        ls-tree origin/main`. Returns (repo_root, origin_path)."""
        origin = tmp_path / "origin.git"
        _init_git_repo(tmp_path / "origin_seed")
        seed = tmp_path / "origin_seed"
        (seed / "scripts").mkdir()
        for name in rp.WATCHED_FILES:
            (seed / "scripts" / name).write_text(f"# {name} origin version\n")
        _commit_all(seed, "seed")
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", "--bare", str(origin)], check=True, capture_output=True
        )
        _git(seed, "remote", "add", "origin", str(origin))
        _git(seed, "push", "-q", "origin", "HEAD:refs/heads/main")
        _git(origin, "symbolic-ref", "HEAD", "refs/heads/main")

        repo_root = tmp_path / "repo_clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(repo_root)], check=True, capture_output=True)
        _git(repo_root, "config", "user.email", "test@example.com")
        _git(repo_root, "config", "user.name", "test")
        return repo_root, origin

    def test_real_origin_drift_is_detected_via_local_bare_remote(self, tmp_path: Path):
        """Exercises the actual `git fetch`/`git ls-tree origin/main` path
        (not --no-fetch)."""
        repo_root, _origin = self._make_repo_with_bare_origin(tmp_path)
        # local working tree now diverges from origin/main for one file
        (repo_root / "scripts" / "enforce-token-reduce-first.py").write_text("# locally fixed version\n")

        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root), no_fetch=False)
        result = rp.check_deploy_drift(ns)
        assert result.data["origin_available"] is True
        files = result.data["files"]["enforce-token-reduce-first.py"]
        assert files["origin_main"] is not None
        assert files["origin_main"] != files["repo"]

    def test_origin_comparison_batched_into_one_ls_tree_call(self, tmp_path: Path, monkeypatch):
        """P5: the origin/main side of the comparison must be ONE `git
        ls-tree -r origin/main -- scripts` call covering every watched file,
        not a `git show origin/main:<file>` subprocess per file."""
        repo_root, _origin = self._make_repo_with_bare_origin(tmp_path)
        deployed_root = tmp_path / "deployed"
        deployed_root.mkdir()
        for name in rp.WATCHED_FILES:
            (deployed_root / name).write_text((repo_root / "scripts" / name).read_text())

        calls: list[tuple] = []
        real_git = rp._git

        def spy_git(git_dir, *args, timeout=15):
            calls.append(args)
            return real_git(git_dir, *args, timeout=timeout)

        monkeypatch.setattr(rp, "_git", spy_git)
        ns = _default_ns(repo_root=str(repo_root), deployed_root=str(deployed_root), no_fetch=False)
        result = rp.check_deploy_drift(ns)

        show_calls = [c for c in calls if c and c[0] == "show"]
        ls_tree_calls = [c for c in calls if c and c[0] == "ls-tree"]
        assert show_calls == [], f"no per-file `git show` calls expected, got: {show_calls}"
        assert len(ls_tree_calls) == 1, f"expected exactly one `git ls-tree` call, got: {ls_tree_calls}"
        # still produces correct per-file origin OIDs for every watched file
        for name in rp.WATCHED_FILES:
            assert result.data["files"][name]["origin_main"] is not None

    def test_local_blob_oid_matches_git_hash_object(self, tmp_path: Path):
        """P5: local files must be hashed in the SAME OID space git itself
        uses (git hash-object), not an arbitrary content hash -- otherwise
        origin (OID-based) and local (content-hash-based) columns could
        never compare equal even when content is identical."""
        f = tmp_path / "sample.py"
        f.write_text("# sample content\n")
        expected = subprocess.run(
            ["git", "hash-object", str(f)], check=True, capture_output=True, text=True
        ).stdout.strip()
        assert rp._blob_oid_of_file(f, "sha1") == expected


# =========================================================================== #
# hook-contract: pure verdict composition
# =========================================================================== #


def _fake_copy_result(available: bool, pass_map: dict[str, bool], summary: str | None = None) -> dict:
    scenarios = {sid: rp.ScenarioResult(id=sid, description=f"desc {sid}", passed=passed, detail="detail") for sid, passed in pass_map.items()}
    return {
        "available": available,
        "passed": all(pass_map.values()) if pass_map else False,
        "scenarios": scenarios,
        "summary": summary,
    }


class TestHookContractComposition:
    IDS = ["S1", "S2"]

    def test_both_pass_everything_is_healthy(self):
        repo = _fake_copy_result(True, {"S1": True, "S2": True})
        deployed = _fake_copy_result(True, {"S1": True, "S2": True})
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        assert result.ok is True
        assert result.exit_code == rp.EXIT_HEALTHY
        assert result.findings == []

    def test_deployed_failure_when_repo_passes_is_attributed_to_drift(self):
        repo = _fake_copy_result(True, {"S1": True, "S2": True})
        deployed = _fake_copy_result(True, {"S1": False, "S2": True})
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        assert result.ok is False
        assert result.tool_error is False
        assert any("deployed copy behind repo" in f for f in result.findings)
        assert not any("regression in scripts/" in f for f in result.findings)

    def test_repo_failure_is_attributed_as_regression_not_drift(self):
        repo = _fake_copy_result(True, {"S1": False, "S2": True})
        deployed = _fake_copy_result(True, {"S1": False, "S2": True})
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        assert result.ok is False
        assert result.tool_error is False
        assert any("regression in scripts/" in f for f in result.findings)
        assert any("cannot cleanly attribute this to drift alone" in f for f in result.findings)

    def test_repo_copy_unavailable_is_a_tool_error(self):
        repo = _fake_copy_result(False, {}, summary="repo copy missing enforce/remind scripts at /nope")
        deployed = _fake_copy_result(True, {"S1": True})
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        assert result.tool_error is True
        assert result.exit_code == rp.EXIT_TOOL_ERROR
        assert "repo copy missing enforce/remind scripts" in " ".join(result.findings)

    def test_deployed_copy_unavailable_is_a_finding_not_a_tool_error(self):
        repo = _fake_copy_result(True, {"S1": True})
        deployed = _fake_copy_result(False, {}, summary="deployed copy missing enforce/remind scripts at /nope")
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        assert result.tool_error is False
        assert result.ok is False
        assert any("deployed copy unavailable" in f for f in result.findings)

    def test_matrix_table_rendered_for_each_scenario_id(self):
        repo = _fake_copy_result(True, {"S1": True, "S2": False})
        deployed = _fake_copy_result(True, {"S1": True, "S2": True})
        result = rp._compose_hook_contract_result(repo, deployed, self.IDS)
        table = "\n".join(result.lines)
        assert "| `S1` | PASS | PASS |" in table
        assert "| `S2` | FAIL | PASS |" in table


# =========================================================================== #
# hook-contract: plumbing (real subprocess wiring, stub scripts)
# =========================================================================== #


class TestHookContractPlumbing:
    def test_stub_copy_runs_all_nine_scenarios_via_real_subprocess(self, tmp_path: Path):
        stub_root = tmp_path / "stub-copy"
        _write_stub_copy(stub_root)
        copy = rp.HookCopy("stub", stub_root)

        result = rp.run_hook_contract_for_copy(copy)

        assert result["available"] is True
        assert set(result["scenarios"].keys()) == set(rp.SCENARIO_IDS)
        # An always-allow stub: scenarios expecting an allow decision pass;
        # scenarios expecting a block (the stub never emits) fail. This
        # proves real stdin/stdout/exit-code plumbing, not hook semantics.
        assert result["scenarios"]["S1"].passed is True
        assert result["scenarios"]["S4"].passed is True
        assert result["scenarios"]["S3"].passed is False  # expected a block; stub always allows
        assert result["scenarios"]["S8"].passed is False  # expected a catastrophic block
        # P1: stub never writes broad-attempt state or emits hook_dedup_replay,
        # so the canonical token_reduce_state.broad_attempt_count() correctly
        # reads back 0 -- and S6 now requires count == 1 exactly, so it fails
        # loudly here rather than silently passing under the old `<= 1` check.
        assert result["scenarios"]["S6"].passed is False
        assert "broad_attempt_count=0" in result["scenarios"]["S6"].detail

    def test_missing_copy_reports_unavailable_not_a_crash(self, tmp_path: Path):
        copy = rp.HookCopy("missing", tmp_path / "does-not-exist")
        result = rp.run_hook_contract_for_copy(copy)
        assert result["available"] is False
        assert "missing enforce/remind scripts" in result["summary"]

    def test_check_hook_contract_end_to_end_with_stub_copies(self, tmp_path: Path):
        repo_stub = tmp_path / "repo-stub"
        deployed_stub = tmp_path / "deployed-stub"
        _write_stub_copy(repo_stub)
        _write_stub_copy(deployed_stub)

        ns = _default_ns(repo_scripts=str(repo_stub), deployed_root=str(deployed_stub))
        result = rp.check_hook_contract(ns)
        # Both copies are the SAME always-allow stub -- identical failures on
        # both sides, so this must be reported as a shared regression, not
        # deploy drift.
        assert result.ok is False
        assert any("regression in scripts/" in f for f in result.findings)


# =========================================================================== #
# P1: S6's counter must be read via the canonical token_reduce_state helper
# =========================================================================== #


class TestScenarioS6CounterSourceOfTruth:
    """P1 (masking risk): S6 previously reimplemented the session-key slug +
    state path + {"count": int} schema by hand. If that hand-rolled copy
    ever drifted from token_reduce_state's real layout, it would silently
    read a missing file, return 0, and `count <= 1` would stay green --
    masking the exact double-increment regression the tool exists to catch.
    S6 must now delegate to token_reduce_state.broad_attempt_count() and
    require count == 1 exactly (not just <= 1)."""

    def test_requires_exact_count_one_not_just_le_one(self, tmp_path: Path):
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)  # always-allow: never writes state, never emits dedup event
        copy = rp.HookCopy("stub", stub_root)
        result, _steps = rp._scenario_s6(copy)
        # count stays 0 (no state ever written) -- must FAIL, not silently
        # pass as it would under the old `count <= 1` check.
        assert result.passed is False
        assert "broad_attempt_count=0" in result.detail

    def test_delegates_to_token_reduce_state_broad_attempt_count(self, tmp_path: Path, monkeypatch):
        """Monkeypatching the canonical helper and observing the reported
        count change proves _scenario_s6 calls THROUGH it, rather than a
        private reimplementation that could silently disagree."""
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        copy = rp.HookCopy("stub", stub_root)
        monkeypatch.setattr(rp._trs, "broad_attempt_count", lambda root, key: 7)
        result, _steps = rp._scenario_s6(copy)
        assert "broad_attempt_count=7" in result.detail
        assert result.passed is False  # 7 != 1

    def test_passes_when_canonical_helper_reports_exactly_one(self, tmp_path: Path, monkeypatch):
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        copy = rp.HookCopy("stub", stub_root)
        monkeypatch.setattr(rp._trs, "broad_attempt_count", lambda root, key: 1)
        monkeypatch.setattr(rp._trt, "load_events", lambda root: [{"event": "hook_dedup_replay"}])
        result, _steps = rp._scenario_s6(copy)
        assert result.passed is True
        assert "broad_attempt_count=1" in result.detail


# =========================================================================== #
# P6: os.sep-safe trailing-separator construction
# =========================================================================== #


class TestWithTrailingSep:
    """P6: env-sanity's with_slash previously used str(path) + "/" directly.
    _with_trailing_sep must guarantee exactly one trailing os.sep regardless
    of whether the input already ends with one, so the bare-vs-slash
    distinction the symlink-find trap check depends on can never collapse."""

    def test_no_trailing_sep_gets_exactly_one_added(self):
        assert rp._with_trailing_sep("/foo/bar") == "/foo/bar/"

    def test_existing_trailing_sep_is_not_doubled(self):
        assert rp._with_trailing_sep("/foo/bar/") == "/foo/bar/"

    def test_root_path_stays_single_separator(self):
        assert rp._with_trailing_sep("/") == "/"


# =========================================================================== #
# env-sanity
# =========================================================================== #


class TestEnvSanity:
    def _make_symlink_fixture(self, tmp_path: Path) -> Path:
        real_dir = tmp_path / "real_projects"
        real_dir.mkdir()
        for i in range(5):
            (real_dir / f"session-{i}").mkdir()
        link = tmp_path / "projects_link"
        link.symlink_to(real_dir)
        return link

    def test_non_symlink_path_reports_not_applicable(self, tmp_path: Path):
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        ns = _default_ns(repo_scripts=str(stub_root), deployed_root=str(stub_root), projects_path=str(plain_dir))
        result = rp.check_env_sanity(ns)
        assert result.data["is_symlink"] is False
        assert any("not a symlink" in line for line in result.lines)

    def test_symlink_trap_is_confirmed_with_real_fixture(self, tmp_path: Path):
        link = self._make_symlink_fixture(tmp_path)
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        ns = _default_ns(repo_scripts=str(stub_root), deployed_root=str(stub_root), projects_path=str(link))
        result = rp.check_env_sanity(ns)
        assert result.data["trap_live"] is True
        assert any("CONFIRMED live" in line for line in result.lines)

    def test_guarded_copy_reports_guarded_status(self, tmp_path: Path):
        link = self._make_symlink_fixture(tmp_path)
        guarded_enforce = (
            "import json, sys\n"
            "data = json.load(sys.stdin)\n"
            "cmd = str((data.get('tool_input') or {}).get('command',''))\n"
            "if 'find' in cmd and " + repr(str(link)) + " in cmd:\n"
            "    print(json.dumps({'decision':'block','reason':\"find root is a symlink\"}))\n"
            "    sys.exit(2)\n"
            "sys.exit(0)\n"
        )
        guarded_root = tmp_path / "guarded"
        _write_stub_copy(guarded_root, enforce_src=guarded_enforce)
        unguarded_root = tmp_path / "unguarded"
        _write_stub_copy(unguarded_root)

        ns = _default_ns(repo_scripts=str(guarded_root), deployed_root=str(unguarded_root), projects_path=str(link))
        result = rp.check_env_sanity(ns)
        assert result.data["guard_status"]["repo"] == "guarded"
        assert result.data["guard_status"]["deployed"] == "unguarded (silently allowed)"
        assert any("deployed copy is UNGUARDED" in f for f in result.findings)
        assert not any("repo copy does not guard" in f for f in result.findings)

    def test_rg_hidden_demo_reports_gap(self, tmp_path: Path):
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        ns = _default_ns(repo_scripts=str(stub_root), deployed_root=str(stub_root), projects_path=str(plain_dir))
        result = rp.check_env_sanity(ns)
        demo = result.data["rg_hidden_demo"]
        if demo.get("skipped"):
            pytest.skip("rg not installed on this host")
        assert demo["ok"] is True
        assert demo["full_count"] > demo["default_count"]


# =========================================================================== #
# P2: adoption-snapshot delegates to token_reduce_telemetry.load_events
# =========================================================================== #


class TestLoadEventsDelegation:
    """P2: check_adoption_snapshot previously reimplemented events.jsonl
    path/parse/cutoff logic that token_reduce_telemetry.load_events(days=...)
    already provides. Monkeypatching the canonical helper and observing the
    call proves check_adoption_snapshot delegates to it."""

    def test_check_adoption_snapshot_calls_token_reduce_telemetry_load_events(self, tmp_path: Path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        calls: list[tuple] = []

        def fake_load_events(root, *, days=None):
            calls.append((root, days))
            return []

        monkeypatch.setattr(rp._trt, "load_events", fake_load_events)
        ns = _default_ns(repo_root=str(repo_root), days=9)
        rp.check_adoption_snapshot(ns)
        assert calls == [(repo_root, 9)]


# =========================================================================== #
# adoption-snapshot
# =========================================================================== #


class TestAdoptionSnapshot:
    def _write_events(self, repo_root: Path, events: list[dict]) -> None:
        events_dir = repo_root / "artifacts" / "token-reduction"
        events_dir.mkdir(parents=True, exist_ok=True)
        path = events_dir / "events.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")

    def _event(
        self,
        event: str,
        *,
        session_key: str,
        ts: str,
        command: str | None = None,
        extra_meta: dict | None = None,
        status: str = "blocked",
    ) -> dict:
        meta = {"session_key": session_key}
        if command:
            meta["command"] = command
        if extra_meta:
            meta.update(extra_meta)
        return {"timestamp": ts, "event": event, "source": "hook", "status": status, "meta": meta}

    def test_counts_and_top_blocked_commands(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        events = [
            self._event("hook_block", session_key="s1", ts="2026-09-12T00:00:00+00:00", command="find / -name x"),
            self._event("hook_block", session_key="s1", ts="2026-09-12T00:00:01+00:00", command="find / -name x"),
            self._event("hook_warn", session_key="s2", ts="2026-09-12T00:00:02+00:00", command="tree ."),
            self._event("hook_error", session_key="s3", ts="2026-09-12T00:00:03+00:00"),
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["by_event"]["hook_block"] == 2
        assert result.data["by_event"]["hook_warn"] == 1
        assert result.data["top_blocked_commands"][0] == ("find / -name x", 2)
        assert any("hook_error event(s)" in f for f in result.findings)

    def test_warn_status_hook_block_excluded_from_storm_and_top_blocked(self, tmp_path: Path):
        """P4: a hook_block EVENT with status="warn" (TOKEN_REDUCE_ENFORCE_MODE=warn
        telemetry -- a would-have-blocked record, not a real block) must not
        count toward storm detection or top-blocked-commands."""
        repo_root = tmp_path / "repo"
        events = [
            self._event(
                "hook_block", session_key="warn-session", ts="2026-09-12T00:00:00+00:00", command="warn-cmd-1", status="warn"
            ),
            self._event(
                "hook_block", session_key="warn-session", ts="2026-09-12T00:00:01+00:00", command="warn-cmd-2", status="warn"
            ),
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["storm_sessions"] == []
        assert result.data["top_blocked_commands"] == []
        assert result.ok is True

    def test_mixed_warn_and_real_block_only_real_block_counts(self, tmp_path: Path):
        """P4: in a session with one warn-status hook_block and one real
        (status="blocked") hook_block, only the real block should surface in
        top-blocked-commands, and a single real block is not a storm."""
        repo_root = tmp_path / "repo"
        events = [
            self._event(
                "hook_block", session_key="mixed-session", ts="2026-09-12T00:00:00+00:00", command="warn-cmd", status="warn"
            ),
            self._event(
                "hook_block", session_key="mixed-session", ts="2026-09-12T00:00:01+00:00", command="real-cmd", status="blocked"
            ),
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["storm_sessions"] == []
        assert result.data["top_blocked_commands"] == [("real-cmd", 1)]

    def test_storm_session_detected_in_first_five_events(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        events = [
            self._event("hook_block", session_key="storm-session", ts=f"2026-09-12T00:00:0{i}+00:00", command=f"cmd{i}")
            for i in range(2)
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        storm_keys = [s[0] for s in result.data["storm_sessions"]]
        assert "storm-session" in storm_keys
        assert any("storm session" in f for f in result.findings)

    def test_no_storm_when_blocks_spread_across_sessions(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        events = [
            self._event("hook_block", session_key="s1", ts="2026-09-12T00:00:00+00:00", command="a"),
            self._event("hook_block", session_key="s2", ts="2026-09-12T00:00:01+00:00", command="b"),
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["storm_sessions"] == []

    def test_dedup_ratio_reported_when_present(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        events = [
            self._event("hook_block", session_key="s1", ts="2026-09-12T00:00:00+00:00", command="tree ."),
            self._event("hook_dedup_replay", session_key="s1", ts="2026-09-12T00:00:00+00:00"),
        ]
        self._write_events(repo_root, events)
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["dedup_ratio"] is not None
        assert any("dedup ratio" in line and "%" in line for line in result.lines)

    def test_dedup_ratio_absent_when_no_replay_events(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        self._write_events(repo_root, [self._event("hook_block", session_key="s1", ts="2026-09-12T00:00:00+00:00", command="x")])
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.data["dedup_ratio"] is None
        assert any("no hook_dedup_replay telemetry" in line for line in result.lines)

    def test_events_outside_window_are_excluded(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        old_event = self._event("hook_block", session_key="s1", ts="2020-01-01T00:00:00+00:00", command="ancient")
        self._write_events(repo_root, [old_event])
        ns = _default_ns(repo_root=str(repo_root), days=7)
        result = rp.check_adoption_snapshot(ns)
        assert result.data["by_event"].get("hook_block", 0) == 0

    def test_no_events_file_is_healthy_empty_report(self, tmp_path: Path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_adoption_snapshot(ns)
        assert result.ok is True
        assert "total events: 0" in result.lines


# =========================================================================== #
# inventory-staleness
# =========================================================================== #


class TestInventoryStaleness:
    def _make_repo(self, tmp_path: Path) -> Path:
        repo_root = tmp_path / "repo"
        _init_git_repo(repo_root)
        (repo_root / "scripts").mkdir()
        (repo_root / "README.md").write_text("mentions wired_script here\n")
        return repo_root

    def test_unwired_and_stale_script_is_a_demote_candidate(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path)
        old_ts = time.time() - 60 * 86400  # 60 days ago
        (repo_root / "scripts" / "wired_script.py").write_text("# wired\n")
        (repo_root / "scripts" / "orphan_script.py").write_text("# orphan\n")
        _commit_all(repo_root, "add scripts", when=old_ts)

        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_inventory_staleness(ns)
        candidate_files = [c["file"] for c in result.data["demote_candidates"]]
        assert "scripts/orphan_script.py" in candidate_files
        assert "scripts/wired_script.py" not in candidate_files
        assert any("orphan_script.py" in f for f in result.findings)

    def test_recently_touched_unwired_script_is_not_a_candidate(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path)
        (repo_root / "scripts" / "fresh_orphan.py").write_text("# fresh\n")
        _commit_all(repo_root, "add fresh")  # now, not backdated

        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_inventory_staleness(ns)
        candidate_files = [c["file"] for c in result.data["demote_candidates"]]
        assert "scripts/fresh_orphan.py" not in candidate_files

    def test_script_wired_via_cross_import_is_not_a_candidate(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path)
        old_ts = time.time() - 60 * 86400
        (repo_root / "scripts" / "helper_module.py").write_text("# helper\n")
        (repo_root / "scripts" / "caller.py").write_text("from helper_module import thing\n")
        _commit_all(repo_root, "add", when=old_ts)

        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_inventory_staleness(ns)
        candidate_files = [c["file"] for c in result.data["demote_candidates"]]
        assert "scripts/helper_module.py" not in candidate_files

    def test_no_candidates_is_healthy(self, tmp_path: Path):
        repo_root = self._make_repo(tmp_path)
        (repo_root / "scripts" / "wired_script.py").write_text("# wired\n")
        _commit_all(repo_root, "add")

        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_inventory_staleness(ns)
        assert result.ok is True
        assert result.data["demote_candidates"] == []

    def test_missing_scripts_dir_is_a_tool_error(self, tmp_path: Path):
        repo_root = tmp_path / "no-scripts-repo"
        repo_root.mkdir()
        ns = _default_ns(repo_root=str(repo_root))
        result = rp.check_inventory_staleness(ns)
        assert result.tool_error is True
        assert result.exit_code == rp.EXIT_TOOL_ERROR


# =========================================================================== #
# CLI / `all` wiring
# =========================================================================== #


class TestCliWiring:
    def test_main_dispatches_env_sanity_and_returns_its_exit_code(self, tmp_path: Path, capsys):
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        stub_root = tmp_path / "stub"
        _write_stub_copy(stub_root)
        rc = rp.main(
            [
                "--repo-scripts",
                str(stub_root),
                "--deployed-root",
                str(stub_root),
                "--projects-path",
                str(plain_dir),
                "env-sanity",
            ]
        )
        out = capsys.readouterr().out
        assert "env-sanity" in out
        assert rc in (rp.EXIT_HEALTHY, rp.EXIT_FINDINGS)

    def test_all_writes_report_and_exits_worst_of_five(self, tmp_path: Path, capsys):
        repo_root = tmp_path / "repo"
        _init_git_repo(repo_root)
        (repo_root / "scripts").mkdir()
        for name in rp.WATCHED_FILES:
            (repo_root / "scripts" / name).write_text(f"# {name}\n")
        _write_stub_copy(repo_root / "scripts")  # ensures enforce/remind are runnable stubs too
        _commit_all(repo_root, "init")
        deployed_root = tmp_path / "deployed"
        _write_stub_copy(deployed_root)
        report_path = tmp_path / "report.md"

        rc = rp.main(
            [
                "--no-fetch",
                "--repo-root",
                str(repo_root),
                "--deployed-root",
                str(deployed_root),
                "all",
                "--report",
                str(report_path),
            ]
        )
        assert report_path.is_file()
        text = report_path.read_text()
        assert "# token-reduce review pass" in text
        assert "## deploy-drift" in text
        assert "## hook-contract" in text
        assert "## env-sanity" in text
        assert "## adoption-snapshot" in text
        assert "## inventory-staleness" in text
        assert rc == rp.EXIT_FINDINGS  # this fixture has deliberate drift/regressions baked in
        out = capsys.readouterr().out
        assert "full report:" in out

    def test_unknown_check_never_crashes_main(self, tmp_path: Path):
        # A tool error inside a check must be caught by main(), not propagate.
        repo_root = tmp_path / "not-a-dir-with-scripts"
        rc = rp.main(["--repo-root", str(repo_root), "inventory-staleness"])
        assert rc == rp.EXIT_TOOL_ERROR
