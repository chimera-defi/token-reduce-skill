"""Regression tests for dispatch ranking and config-path consistency."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
DISPATCH = SCRIPTS_DIR / "token_reduce_dispatch.py"


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
        capture_output=True,
    )


def test_dispatch_accepts_events_file_without_argparse_failure(tmp_path: Path) -> None:
    """The paths wrapper passes --events-file whenever telemetry exists."""
    _init_git_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "token-reduce-paths.sh").write_text("#!/usr/bin/env bash\n")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "architecture.md").write_text("# Architecture\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)

    events = tmp_path / "artifacts" / "token-reduction" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        json.dumps(
            {
                "event": "file_read_after_helper",
                "query": "architecture docs",
                "path": "references/architecture.md",
            }
        )
        + "\n"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(DISPATCH),
            "--mode",
            "paths",
            "--query",
            "architecture docs",
            "--repo-root",
            str(tmp_path),
            "--events-file",
            str(events),
        ],
        input="scripts/token-reduce-paths.sh\nreferences/architecture.md\n",
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "unrecognized arguments" not in result.stderr
    assert result.stdout.splitlines()[0] == "references/architecture.md"


def test_config_path_is_consistent_with_token_reduce_config(tmp_path: Path) -> None:
    """Setup docs and manage scripts should not hard-code a different config path."""
    env = os.environ.copy()
    env["TOKEN_REDUCE_CONFIG_PATH"] = str(tmp_path / "token-reduce-config.json")
    code = (
        "from token_reduce_config import config_path; "
        "print(config_path())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(SCRIPTS_DIR),
        env={**env, "PYTHONPATH": str(SCRIPTS_DIR)},
        text=True,
        capture_output=True,
        check=True,
    )
    canonical = result.stdout.strip()

    skill_text = (SCRIPTS_DIR.parent / "SKILL.md").read_text()
    manage_text = (SCRIPTS_DIR / "token-reduce-manage.sh").read_text()
    wizard_text = (SCRIPTS_DIR / "token_reduce_setup_wizard.py").read_text()

    assert "~/.claude/token-reduce-config.json" not in skill_text
    assert "../.claude/token-reduce-config.json" not in manage_text
    assert "~/.claude/token-reduce-config.json" not in wizard_text
    assert canonical.endswith("token-reduce-config.json")
