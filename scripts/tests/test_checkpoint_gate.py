"""Tests for zero-coverage functions in checkpoint_gate.py: tail_lines and render_markdown."""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from checkpoint_gate import tail_lines, render_markdown


# ---------------------------------------------------------------------------
# tail_lines
# ---------------------------------------------------------------------------

class TestTailLines:




    def test_more_lines_than_max_returns_last_n(self):
        lines = [str(i) for i in range(25)]
        text = "\n".join(lines)
        result = tail_lines(text, max_lines=5)
        assert result == "20\n21\n22\n23\n24"


    def test_blank_lines_are_skipped(self):
        text = "a\n\n\nb\n\nc"
        result = tail_lines(text, max_lines=20)
        # blank lines excluded, so only a, b, c remain
        assert result == "a\nb\nc"





# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

def _make_report(steps: list[dict], overall_pass: bool = True) -> dict:
    return {
        "generated_at": "2026-07-30T00:00:00+00:00",
        "repo_root": "/home/user/token-reduce-skill",
        "overall_pass": overall_pass,
        "steps": steps,
    }


def _passing_step(name: str = "validate") -> dict:
    return {
        "name": name,
        "command": ["./scripts/token-reduce-manage.sh", name],
        "exit_code": 0,
        "duration_ms": 123,
        "status": "pass",
        "stdout_tail": "OK",
        "stderr_tail": "",
    }


def _failing_step(name: str = "release_gate", stderr: str = "Error: gate failed") -> dict:
    return {
        "name": name,
        "command": ["./scripts/token-reduce-manage.sh", name],
        "exit_code": 1,
        "duration_ms": 456,
        "status": "fail",
        "stdout_tail": "",
        "stderr_tail": stderr,
    }


class TestRenderMarkdown:







    def test_no_failures_section_when_all_pass(self):
        result = render_markdown(_make_report([_passing_step(), _passing_step("measure_repo")]))
        assert "## Failures" not in result

    def test_failures_section_present_when_step_fails(self):
        result = render_markdown(_make_report([_failing_step()], overall_pass=False))
        assert "## Failures" in result


    def test_failing_step_stderr_in_output(self):
        result = render_markdown(_make_report([_failing_step(stderr="gate failed: stale lock")], overall_pass=False))
        assert "gate failed: stale lock" in result





