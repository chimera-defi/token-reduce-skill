"""Three real CLI flows: session choices, discovery, and RTK approval."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def cli(*args, env, cwd):
    return subprocess.run([sys.executable, str(SCRIPTS / "token_reduce_layers.py"), *args],
                          env=env, cwd=cwd, capture_output=True, text=True, timeout=15)


def test_task_config_override_status_and_literal_argv(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"layers": {"rtk": "off", "memory": "off"}}))
    env = {**os.environ, "TOKEN_REDUCE_CONFIG_PATH": str(config)}
    assert cli("mode", "rtk", env=env, cwd=tmp_path).stdout.strip() == "off"
    override = {**env, "TOKEN_REDUCE_LAYER_RTK": "on"}
    assert cli("mode", "rtk", env=override, cwd=tmp_path).stdout.strip() == "on"
    report = cli("status", env=env, cwd=tmp_path)
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["layers"]["rtk"]["mode"] == "off"
    output = tmp_path / "argv.txt"
    literal = 'spaces $HOME `false` $(false) ; literal'
    result = cli("run", "--", sys.executable, "-c",
                 "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);sys.exit(7)",
                 str(output), literal, env=env, cwd=tmp_path)
    assert result.returncode == 7
    assert output.read_text() == literal
    assert json.loads(config.read_text())["layers"]["rtk"] == "off"


def test_disabled_qmd_and_memory_run_real_discovery(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    marker = tmp_path / "qmd-called"
    probe = binary / "qmd"
    probe.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    probe.chmod(0o755)
    (tmp_path / "topic.md").write_text("session layers unique discovery topic")
    env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
           "TOKEN_REDUCE_LAYER_SEARCH_QMD": "off", "TOKEN_REDUCE_LAYER_MEMORY": "off"}
    result = subprocess.run([str(SCRIPTS / "token-reduce-paths.sh"), "unique"], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "topic.md" in result.stdout
    assert not marker.exists()
    assert "brain-hint" not in result.stderr


@pytest.mark.skipif(shutil.which("rtk") is None, reason="real RTK required for companion e2e")
def test_real_rtk_rewrite_and_approved_readonly_command(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    env = {**os.environ, "TOKEN_REDUCE_LAYER_RTK": "on"}
    result = cli("run", "--", "git", "status", env=env, cwd=tmp_path)
    assert result.returncode in {0, 3}, result.stderr
    if result.returncode == 3:
        assert result.stdout.strip() == "rtk git status"
    approved = cli("run", "--approved-rtk-rewrite", "--", "git", "status", env=env, cwd=tmp_path)
    assert approved.returncode == 0, approved.stderr
    assert approved.stdout.strip()
