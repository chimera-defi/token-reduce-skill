"""Operator decision 2026-10-28: token-reduce hooks never block (exit 0 always)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "enforce-token-reduce-first.py"

CASES = [
    {"tool_name": "Bash", "tool_input": {"command": "find / -name x"}},  # catastrophic
    {"tool_name": "Bash", "tool_input": {"command": "find /home/agents/.claude/projects -name '*.jsonl'"}},
    {"tool_name": "Bash", "tool_input": {"command": "grep -rn foo ."}},
    {"tool_name": "Glob", "tool_input": {"pattern": "**/*"}},
    {"tool_name": "Grep", "tool_input": {"pattern": "foo", "path": "."}},
]


def run(payload, tmp_path, mode=None):
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(tmp_path)
    env["TOKEN_REDUCE_CONFIG_PATH"] = str(tmp_path / "none.json")
    env["PYTHONPATH"] = str(HOOK.parent)
    env.pop("TOKEN_REDUCE_ENFORCE_MODE", None)
    if mode:
        env["TOKEN_REDUCE_ENFORCE_MODE"] = mode
    payload = dict(payload, session_id="s-nb")
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=30)


def test_default_never_exits_2_or_emits_block(tmp_path):
    for _ in range(4):  # repeat to pass the repeat_broad threshold too
        for case in CASES:
            r = run(case, tmp_path)
            assert r.returncode == 0, (case, r.stdout, r.stderr)
            assert '"decision": "block"' not in r.stdout


def test_catastrophic_blocks_only_with_explicit_test_optin(tmp_path):
    assert run(CASES[0], tmp_path, mode="block").returncode == 2
