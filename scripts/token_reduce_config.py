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
        "workspace_days": 14,
        "workspace_include_source_repo": False,
        "upload_timeout_seconds": 10,
    },
    "benchmark": {
        "max_age_days": 14,
    },
    "updates": {
        "auto_update": False,
        "workspace_auto_update": True,
        "workspace_force_relink": True,
        "check_on_manage": True,
    },
    "routing": {
        "profile": "balanced",
        "adaptive_hint": True,
        "behavior_days": 3,
        "rapid_repeat_snippet_threshold": 0.35,
        "enable_structural": True,
        "enable_context_mode_recommendations": True,
        "enable_headroom_recommendations": True,
        "enable_code_review_graph_recommendations": True,
    },
    "delegates": {
        "devin": {
            "enabled": False,
            "mode": "recommend_and_wrap",
            "description": "Browser, UI, screenshot, sandbox, adversarial review",
        },
        "kimi": {
            "enabled": False,
            "mode": "recommend_only",
            "description": "Cheap research, review, summarize",
        },
        "grok": {
            "enabled": False,
            "mode": "recommend_only",
            "description": "Multi-file refactor, large codebase",
        },
        "spark": {
            "enabled": False,
            "mode": "recommend_only",
            "description": "Local Codex write-mode implementation",
        },
    },
    "companions": {
        "headroom": {"enabled": True},
        "caveman": {"enabled": False},
        "context_mode": {"enabled": True},
        "code_review_graph": {"enabled": False},
        "qmd": {"enabled": True},
    },
    "enforcement": "warn_first",
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


def _list_tools(config: dict[str, Any]) -> None:
    import shutil
    print("Delegates:")
    for name, cfg in config.get("delegates", {}).items():
        installed = "installed" if shutil.which(f"{name}-delegate") else "not found"
        enabled = "enabled" if cfg.get("enabled") else "disabled"
        mode = cfg.get("mode", "?")
        print(f"  {name:<8}  {enabled:<8}  {installed:<12}  mode={mode}")
    print("Companions:")
    for name, cfg in config.get("companions", {}).items():
        installed = "installed" if shutil.which(name) else "not found"
        enabled = "enabled" if cfg.get("enabled") else "disabled"
        print(f"  {name:<16}  {enabled:<8}  {installed}")
    print(f"Enforcement: {config.get('enforcement', 'warn_first')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="token-reduce config CLI")
    parser.add_argument("--path", action="store_true", help="Print the active config path")
    parser.add_argument("--list-tools", action="store_true", help="List delegates/companions")
    parser.add_argument("--get", metavar="KEY", help="Get a config value by dotted key")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a config value")
    args = parser.parse_args()
    cfg = load_config()
    if args.path:
        print(config_path())
    elif args.list_tools:
        _list_tools(cfg)
    elif args.get:
        parts = args.get.split(".")
        cur: Any = cfg
        for p in parts:
            cur = cur.get(p) if isinstance(cur, dict) else None
        print(json.dumps(cur))
    elif args.set:
        key, raw_val = args.set
        set_nested(cfg, key, parse_value(raw_val))
        path = save_config(cfg)
        print(f"Saved to {path}")
    else:
        parser.print_help()
