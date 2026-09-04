"""Regression coverage for measure_token_reduction.py's session cache.

Before this cache existed, ``measure(scope, repo_root)`` re-read and
re-parsed every Claude/Codex session transcript on every single invocation,
regardless of whether the underlying files had changed. At --scope global
this made runs against the real workspace corpus (~1000+ Codex session
files, several GB) take 8-10+ minutes and, per prior observation, not
complete even under a 590s timeout.

These tests build small synthetic session corpora under a fake $HOME so
they run in milliseconds, and assert -- via call-count spies on the
expensive parse functions, not just wall-clock timing -- that:

1. An unchanged corpus is not re-parsed on a second `measure()` call.
2. Only a file that actually changed gets re-parsed.
3. Cached and uncached runs produce identical output.
4. Progress is persisted incrementally, so a run that gets killed partway
   through (the observed real-world failure mode) still leaves the files it
   finished processing cached for the next attempt instead of losing all
   progress.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import measure_token_reduction as mtr  # noqa: E402
from session_metrics_cache import cache_path as smc_cache_path  # noqa: E402


CODEX_LINE = json.dumps(
    {
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "arguments": json.dumps({"cmd": "rg -g '*.py' foo src"}),
        }
    }
)


def _write_codex_session(path: Path, lines: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((CODEX_LINE + "\n") * lines)


def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def _spy_on(monkeypatch: pytest.MonkeyPatch, name: str):
    real_fn = getattr(mtr, name)
    counter = {"n": 0}

    def wrapper(path):
        counter["n"] += 1
        return real_fn(path)

    monkeypatch.setattr(mtr, name, wrapper)
    return counter


def test_measure_second_global_call_does_not_reparse_unchanged_codex_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = _fake_home(tmp_path, monkeypatch)
    sessions_dir = fake_home / ".codex" / "sessions" / "2026" / "01" / "01"
    for i in range(3):
        _write_codex_session(sessions_dir / f"rollout-{i}.jsonl")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    counter = _spy_on(monkeypatch, "parse_codex_session")

    result1 = mtr.measure("global", str(repo_root))
    assert counter["n"] == 3
    assert result1["session_count"] == 3

    counter["n"] = 0
    result2 = mtr.measure("global", str(repo_root))
    assert counter["n"] == 0, "unchanged files must be served from cache, not re-parsed"
    assert result2["session_count"] == 3


def test_measure_reparses_only_the_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = _fake_home(tmp_path, monkeypatch)
    sessions_dir = fake_home / ".codex" / "sessions" / "2026" / "01" / "01"
    paths = []
    for i in range(3):
        p = sessions_dir / f"rollout-{i}.jsonl"
        _write_codex_session(p)
        paths.append(p)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    counter = _spy_on(monkeypatch, "parse_codex_session")
    mtr.measure("global", str(repo_root))
    counter["n"] = 0

    _write_codex_session(paths[1], lines=3)  # mutate exactly one file

    mtr.measure("global", str(repo_root))
    assert counter["n"] == 1


def test_measure_repo_scope_caches_claude_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = _fake_home(tmp_path, monkeypatch)
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    slug = "-" + repo_root.resolve().as_posix().lstrip("/").replace("/", "-")
    project_dir = fake_home / ".claude" / "projects" / slug
    project_dir.mkdir(parents=True)
    for i in range(3):
        (project_dir / f"session-{i}.jsonl").write_text(
            json.dumps({"message": {"content": "hello"}}) + "\n"
        )

    counter = _spy_on(monkeypatch, "parse_claude_session")

    result1 = mtr.measure("repo", str(repo_root))
    assert counter["n"] == 3
    assert result1["session_count"] == 3

    counter["n"] = 0
    result2 = mtr.measure("repo", str(repo_root))
    assert counter["n"] == 0
    assert result2["session_count"] == 3


def test_measure_cached_and_uncached_output_are_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = _fake_home(tmp_path, monkeypatch)
    sessions_dir = fake_home / ".codex" / "sessions" / "2026" / "01" / "01"
    for i in range(2):
        _write_codex_session(sessions_dir / f"rollout-{i}.jsonl")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    warm1 = mtr.measure("global", str(repo_root))
    warm2 = mtr.measure("global", str(repo_root))  # served entirely from cache
    cold = mtr.measure("global", str(repo_root), use_cache=False)

    def _strip(d: dict) -> dict:
        d = dict(d)
        d.pop("measured_at", None)
        return d

    assert _strip(warm1) == _strip(warm2) == _strip(cold)


def test_measure_persists_progress_incrementally_so_a_killed_run_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reproduces the real failure mode: a global run gets killed partway
    through (observed: 590s timeout, run never completes). If the cache is
    only written once at the very end, a killed run persists nothing and the
    next attempt starts cold again, forever. Progress must be saved as the
    run goes so a resumed run only has to redo the unfinished tail.
    """
    fake_home = _fake_home(tmp_path, monkeypatch)
    sessions_dir = fake_home / ".codex" / "sessions" / "2026" / "01" / "01"
    for i in range(5):
        _write_codex_session(sessions_dir / f"rollout-{i}.jsonl")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    class Boom(Exception):
        pass

    real_parse = mtr.parse_codex_session
    call_count = {"n": 0}

    def flaky_parse(path):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise Boom("simulated kill mid-run")
        return real_parse(path)

    monkeypatch.setattr(mtr, "parse_codex_session", flaky_parse)

    with pytest.raises(Boom):
        mtr.measure("global", str(repo_root), cache_flush_every=1)

    cache_file = smc_cache_path(repo_root)
    assert cache_file.exists(), "partial progress must be flushed to disk before the crash"
    on_disk = json.loads(cache_file.read_text())
    assert len(on_disk["entries"]) == 2, "only the 2 files that finished before the crash are cached"

    # Resume: the crashed 3rd file plus the 2 never-attempted files must be
    # reparsed; the 2 that finished before the crash must not be.
    monkeypatch.setattr(mtr, "parse_codex_session", real_parse)
    counter = _spy_on(monkeypatch, "parse_codex_session")

    result = mtr.measure("global", str(repo_root))
    assert counter["n"] == 3
    assert result["session_count"] == 5
