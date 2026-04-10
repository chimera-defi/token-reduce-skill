#!/usr/bin/env python3
"""Manage local token-reduce settings (telemetry opt-in and updates)."""
from __future__ import annotations

import argparse
import json
from typing import Any

from token_reduce_config import DEFAULT_CONFIG, load_config, parse_value, save_config, set_nested


def cmd_show() -> int:
    config = load_config()
    print(json.dumps(config, indent=2))
    return 0


def cmd_set(key: str, raw_value: str) -> int:
    config = load_config()
    set_nested(config, key, parse_value(raw_value))
    path = save_config(config)
    print(f"updated {path}: {key}={raw_value}")
    return 0


def cmd_reset() -> int:
    path = save_config(dict(DEFAULT_CONFIG))
    print(f"reset {path} to defaults")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show")
    set_parser = sub.add_parser("set")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    sub.add_parser("reset")

    args = parser.parse_args()

    if args.command == "show":
        return cmd_show()
    if args.command == "set":
        return cmd_set(args.key, args.value)
    if args.command == "reset":
        return cmd_reset()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
