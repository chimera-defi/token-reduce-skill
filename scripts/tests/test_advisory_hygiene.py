"""Hygiene advice is silent telemetry and always fails open."""
import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def hygiene():
    import advisory_hygiene
    return advisory_hygiene


def large_file(tmp_path, lines=301, trailing_newline=True):
    path = tmp_path / "large.txt"
    path.write_bytes((b"x" * 50 + b"\n") * (lines - 1) + b"x" * 50 +
                     (b"\n" if trailing_newline else b""))
    return path


@pytest.mark.parametrize("lines,expected", [(300, None), (301, "read_unbounded")])
@pytest.mark.parametrize("trailing_newline", [True, False])
def test_read_line_boundary(tmp_path, lines, expected, trailing_newline):
    path = large_file(tmp_path, lines, trailing_newline)
    assert hygiene().read_advice({"file_path": str(path)}) == expected


def test_small_file_is_not_opened(monkeypatch, tmp_path):
    path = tmp_path / "small.txt"
    path.write_bytes(b"x\n" * 301)
    module = hygiene()
    monkeypatch.setattr(builtins, "open", lambda *a, **kw: pytest.fail("opened small file"))
    assert module.read_advice({"file_path": str(path)}) is None


def test_huge_no_newline_file(tmp_path):
    path = tmp_path / "huge.txt"
    path.write_bytes(b"x" * 1_000_000)
    assert hygiene().read_advice({"file_path": str(path)}) is None


def test_read_stops_after_line_threshold(monkeypatch, tmp_path):
    path = large_file(tmp_path)
    module = hygiene()

    class Chunks(io.BytesIO):
        def read(self, size=-1):
            assert size > 0
            assert self.tell() == 0, "continued reading after threshold"
            return super().read(size)

    monkeypatch.setattr(builtins, "open", lambda *a, **kw: Chunks(b"x\n" * 301))
    assert module.read_advice({"file_path": str(path)}) == "read_unbounded"


def test_read_absent_directory_and_unreadable(monkeypatch, tmp_path):
    module = hygiene()
    assert module.read_advice({"file_path": str(tmp_path / "absent")}) is None
    assert module.read_advice({"file_path": str(tmp_path)}) is None
    path = large_file(tmp_path)

    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(builtins, "open", denied)
    assert module.read_advice({"file_path": str(path)}) is None


@pytest.mark.parametrize("head_limit,expected", [
    (None, "grep_no_head_limit"), (0, "grep_no_head_limit"),
    (-1, "grep_no_head_limit"), (10, None),
])
def test_grep_content(head_limit, expected):
    tool_input = {"output_mode": "content"}
    if head_limit is not None:
        tool_input["head_limit"] = head_limit
    assert hygiene().grep_advice(tool_input) == expected


@pytest.mark.parametrize("mode", [None, "files_with_matches", "count"])
def test_grep_other_modes(mode):
    assert hygiene().grep_advice({"output_mode": mode}) is None


PATHS = [f"src/file-{i}.py" for i in range(51)]
RESPONSES = ["\n" + "\n".join(PATHS) + "\n\n", PATHS,
             {"filenames": PATHS}, {"files": PATHS}, {"numFiles": 51},
             {"content": "\n".join(PATHS)}]


@pytest.mark.parametrize("response", RESPONSES)
@pytest.mark.parametrize("key", ["tool_response", "tool_result"])
def test_glob_result_forms(key, response):
    assert hygiene().glob_result_advice({key: response}) == ("glob_explosion", 51)


def test_glob_ignores_empty_entries_and_boundary():
    module = hygiene()
    assert module.glob_result_advice({"tool_response": PATHS[:50] + ["", " ", None]}) is None
    assert module.glob_result_advice({"tool_response": {"files": ["a", "", "b", "c"]}}) is None
    assert module.glob_result_advice({"tool_response": None, "tool_result": PATHS}) == ("glob_explosion", 51)


@pytest.mark.parametrize("bad", [None, [], "bad", 12, {"file_path": None}])
def test_helpers_fail_open(bad):
    module = hygiene()
    assert module.read_advice(bad) is None
    assert module.grep_advice(bad) is None
    assert module.glob_result_advice(bad) is None


def run_hook(tmp_path, script, data, *, raw=False, scripts=SCRIPTS):
    sink = tmp_path / "central.jsonl"
    result = subprocess.run(
        [sys.executable, str(scripts / script)],
        input=data if raw else json.dumps(data), text=True, capture_output=True,
        cwd=tmp_path, timeout=15,
        env=dict(os.environ, TOKEN_REDUCE_CENTRAL_EVENTS=str(sink),
                 TOKEN_REDUCE_ENFORCE_MODE="warn", TOKEN_REDUCE_REPO_ROOT=str(tmp_path)),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    rows = [json.loads(line) for line in sink.read_text().splitlines()] if sink.exists() else []
    return [row for row in rows if row["event"] in ("hook_call", "hook_result")]


@pytest.mark.parametrize("limit", [None, 50])
def test_read_hook_telemetry_and_limit(tmp_path, limit):
    tool_input = {"file_path": str(large_file(tmp_path))}
    if limit is not None:
        tool_input["limit"] = limit
    [row] = run_hook(tmp_path, "enforce-token-reduce-first.py", {
        "tool_name": "Read", "tool_input": tool_input, "hook_event_name": "PreToolUse"})
    assert row["matched"] is (limit is None)
    assert row["rule"] == ("read_unbounded" if limit is None else None)


def test_read_advice_never_spawns(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("hygiene_hook", SCRIPTS / "enforce-token-reduce-first.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    data = {"tool_name": "Read", "tool_input": {"file_path": str(large_file(tmp_path))}}
    monkeypatch.setenv("TOKEN_REDUCE_ENFORCE_MODE", "warn")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("Read spawned a process"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    assert hook.main() == 0
    assert hook._ADVICE == {"matched": True, "rule": "read_unbounded"}


@pytest.mark.parametrize("tool_input,rule", [
    ({"output_mode": "content"}, "grep_no_head_limit"),
    ({"output_mode": "content", "head_limit": 20}, None),
    ({"output_mode": "files_with_matches"}, None),
])
def test_grep_hook_telemetry(tmp_path, tool_input, rule):
    path = large_file(tmp_path)
    [row] = run_hook(tmp_path, "enforce-token-reduce-first.py", {
        "tool_name": "Grep", "tool_input": dict(tool_input, path=str(path), pattern="x"),
        "hook_event_name": "PreToolUse"})
    assert (row["matched"], row["rule"]) == (rule is not None, rule)


@pytest.mark.parametrize("response", RESPONSES)
def test_glob_hook_telemetry(tmp_path, response):
    [row] = run_hook(tmp_path, "warn-glob-explosion.py", {
        "tool_name": "Glob", "tool_response": response, "hook_event_name": "PostToolUse"})
    assert row["matched"] is True
    assert row["rule"] == "glob_explosion"
    assert row["count"] == 51
    assert row["hook_event"] == "PostToolUse"
    assert row["event"] == "hook_result"


def test_glob_small_result(tmp_path):
    assert run_hook(tmp_path, "warn-glob-explosion.py", {
        "tool_name": "Glob", "tool_response": PATHS[:3], "hook_event_name": "PostToolUse"}) == []


@pytest.mark.parametrize("stdin", ["garbage", "", "[]", "null", "42"])
def test_glob_garbage_is_silent(tmp_path, stdin):
    assert run_hook(tmp_path, "warn-glob-explosion.py", stdin, raw=True) == []


@pytest.mark.parametrize("script,tool", [("enforce-token-reduce-first.py", "Read"),
                                         ("warn-glob-explosion.py", "Glob")])
def test_optional_hygiene_module_missing(tmp_path, script, tool):
    scripts = tmp_path / "scripts"
    shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns("advisory_hygiene.py", "__pycache__", "tests"))
    rows = run_hook(tmp_path, script, {"tool_name": tool}, scripts=scripts)
    assert all(row["matched"] is False for row in rows)


def test_report_keeps_glob_rule_without_double_counting(tmp_path):
    import importlib.util
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    pre = {"ts": now, "event": "hook_call", "source": "hook", "tool": "Glob",
           "session": "s", "call": "c", "advised": False, "rule": None}
    post = dict(pre, event="hook_result", matched=True, rule="glob_explosion")
    sink = tmp_path / "x.jsonl"
    sink.write_text("\n".join(json.dumps(r) for r in (pre, post)) + "\n")
    spec = importlib.util.spec_from_file_location("ur", SCRIPTS / "token-reduce-usage-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.summarize(sink, 14)
    assert report["by_tool"] == {"Glob": 1}
    assert report["advice_by_rule"] == {"glob_explosion": 1}
