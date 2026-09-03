"""Unit tests for token_reduce_config.py — pure-function coverage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

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
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        incoming = {"b": 99, "c": 3}
        result = deep_merge(base, incoming)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_nested_dict_merges_recursively(self):
        base = {"telemetry": {"enabled": False, "endpoint": "http://old"}}
        incoming = {"telemetry": {"enabled": True}}
        result = deep_merge(base, incoming)
        assert result["telemetry"]["enabled"] is True
        assert result["telemetry"]["endpoint"] == "http://old"

    def test_base_unchanged(self):
        base = {"x": {"y": 1}}
        _ = deep_merge(base, {"x": {"z": 2}})
        assert base == {"x": {"y": 1}}  # original not mutated

    def test_empty_incoming_returns_copy_of_base(self):
        base = {"a": 1}
        result = deep_merge(base, {})
        assert result == {"a": 1}
        assert result is not base

    def test_incoming_non_dict_value_wins_over_dict(self):
        base = {"routing": {"profile": "balanced"}}
        incoming = {"routing": "override_string"}
        result = deep_merge(base, incoming)
        assert result["routing"] == "override_string"

    def test_deep_three_levels(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        incoming = {"a": {"b": {"c": 99}}}
        result = deep_merge(base, incoming)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2


# ---------------------------------------------------------------------------
# parse_value
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_true_string(self):
        assert parse_value("true") is True
        assert parse_value("True") is True
        assert parse_value("TRUE") is True

    def test_false_string(self):
        assert parse_value("false") is False
        assert parse_value("False") is False

    def test_null_variants(self):
        assert parse_value("null") is None
        assert parse_value("none") is None
        assert parse_value("None") is None

    def test_integer(self):
        assert parse_value("42") == 42
        assert isinstance(parse_value("42"), int)

    def test_float(self):
        assert parse_value("3.14") == 3.14
        assert isinstance(parse_value("3.14"), float)

    def test_plain_string(self):
        assert parse_value("hello") == "hello"
        assert parse_value("http://example.com") == "http://example.com"

    def test_whitespace_stripped(self):
        assert parse_value("  true  ") is True
        assert parse_value("  42  ") == 42


# ---------------------------------------------------------------------------
# set_nested
# ---------------------------------------------------------------------------

class TestSetNested:
    def test_top_level_key(self):
        cfg: dict = {}
        set_nested(cfg, "enforcement", "block")
        assert cfg["enforcement"] == "block"

    def test_two_level_key(self):
        cfg: dict = {"telemetry": {"enabled": False}}
        set_nested(cfg, "telemetry.enabled", True)
        assert cfg["telemetry"]["enabled"] is True

    def test_creates_missing_intermediate_dicts(self):
        cfg: dict = {}
        set_nested(cfg, "routing.profile", "aggressive")
        assert cfg == {"routing": {"profile": "aggressive"}}

    def test_replaces_non_dict_intermediate(self):
        cfg: dict = {"routing": "old_string"}
        set_nested(cfg, "routing.profile", "balanced")
        assert cfg["routing"]["profile"] == "balanced"

    def test_three_level_key(self):
        cfg: dict = {}
        set_nested(cfg, "companions.caliper.url", "http://127.0.0.1:1234")
        assert cfg["companions"]["caliper"]["url"] == "http://127.0.0.1:1234"

    def test_overwrite_existing_leaf(self):
        cfg = {"budgets": {"daily_warning_usd": 20}}
        set_nested(cfg, "budgets.daily_warning_usd", 50)
        assert cfg["budgets"]["daily_warning_usd"] == 50


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

    def test_load_returns_default_when_root_is_not_dict(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(path)
        try:
            cfg = load_config()
            assert cfg == dict(DEFAULT_CONFIG)
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "config.json"
        os.environ["TOKEN_REDUCE_CONFIG_PATH"] = str(nested)
        try:
            saved_path = save_config(dict(DEFAULT_CONFIG))
            assert saved_path.exists()
        finally:
            del os.environ["TOKEN_REDUCE_CONFIG_PATH"]
