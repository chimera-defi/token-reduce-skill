"""Unit tests for token_reduce_config.py — pure-function coverage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from token_reduce_config import (
    DEFAULT_CONFIG,
    config_path,
    deep_merge,
    load_config,
    parse_value,
    save_config,
    set_nested,
)


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------

class TestDeepMerge:

    def test_nested_dict_merges_recursively(self):
        base = {"telemetry": {"enabled": False, "endpoint": "http://old"}}
        incoming = {"telemetry": {"enabled": True}}
        result = deep_merge(base, incoming)
        assert result["telemetry"]["enabled"] is True
        assert result["telemetry"]["endpoint"] == "http://old"



    def test_incoming_non_dict_value_wins_over_dict(self):
        base = {"routing": {"profile": "balanced"}}
        incoming = {"routing": "override_string"}
        result = deep_merge(base, incoming)
        assert result["routing"] == "override_string"



# ---------------------------------------------------------------------------
# parse_value
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_true_string(self):
        assert parse_value("true") is True
        assert parse_value("True") is True
        assert parse_value("TRUE") is True



    def test_integer(self):
        assert parse_value("42") == 42
        assert isinstance(parse_value("42"), int)





# ---------------------------------------------------------------------------
# set_nested
# ---------------------------------------------------------------------------

class TestSetNested:

    def test_two_level_key(self):
        cfg: dict = {"telemetry": {"enabled": False}}
        set_nested(cfg, "telemetry.enabled", True)
        assert cfg["telemetry"]["enabled"] is True

    def test_creates_missing_intermediate_dicts(self):
        cfg: dict = {}
        set_nested(cfg, "routing.profile", "aggressive")
        assert cfg == {"routing": {"profile": "aggressive"}}





# ---------------------------------------------------------------------------
# config_path
# ---------------------------------------------------------------------------

class TestConfigPath:
    def test_default_path_under_home(self):
        env_backup = os.environ.pop("TOKEN_REDUCE_CONFIG_PATH", None)
        try:
            p = config_path()
            assert ".config" in str(p)
            assert "token-reduce" in str(p)
            assert p.name == "config.json"
        finally:
            if env_backup is not None:
                os.environ["TOKEN_REDUCE_CONFIG_PATH"] = env_backup

    def test_env_override(self, tmp_path):
        override = str(tmp_path / "custom_config.json")
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = override
        try:
            p = config_path()
            assert str(p) == str(Path(override).expanduser().resolve())
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------

class TestLoadSaveConfig:
    def test_load_returns_default_when_no_file(self, tmp_path):
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(tmp_path / "missing.json")
        try:
            cfg = load_config()
            assert cfg["version"] == DEFAULT_CONFIG["version"]
            assert "telemetry" in cfg
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "config.json"
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(path)
        try:
            original = load_config()
            original["enforcement"] = "block"
            save_config(original)
            reloaded = load_config()
            assert reloaded["enforcement"] == "block"
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]

    def test_load_merges_partial_file(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"enforcement": "block"}), encoding="utf-8")
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(path)
        try:
            cfg = load_config()
            # custom key preserved
            assert cfg["enforcement"] == "block"
            # default keys filled in
            assert "telemetry" in cfg
            assert "routing" in cfg
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]

    def test_load_returns_default_on_invalid_json(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("not valid json", encoding="utf-8")
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(path)
        try:
            cfg = load_config()
            assert cfg == dict(DEFAULT_CONFIG)
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]




def test_null_layers_in_config_means_defaults(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"layers": null}')
    monkeypatch.setenv("TOKEN_REDUCE_CONFIG_PATH", str(cfg))
    monkeypatch.delenv("TOKEN_REDUCE_LAYER_SEARCH_QMD", raising=False)
    import token_reduce_config as c
    assert c.layer_mode("search_qmd") == "auto"
