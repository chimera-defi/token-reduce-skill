#!/usr/bin/env python3
"""Shared config helpers for token-reduce local management scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "telemetry": {
        "enabled": False,
        "endpoint": "",
        "api_key": "",
        "signing_secret": "",
        "workspace_root": "/root/.openclaw/workspace/dev",
        "upload_timeout_seconds": 10,
    },
    "benchmark": {
        "max_age_days": 14,
    },
    "updates": {
        "auto_update": False,
        "check_on_manage": True,
    },
}


def config_path() -> Path:
    override = os.environ.get("TOKEN_REDUCE_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".config" / "token-reduce" / "config.json").resolve()


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return dict(DEFAULT_CONFIG)
    return deep_merge(dict(DEFAULT_CONFIG), raw)


def save_config(config: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def parse_value(raw: str) -> Any:
    lowered = raw.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def set_nested(config: dict[str, Any], dotted_key: str, value: Any) -> None:
    current: dict[str, Any] = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value
