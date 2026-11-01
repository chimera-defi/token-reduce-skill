"""Advisory output and telemetry must describe the actual, nonblocking outcome."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from command_rewrites import is_broad_find, is_catastrophic
from token_reduce_telemetry import summarize_events


def invoke(tmp_path, command, *, tool_id=None, mode="warn"):
    payload = {"session_id": "advisory", "tool_name": "Bash",
               "tool_input": {"command": command}}
    if tool_id:
        payload["tool_use_id"] = tool_id
    env = dict(os.environ, TOKEN_REDUCE_ENFORCE_MODE=mode,
               TOKEN_REDUCE_REPO_ROOT=str(tmp_path))
    return subprocess.run([sys.executable, str(SCRIPTS / "enforce-token-reduce-first.py")],
                          input=json.dumps(payload), text=True, capture_output=True,
                          env=env, cwd=tmp_path, timeout=10)


def events(tmp_path):
    path = tmp_path / "artifacts/token-reduction/events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_warning_events_never_count_as_blocks(tmp_path):
    for command in ("find / -name x", "tree .", "tree ."):
        result = invoke(tmp_path, command)
        assert result.returncode == 0 and result.stdout == ""
    recorded = events(tmp_path)
    assert len(recorded) == 3
    assert all(e["event"] == "hook_warn" and e["status"] == "warn" for e in recorded)
    assert not (tmp_path / ".claude/token-reduce-state/last_block.json").exists()


def test_advisory_mode_does_not_replay_cached_block(tmp_path):
    command = "find / -name x"
    assert invoke(tmp_path, command, tool_id="cached", mode="block").returncode == 2
    result = invoke(tmp_path, command, tool_id="cached")
    assert result.returncode == 0 and result.stdout == ""
    assert events(tmp_path)[-1]["event"] == "hook_warn"


def test_historical_warning_counts_are_normalized_without_mutation():
    old = {"event": "hook_block", "status": "warn", "meta": {"mode": "warn"}}
    actual = {"event": "hook_block", "status": "blocked"}
    summary = summarize_events([old, actual])
    assert summary["by_event"] == {"hook_warn": 1, "hook_block": 1}
    assert old["event"] == "hook_block"


def test_symlink_hint_is_advisory_and_deduplicated(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    command = f"find {link} -maxdepth 1"
    first = invoke(tmp_path, command, tool_id="symlink-1")
    second = invoke(tmp_path, command, tool_id="symlink-1")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    output = json.loads(first.stdout)
    assert set(output) == {"hookSpecificOutput"}
    specific = output["hookSpecificOutput"]
    assert set(specific) == {"hookEventName", "additionalContext"}
    assert specific["hookEventName"] == "PreToolUse"
    assert "symlink" in specific["additionalContext"]
    assert "-H/-L" in specific["additionalContext"]
    assert len(events(tmp_path)) == 1
    for root in (f"-H {link}", f"-L {link}", f"{link}/"):
        assert invoke(tmp_path, f"find {root} -maxdepth 1").stdout == ""


@pytest.mark.parametrize("depth", [0, 1, 2, 6])
def test_bounded_specific_find_is_not_catastrophic(depth):
    assert not is_catastrophic(f"find /tmp -name x -maxdepth {depth}")
    assert is_catastrophic(f"find / -maxdepth {depth}")
    # A depth limit of six can still emit a large listing; retain broad advice.
    assert is_broad_find("find /tmp -maxdepth 6")


def test_disk_summary_never_increments_broad_counter(tmp_path):
    for _ in range(3):
        assert invoke(tmp_path, "cd ~; du -sh paths").returncode == 0
    assert events(tmp_path) == []
    assert not list((tmp_path / ".claude/token-reduce-state").glob("broad_attempt*"))


def setup_command(script):
    """Evaluate only the generator assignment, never execute setup or edit settings."""
    text = (SCRIPTS / "setup.sh").read_text()
    body = text.split("<<'PYEOF'\n", 1)[1].split("\nPYEOF", 1)[0]
    tree = ast.parse(body)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "enforce_cmd" for t in n.targets))
    namespace = {"enforce_script": str(script), "uv_abs": "/missing/uv",
                 "python_abs": sys.executable}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), "setup-command", "exec"), namespace)
    return namespace["enforce_cmd"]


def test_generated_launcher_forwards_only_advisory_even_with_block_env(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    command = setup_command(SCRIPTS / "enforce-token-reduce-first.py")
    assert "uv run" not in command and "--no-project" not in command
    env = dict(os.environ, TOKEN_REDUCE_REPO_ROOT=str(tmp_path), TOKEN_REDUCE_ENFORCE_MODE="block")
    result = subprocess.run(["sh", "-c", command], env=env, text=True, capture_output=True,
                            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"find {link}"}}))
    assert result.returncode == 0
    assert "additionalContext" in json.loads(result.stdout)["hookSpecificOutput"]
    for content in (None, "raise RuntimeError('broken fixture')\n"):
        missing = tmp_path / "broken.py"
        if content:
            missing.write_text(content)
        result = subprocess.run(["sh", "-c", setup_command(missing)], env=env,
                                input="{}", text=True, capture_output=True)
        assert result.returncode == 0 and result.stdout == result.stderr == ""


def test_generated_launcher_timeout_fails_open(tmp_path):
    hanging = tmp_path / "hanging.py"
    hanging.write_text("import time; time.sleep(30)\n")
    result = subprocess.run(["sh", "-c", setup_command(hanging)], input="{}",
                            text=True, capture_output=True, timeout=8)
    assert result.returncode == 0 and result.stdout == result.stderr == ""


def test_read_fast_path_avoids_repository_subprocess(monkeypatch):
    spec = importlib.util.spec_from_file_location("advisory_hook", SCRIPTS / "enforce-token-reduce-first.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    monkeypatch.setenv("TOKEN_REDUCE_ENFORCE_MODE", "warn")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps({"tool_name": "Read"})))
    calls = []
    monkeypatch.setattr(hook, "repo_root", lambda: calls.append(True))
    assert hook.main() == 0
    assert calls == []
