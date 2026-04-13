#!/usr/bin/env python3
"""Manage local token-reduce settings (telemetry opt-in and updates)."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any

from token_reduce_config import DEFAULT_CONFIG, load_config, parse_value, save_config, set_nested


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = deepcopy(config)
    telemetry = redacted.get("telemetry")
    if isinstance(telemetry, dict):
        for key in ("api_key", "signing_secret"):
            value = telemetry.get(key)
            if isinstance(value, str) and value:
                telemetry[key] = "***redacted***"
    return redacted


def cmd_show(*, raw: bool) -> int:
    config = load_config()
    if not raw:
        config = redact_config(config)
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


def prompt_yes_no(message: str, *, default: bool) -> bool:
    default_hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{message} [{default_hint}] ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def cmd_onboard(*, yes: bool, no: bool, endpoint: str | None, non_interactive: bool) -> int:
    config = load_config()
    telemetry = config.setdefault("telemetry", {})
    current_enabled = bool(telemetry.get("enabled", False))
    current_endpoint = str(telemetry.get("endpoint", "") or "")

    if yes:
        target_enabled = True
    elif no:
        target_enabled = False
    elif non_interactive:
        target_enabled = current_enabled
    else:
        target_enabled = prompt_yes_no(
            "Opt in to anonymized token-reduce telemetry to improve routing and defaults?",
            default=current_enabled,
        )

    if target_enabled:
        target_endpoint = endpoint if endpoint is not None else current_endpoint
        if endpoint is None and not non_interactive:
            entered = input(
                "Telemetry endpoint URL (optional; leave blank to keep local-only telemetry): "
            ).strip()
            if entered:
                target_endpoint = entered
        telemetry["endpoint"] = target_endpoint
    telemetry["enabled"] = target_enabled

    path = save_config(config)
    summary = {
        "telemetry_enabled": bool(telemetry.get("enabled", False)),
        "endpoint_configured": bool(str(telemetry.get("endpoint", "") or "").strip()),
        "config_path": str(path),
    }
    print(json.dumps(summary, indent=2))
    if target_enabled:
        print("next: token-reduce-manage telemetry-sync")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    show_parser = sub.add_parser("show")
    show_parser.add_argument("--raw", action="store_true", help="Show secrets without redaction")
    set_parser = sub.add_parser("set")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    sub.add_parser("reset")
    onboard_parser = sub.add_parser("onboard")
    onboard_parser.add_argument("--yes", action="store_true")
    onboard_parser.add_argument("--no", action="store_true")
    onboard_parser.add_argument("--endpoint")
    onboard_parser.add_argument("--non-interactive", action="store_true")

    args = parser.parse_args()

    if args.command == "show":
        return cmd_show(raw=args.raw)
    if args.command == "set":
        return cmd_set(args.key, args.value)
    if args.command == "reset":
        return cmd_reset()
    if args.command == "onboard":
        if args.yes and args.no:
            raise SystemExit("--yes and --no are mutually exclusive")
        return cmd_onboard(
            yes=args.yes,
            no=args.no,
            endpoint=args.endpoint,
            non_interactive=args.non_interactive,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
