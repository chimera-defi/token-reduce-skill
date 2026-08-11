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
    def test_empty_string_returns_empty(self):
        assert tail_lines("") == ""

    def test_whitespace_only_returns_empty(self):
        assert tail_lines("   \n  \n") == ""

    def test_single_line_returned(self):
        assert tail_lines("hello") == "hello"

    def test_fewer_lines_than_max_returns_all(self):
        text = "a\nb\nc"
        result = tail_lines(text, max_lines=10)
        assert result == "a\nb\nc"

    def test_more_lines_than_max_returns_last_n(self):
        lines = [str(i) for i in range(25)]
        text = "\n".join(lines)
        result = tail_lines(text, max_lines=5)
        assert result == "20\n21\n22\n23\n24"

    def test_exact_max_lines_returns_all(self):
        lines = [str(i) for i in range(20)]
        text = "\n".join(lines)
        result = tail_lines(text, max_lines=20)
        assert result == text

    def test_blank_lines_are_skipped(self):
        text = "a\n\n\nb\n\nc"
        result = tail_lines(text, max_lines=20)
        # blank lines excluded, so only a, b, c remain
        assert result == "a\nb\nc"

    def test_blank_lines_skipped_before_tail_count(self):
        # 5 non-blank lines, max_lines=3 → last 3 non-blank
        text = "1\n\n2\n\n3\n\n4\n\n5"
        result = tail_lines(text, max_lines=3)
        assert result == "3\n4\n5"

    def test_default_max_lines_is_20(self):
        lines = [str(i) for i in range(30)]
        text = "\n".join(lines)
        result = tail_lines(text)
        assert result == "\n".join(str(i) for i in range(10, 30))

    def test_max_lines_one_returns_last_line(self):
        assert tail_lines("a\nb\nc", max_lines=1) == "c"


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
    def test_output_is_string(self):
        report = _make_report([_passing_step()])
        result = render_markdown(report)
        assert isinstance(result, str)

    def test_has_checkpoint_gate_header(self):
        result = render_markdown(_make_report([_passing_step()]))
        assert "# Checkpoint Gate" in result

    def test_contains_generated_at(self):
        result = render_markdown(_make_report([_passing_step()]))
        assert "2026-07-30" in result

    def test_contains_repo_root(self):
        result = render_markdown(_make_report([_passing_step()]))
        assert "/home/user/token-reduce-skill" in result

    def test_overall_pass_true_in_output(self):
        result = render_markdown(_make_report([_passing_step()], overall_pass=True))
        assert "true" in result

    def test_overall_pass_false_in_output(self):
        result = render_markdown(_make_report([_failing_step()], overall_pass=False))
        assert "false" in result

    def test_table_row_for_passing_step(self):
        result = render_markdown(_make_report([_passing_step("validate")]))
        assert "validate" in result
        assert "pass" in result

    def test_no_failures_section_when_all_pass(self):
        result = render_markdown(_make_report([_passing_step(), _passing_step("measure_repo")]))
        assert "## Failures" not in result

    def test_failures_section_present_when_step_fails(self):
        result = render_markdown(_make_report([_failing_step()], overall_pass=False))
        assert "## Failures" in result

    def test_failing_step_name_in_failures_section(self):
        result = render_markdown(_make_report([_failing_step("release_gate")], overall_pass=False))
        assert "release_gate" in result

    def test_failing_step_stderr_in_output(self):
        result = render_markdown(_make_report([_failing_step(stderr="gate failed: stale lock")], overall_pass=False))
        assert "gate failed: stale lock" in result

    def test_failing_step_with_stdout_not_stderr(self):
        step = _failing_step()
        step["stderr_tail"] = ""
        step["stdout_tail"] = "some stdout output"
        result = render_markdown(_make_report([step], overall_pass=False))
        assert "some stdout output" in result

    def test_table_contains_duration(self):
        result = render_markdown(_make_report([_passing_step()]))
        assert "123" in result

    def test_multiple_steps_all_appear_in_table(self):
        steps = [_passing_step("step_a"), _passing_step("step_b"), _failing_step("step_c")]
        result = render_markdown(_make_report(steps, overall_pass=False))
        assert "step_a" in result
        assert "step_b" in result
        assert "step_c" in result

    def test_ends_with_newline(self):
        result = render_markdown(_make_report([_passing_step()]))
        assert result.endswith("\n")

    def test_empty_steps_list_no_failures_section(self):
        result = render_markdown(_make_report([]))
        assert "## Failures" not in result
