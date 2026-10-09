"""End-to-end report, on-load hook, and bounded scan through the real CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "context_audit.py"


def cli(*args, env=None, payload=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, input=payload,
                          capture_output=True, text=True, timeout=15)


def test_report_from_transcript_file_preserves_usage_inventory_and_privacy(tmp_path):
    path = tmp_path / "session.jsonl"
    private = "PRIVATE_CONTENT_MUST_NOT_APPEAR"
    tool = {"name": "mcp__docs__search", "description": private,
            "input_schema": {"type": "object"}, "defer_loading": True}
    usage = {"type": "assistant", "message": {"id": "response-1", "usage": {
        "input_tokens": 2, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10}}}
    rows = [usage, usage,
            {"attachment": {"type": "prompt_snapshot", "systemPrompt": [private]}},
            {"attachment": {"type": "instructions", "files": [{"path": "CLAUDE.md", "content": private}]}},
            {"attachment": {"type": "deferred_tools_record", "entries": [tool, tool]}},
            {"attachment": {"type": "deferred_tools_delta", "addedNames": [tool["name"]], "addedLines": ["short catalog entry"]}}]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    before = path.read_bytes()
    output = tmp_path / "report.json"
    result = cli("--transcript", str(path), "--budget", "300", "--output", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["provider_input"]["latest"]["input_tokens"] == 112
    assert report["provider_input"]["responses"] == 1
    assert report["context_budget"]["measurement"] == "assumed_operator_supplied"
    assert report["categories"]["system_prompt"]["bytes"] == len(private.encode())
    assert report["mcp_servers"]["docs"]["definitions"] == 1
    assert report["mcp_servers"]["docs"]["deferred_definitions"] == 1
    assert report["recommendations"][0]["operator_approval_required"]
    assert private not in output.read_text()
    assert path.read_bytes() == before


def test_on_load_hook_is_opt_in_fail_open_and_does_not_write(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({"attachment": {"type": "prompt_snapshot", "systemPrompt": ["PRIVATE_PROMPT"]}}) + "\n")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for mode in ["auto", "off", "on"]:
        result = cli("--hook", env={**os.environ, "TOKEN_REDUCE_LAYER_CONTEXT_AUDIT": mode},
                     payload=json.dumps({"transcript_path": str(path)}))
        assert result.returncode == 0, result.stderr
        if mode == "on":
            assert json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        else:
            assert result.stdout == ""
        assert "PRIVATE_PROMPT" not in result.stdout
    for payload in ["INVALID_PRIVATE_INPUT", "[]", "null", "42", '"PRIVATE_SCALAR"']:
        invalid = cli("--hook", env={**os.environ, "TOKEN_REDUCE_LAYER_CONTEXT_AUDIT": "on"}, payload=payload)
        assert invalid.returncode == 0
        assert "INVALID_PRIVATE_INPUT" not in invalid.stdout + invalid.stderr
        assert "PRIVATE_SCALAR" not in invalid.stdout + invalid.stderr
        assert "Traceback" not in invalid.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_bounded_cli_scan_reports_missing_evidence_without_guessing(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text('not json\n{"type":"user","message":{"content":"unscanned"}}\n')
    result = cli("--transcript", str(path), "--max-bytes", "12")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["malformed_records"] == 1
    assert report["scan_truncated"]
    assert report["context_budget"]["tokens"] is None
    assert report["categories"]["mcp_tool_schemas"]["tokens"] is None
