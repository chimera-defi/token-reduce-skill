import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from token_reduce_config import DEFAULT_CONFIG, layer_mode, load_config
from token_reduce_layers import run_command, status


@pytest.fixture(autouse=True)
def config(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setenv("TOKEN_REDUCE_CONFIG_PATH", str(path))
    for name in DEFAULT_CONFIG["layers"]:
        monkeypatch.delenv(f"TOKEN_REDUCE_LAYER_{name.upper()}", raising=False)
    return path


def test_defaults_do_not_share_nested_mutations():
    first = load_config()
    first["layers"]["rtk"] = "off"
    assert load_config()["layers"]["rtk"] == "auto"


def test_precedence_and_bad_override(config, monkeypatch):
    config.write_text(json.dumps({"layers": {"rtk": "off"}}))
    assert layer_mode("rtk") == "off"
    monkeypatch.setenv("TOKEN_REDUCE_LAYER_RTK", "on")
    assert layer_mode("rtk") == "on"
    monkeypatch.setenv("TOKEN_REDUCE_LAYER_RTK", "oops")
    with pytest.raises(ValueError):
        layer_mode("rtk")


def test_memory_off_does_not_probe_tools(monkeypatch):
    import brain_hint
    monkeypatch.setenv("TOKEN_REDUCE_LAYER_MEMORY", "off")
    monkeypatch.setattr(brain_hint.shutil, "which", lambda _: pytest.fail("tool probe while off"))
    assert brain_hint.hint_line("topic") is None


def test_run_auto_preserves_argv_and_exit(config, tmp_path):
    target = tmp_path / "out"
    text = 'spaces $HOME `false` $(false) ; literal'
    assert run_command([sys.executable, "-c", "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);sys.exit(7)", str(target), text]) == 7
    assert target.read_text() == text


def test_rtk_off_never_rewrites(monkeypatch):
    monkeypatch.setenv("TOKEN_REDUCE_LAYER_RTK", "off")
    monkeypatch.setattr("token_reduce_layers.shutil.which", lambda _: pytest.fail("RTK probe"))
    assert run_command([sys.executable, "-c", "pass"]) == 0


def test_status_no_savings_are_not_zero(monkeypatch):
    monkeypatch.setattr("token_reduce_layers.shutil.which", lambda _: None)
    monkeypatch.setattr("token_reduce_layers.headroom_stats", lambda: {"available": False})
    report = status()
    assert report["layers"]["rtk"]["tokens_saved"] is None
    assert report["layers"]["mcp_trim"]["tokens_saved"] is None
    assert report["layers"]["context_audit"]["mode"] == "auto"


def test_qmd_off_uses_fallback_without_calling_qmd(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[1]
    binary = tmp_path / "bin"
    binary.mkdir()
    marker = tmp_path / "qmd-called"
    qmd = binary / "qmd"
    qmd.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    qmd.chmod(0o755)
    (tmp_path / "topic.md").write_text("session layers unique topic")
    monkeypatch.setenv("TOKEN_REDUCE_LAYER_SEARCH_QMD", "off")
    import os
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    proc = subprocess.run([str(scripts / "token-reduce-search.sh"), "--paths-only", "unique"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "topic.md" in proc.stdout
    assert not marker.exists()
