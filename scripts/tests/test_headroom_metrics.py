from __future__ import annotations

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from measure_token_reduction import (
    apply_command_metrics,
    apply_text_metrics,
    apply_tool_name_metrics,
    fresh_metrics,
)


def test_headroom_text_mentions_are_counted() -> None:
    metrics = fresh_metrics("codex")

    apply_text_metrics(metrics, "Use Headroom for large tool-result payloads.")

    assert metrics["headroom_mention"] is True
    assert metrics["headroom_command"] is False


def test_headroom_command_examples_in_text_are_not_counted_as_usage() -> None:
    metrics = fresh_metrics("codex")

    apply_text_metrics(metrics, "Run `headroom wrap codex` after checking /readyz.")

    assert metrics["headroom_mention"] is True
    assert metrics["headroom_command"] is False


def test_headroom_shell_commands_are_counted() -> None:
    metrics = fresh_metrics("codex")

    apply_command_metrics(metrics, "headroom wrap codex --no-telemetry")

    assert metrics["headroom_command"] is True


def test_headroom_shell_commands_with_flags_are_counted() -> None:
    metrics = fresh_metrics("codex")

    apply_command_metrics(metrics, "headroom --no-telemetry wrap codex")

    assert metrics["headroom_command"] is True


def test_headroom_mcp_tool_names_are_counted() -> None:
    metrics = fresh_metrics("claude")

    apply_tool_name_metrics(metrics, "mcp__headroom__headroom_compress")

    assert metrics["headroom_command"] is True
