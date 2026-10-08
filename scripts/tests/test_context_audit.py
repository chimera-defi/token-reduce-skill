import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import context_audit as audit_module


def write_rows(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def test_provider_cache_input_is_counted_once_and_ids_deduped(tmp_path):
    path = tmp_path / "session.jsonl"
    row = {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 2, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10}}}
    write_rows(path, [row, row])
    report = audit_module.audit(path, budget=300)
    assert report["provider_input"]["latest"]["input_tokens"] == 112
    assert report["provider_input"]["responses"] == 1
    assert report["context_budget"]["measurement"] == "assumed_operator_supplied"
    assert report["categories"]["system_prompt"]["tokens"] is None


def test_snapshots_and_schemas_preserve_distinction_and_no_content_leaks(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_module, "counter", lambda: (lambda text: len(text), "measured_fixture_counter"))
    path = tmp_path / "session.jsonl"
    secret = "DO_NOT_EMIT_PRIVATE_CONTENT"
    tool = {"name": "mcp__big__search", "description": secret, "input_schema": {"type": "object"}, "defer_loading": True}
    write_rows(path, [
        {"attachment": {"type": "prompt_snapshot", "systemPrompt": [secret]}},
        {"attachment": {"type": "instructions", "files": [{"path": "CLAUDE.md", "content": secret}]}},
        {"attachment": {"type": "deferred_tools_record", "entries": [tool, tool]}},
        {"attachment": {"type": "deferred_tools_delta", "addedNames": [tool["name"]], "addedLines": ["short tool description"]}},
    ])
    report = audit_module.audit(path)
    assert report["mcp_servers"]["big"]["definitions"] == 1
    assert report["mcp_servers"]["big"]["deferred_definitions"] == 1
    assert report["categories"]["system_prompt"]["tokens"] == len(secret)
    assert report["categories"]["mcp_tool_schemas"]["tokens"] > report["categories"]["deferred_tool_list"]["tokens"]
    assert secret not in json.dumps(report)
    assert report["recommendations"][0]["operator_approval_required"]


def test_truncation_and_malformed_record_are_visible(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text('not json\n{"type":"user"}\n')
    report = audit_module.audit(path, max_bytes=12)
    assert report["malformed_records"] == 1
    assert report["scan_truncated"]


def test_on_load_hook_is_inert_when_auto_and_fail_open_when_invalid(tmp_path, monkeypatch):
    script = Path(audit_module.__file__)
    before = set(tmp_path.iterdir())
    for mode, payload in [("auto", "{}"), ("on", "invalid")]:
        env = {**os.environ, "TOKEN_REDUCE_LAYER_CONTEXT_AUDIT": mode}
        result = subprocess.run([sys.executable, str(script), "--hook"], input=payload, capture_output=True, text=True, env=env)
        assert result.returncode == 0
        assert result.stdout == ""
    assert set(tmp_path.iterdir()) == before


def test_hook_reports_only_counts(tmp_path):
    path = tmp_path / "session.jsonl"
    write_rows(path, [{"attachment": {"type": "prompt_snapshot", "systemPrompt": ["PRIVATE_PROMPT"]}}])
    result = subprocess.run([sys.executable, audit_module.__file__, "--hook"], input=json.dumps({"transcript_path": str(path)}),
                            capture_output=True, text=True, env={**os.environ, "TOKEN_REDUCE_LAYER_CONTEXT_AUDIT": "on"})
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "PRIVATE_PROMPT" not in result.stdout


def test_removed_deferred_definition_is_not_counted(tmp_path):
    path = tmp_path / "session.jsonl"
    write_rows(path, [{"attachment": {"type": "deferred_tools_record", "entries": [{"name": "mcp__gone__x", "input_schema": {}}]}},
                      {"attachment": {"type": "deferred_tools_delta", "removedNames": ["mcp__gone__x"]}}])
    assert audit_module.audit(path)["mcp_servers"] == {}
