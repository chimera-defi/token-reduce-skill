"""Central telemetry stays private, advisory, and independent of repo state."""
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def central():
    import token_reduce_central
    return token_reduce_central


def rows():
    path = Path(os.environ["TOKEN_REDUCE_CENTRAL_EVENTS"])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def run_hook(tmp_path, payload=None, *, stdin=None, **env_overrides):
    env = dict(os.environ, TOKEN_REDUCE_REPO_ROOT=str(tmp_path),
               TOKEN_REDUCE_ENFORCE_MODE="warn", **env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "enforce-token-reduce-first.py")],
        input=json.dumps(payload) if stdin is None else stdin,
        text=True, capture_output=True, cwd=tmp_path, env=env, timeout=15,
    )


def test_central_schema_and_single_append(monkeypatch, tmp_path):
    c = central()
    monkeypatch.setenv("CLAUDE_SESSION_MODEL", "claude-test")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    calls = []
    flags = []
    open_fd = os.open
    write = os.write

    def track_open(path, options, mode):
        flags.append((options, mode))
        return open_fd(path, options, mode)

    def track(fd, data):
        calls.append(data)
        return write(fd, data)

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("central logging spawned a process"))
    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "write", track)
    c.log_call({"tool_name": "Read", "session_id": "secret-session",
                "cwd": str(tmp_path / "project"), "hook_event_name": "PreToolUse"})
    [row] = rows()
    assert row == dict(ts=row["ts"], event="hook_call", tool="Read", model="claude-test",
                       lane="main", session=c.session_hash({"session_id": "secret-session"}),
                       advised=False, call=None, rule=None, project="project", hook_event="PreToolUse",
                       client="cli", source="hook")
    assert datetime.fromisoformat(row["ts"]).utcoffset().total_seconds() == 0
    assert len(calls) == 1
    assert flags == [(os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)]
    assert calls[0] == (json.dumps(row, sort_keys=True) + "\n").encode()
    assert Path(os.environ["TOKEN_REDUCE_CENTRAL_EVENTS"]).stat().st_mode & 0o777 == 0o600


def test_hash_is_private_and_missing_is_none():
    hashed = central().session_hash({"session_id": "raw-session"})
    assert re.fullmatch("[0-9a-f]{12}", hashed)
    assert hashed != "raw-session"
    assert central().session_hash({}) == "none"
    assert central().session_hash({"transcript_path": "raw-session"}) == hashed


def test_model_precedence_and_tail(monkeypatch, tmp_path):
    c = central()
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"padding":"' + "x" * 100_000 + '"}\n' +
                          '{"model":"earlier"}\n{"message":{"model":"tail-model"}}\ninvalid\n')
    data = {"session_id": str(tmp_path), "transcript_path": str(transcript)}
    monkeypatch.setenv("CLAUDE_SESSION_MODEL", "session-model")
    monkeypatch.setenv("ANTHROPIC_MODEL", "anthropic-model")
    assert c.detect_model(data) == "session-model"
    monkeypatch.delenv("CLAUDE_SESSION_MODEL")
    assert c.detect_model(data) == "anthropic-model"
    monkeypatch.delenv("ANTHROPIC_MODEL")
    assert c.detect_model(dict(data, model="payload-model")) == "payload-model"
    assert c.detect_model(data) == "tail-model"
    transcript.unlink()
    assert c.detect_model(data) == "tail-model"  # process-local session cache
    assert c.detect_model({"transcript_path": str(tmp_path / "absent")}) == "unknown"
    assert c.detect_model({"model": 12}) == "unknown"


def test_model_top_level_tail(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_SESSION_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    path = tmp_path / "top.jsonl"
    path.write_text('[]\n{"message":null,"model":"top-level"}\n')
    assert central().detect_model({"transcript_path": str(path)}) == "top-level"


def test_lane(monkeypatch):
    monkeypatch.delenv("TOKEN_REDUCE_LANE", raising=False)
    c = central()
    assert c.detect_lane({}) == "main"
    assert c.detect_lane({"agent_id": "id"}) == "subagent"
    assert c.detect_lane({"agent_type": "Explore"}) == "subagent"
    assert c.detect_lane({"agent_id": ""}) == "main"
    monkeypatch.setenv("TOKEN_REDUCE_LANE", "review")
    assert c.detect_lane({"agent_id": "id"}) == "review"


def test_record_event_mirrors_without_changing_repo_format(monkeypatch, tmp_path):
    from token_reduce_telemetry import record_event, events_path
    record_event(tmp_path, event="helper_call", source="helper", tool="paths", status="ok",
                 meta={"session_key": "raw-session", "policy": "helper", "context": "test"})
    [row] = rows()
    assert row["session"] == central().session_hash({"session_id": "raw-session"})
    assert row["project"] == tmp_path.name
    assert row["rule"] == "helper"
    assert row["context"] == "test"
    local = json.loads(events_path(tmp_path).read_text())
    assert "timestamp" in local and "ts" not in local and "session" not in local
    record_event(tmp_path, event="hook_call", source="hook", tool="Read")
    assert len(rows()) == 1
    monkeypatch.setattr(central(), "append_line", lambda _: (_ for _ in ()).throw(OSError()))
    record_event(tmp_path, event="helper_call", source="helper")
    assert len(events_path(tmp_path).read_text().splitlines()) == 3


def test_repo_failure_still_raises(tmp_path):
    from token_reduce_telemetry import record_event
    root = tmp_path / "file"
    root.write_text("not a directory")
    with pytest.raises(OSError):
        record_event(root, event="helper_call", source="helper")
    assert rows() == []


@pytest.mark.parametrize("tool,tool_input,advised,rule", [
    ("Bash", {"command": "find . -name x"}, True, "broad_bash"),
    ("Read", {"file_path": "known.py"}, False, None),
    ("Glob", {"pattern": "**/*"}, True, "broad_glob"),
    ("Grep", {"pattern": "foo", "path": "."}, True, "exploratory_grep"),
])
def test_hook_tools(tmp_path, tool, tool_input, advised, rule):
    result = run_hook(tmp_path, {"tool_name": tool, "tool_input": tool_input,
                                "cwd": str(tmp_path), "session_id": "s", "hook_event_name": "PreToolUse"})
    assert result.returncode == 0, result.stderr
    calls = [row for row in rows() if row["event"] == "hook_call"]
    assert len(calls) == 1
    assert (calls[0]["tool"], calls[0]["matched"], calls[0]["rule"]) == (tool, advised, rule)
    assert calls[0]["advised"] is False  # warn mode writes nothing for the model


def test_read_never_discovers_repo(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("central_hook", SCRIPTS / "enforce-token-reduce-first.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    monkeypatch.setenv("TOKEN_REDUCE_ENFORCE_MODE", "warn")
    monkeypatch.setattr(hook, "repo_root", lambda: pytest.fail("Read called repo_root"))
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"tool_name":"Read"}'))
    assert hook.main() == 0
    assert len(rows()) == 1


def test_dedup_replay_logs_once(tmp_path):
    payload = {"tool_name": "Glob", "tool_input": {"pattern": "**/*"},
               "session_id": "s", "tool_use_id": "same-call"}
    for _ in range(2):
        assert run_hook(tmp_path, payload).returncode == 0
    assert len([row for row in rows() if row["event"] == "hook_call"]) == 1


def test_bash_policy_rules_and_allowed_call(tmp_path):
    for command, rule in [("find . -name x", "broad_bash"),
                          ("find . -name x", "repeat_broad"),
                          ("find / -name x", "catastrophic"), ("git status", None)]:
        result = run_hook(tmp_path, {"tool_name": "Bash", "session_id": "s",
                                    "tool_input": {"command": command}})
        assert result.returncode == 0, result.stderr
        row = [row for row in rows() if row["event"] == "hook_call"][-1]
        assert row["rule"] == rule
        assert row["matched"] == (rule is not None)


@pytest.mark.parametrize("value", ["off", "0", ""])
def test_disabled(monkeypatch, tmp_path, value):
    monkeypatch.setenv("TOKEN_REDUCE_CENTRAL_EVENTS", value)
    assert central().central_path() is None
    assert run_hook(tmp_path, {"tool_name": "Glob", "tool_input": {"pattern": "**/*"}}).returncode == 0
    assert not (tmp_path / "central-events.jsonl").exists()


def test_default_path(monkeypatch, tmp_path):
    monkeypatch.delenv("TOKEN_REDUCE_CENTRAL_EVENTS")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert central().central_path() == tmp_path / ".local/share/token-reduce/events.jsonl"


def test_unwritable_sink_fails_open(monkeypatch, tmp_path):
    # /proc cannot create files even when the suite runs as root.
    monkeypatch.setenv("TOKEN_REDUCE_CENTRAL_EVENTS", "/proc/token-reduce-unwritable/events.jsonl")
    assert run_hook(tmp_path, {"tool_name": "Glob", "tool_input": {"pattern": "**/*"}}).returncode == 0
    central().append_line({"event": "test"})


def test_payload_keys_written_once(tmp_path):
    payload = {"tool_name": "Read", "hook_event_name": "PreToolUse", "session_id": "private"}
    assert run_hook(tmp_path, payload).returncode == 0
    path = tmp_path / "payload-keys-PreToolUse-Read.json"
    assert json.loads(path.read_text()) == sorted(payload)
    stat = path.stat()
    assert run_hook(tmp_path, dict(payload, extra_secret="hidden")).returncode == 0
    assert path.stat().st_mtime_ns == stat.st_mtime_ns
    assert "private" not in path.read_text() and "hidden" not in path.read_text()


@pytest.mark.parametrize("stdin", ["[1]", "null", "not json"])
def test_bad_stdin_fails_open(tmp_path, stdin):
    assert run_hook(tmp_path, stdin=stdin).returncode == 0
    assert not [row for row in rows() if row["event"] == "hook_call"]


def test_missing_central_module_preserves_legacy_hook(tmp_path):
    # Load the real hook with only the new import unavailable.
    code = '''
import builtins, runpy, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "token_reduce_central":
        raise ImportError("partial deployment")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.path.insert(0, sys.argv[1])
runpy.run_path(sys.argv[1] + "/enforce-token-reduce-first.py", run_name="__main__")
'''
    result = subprocess.run([sys.executable, "-c", code, str(SCRIPTS)],
                            input='{"tool_name":"Glob","tool_input":{"pattern":"**/*"}}',
                            text=True, capture_output=True,
                            env=dict(os.environ, TOKEN_REDUCE_REPO_ROOT=str(tmp_path)), timeout=15)
    assert result.returncode == 2, result.stderr  # legacy opt-in still works
    assert json.loads(result.stdout)["decision"] == "block"


def run_report(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "token-reduce-usage-report.py"), *args],
                          text=True, capture_output=True, timeout=15)


def test_report_filters_and_groups(tmp_path):
    now = datetime.now(timezone.utc)
    base = dict(ts=now.isoformat(), event="hook_call", source="hook", tool="Bash",
                model="model-a", lane="main", project="project-a", advised=True, rule="broad_bash")
    fixture = [base, dict(base, tool="Read", advised=False, rule=None),
               dict(base, source="test"), dict(base, context="benchmark"),
               dict(base, meta={"context": "synthetic"}),
               dict(base, ts=(now - timedelta(days=30)).isoformat()),
               dict(base, event="hook_warn")]
    path = tmp_path / "fixture.jsonl"
    path.write_text("\n".join(map(json.dumps, fixture)) + '\ninvalid\n[]\n')
    result = run_report("--events", str(path), "--days", "14", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["events_considered"] == 2
    assert report["events_skipped"] == 7
    assert report["by_tool"] == {"Bash": 1, "Read": 1}
    assert report["by_model"] == {"model-a": 2}
    assert report["by_lane"] == {"main": 2}
    assert report["by_project"] == {"project-a": 2}
    assert report["advice_by_rule"] == {"broad_bash": 1}
    assert report["advice_rate_by_tool"]["Bash"] == {"advised": 1, "total": 1, "rate": 1.0}
    assert report["model_tool_matrix"] == {"model-a": {"Bash": 1, "Read": 1}}
    text = run_report("--events", str(path)).stdout
    for label in ("Bash", "model-a", "broad_bash", "Events considered", "Events skipped"):
        assert label in text


@pytest.mark.parametrize("exists", [True, False])
def test_report_empty_or_missing(tmp_path, exists):
    path = tmp_path / "empty.jsonl"
    if exists:
        path.touch()
    result = run_report("--events", str(path))
    assert result.returncode == 0
    assert "No events" in result.stdout
    result = run_report("--events", str(path), "--json")
    assert json.loads(result.stdout)["events_considered"] == 0


def test_report_dedups_same_call_across_hook_layers(tmp_path):
    from datetime import datetime, timezone
    row = {"ts": datetime.now(timezone.utc).isoformat(), "event": "hook_call", "source": "hook",
           "tool": "Read", "session": "s1", "call": "c1", "model": "m", "lane": "main",
           "project": "p", "advised": False, "rule": None}
    sink = tmp_path / "dup.jsonl"
    sink.write_text("\n".join(json.dumps(r) for r in (row, row, dict(row, call="c2"))) + "\n")
    spec = importlib.util.spec_from_file_location("usage_report", SCRIPTS / "token-reduce-usage-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.summarize(sink, 14)["events_considered"] == 2


def test_report_counts_only_calls_and_helper_invocations(tmp_path):
    from datetime import datetime, timezone
    base = {"ts": datetime.now(timezone.utc).isoformat(), "source": "helper", "tool": "token-reduce-snippet"}
    sink = tmp_path / "aux.jsonl"
    sink.write_text("\n".join(json.dumps(dict(base, event=e)) for e in
                              ("helper_invocation", "brain_hint_error", "hook_warn")) + "\n")
    spec = importlib.util.spec_from_file_location("usage_report2", SCRIPTS / "token-reduce-usage-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.summarize(sink, 14)["events_considered"] == 1
