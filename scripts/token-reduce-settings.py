#!/usr/bin/env python3
"""Manage local token-reduce settings (telemetry opt-in and updates)."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any

from token_reduce_config import DEFAULT_CONFIG, load_config, parse_value, save_config, set_nested


PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "minimal-load": {
        "routing": {
            "profile": "minimal-load",
            "adaptive_hint": True,
            "behavior_days": 1,
            "rapid_repeat_snippet_threshold": 0.65,
            "enable_structural": False,
            "enable_context_mode_recommendations": False,
            "enable_code_review_graph_recommendations": False,
        }
    },
    "balanced": {
        "routing": {
            "profile": "balanced",
            "adaptive_hint": True,
            "behavior_days": 3,
            "rapid_repeat_snippet_threshold": 0.35,
            "enable_structural": True,
            "enable_context_mode_recommendations": True,
            "enable_code_review_graph_recommendations": True,
        }
    },
    "max-savings": {
        "routing": {
            "profile": "max-savings",
            "adaptive_hint": True,
            "behavior_days": 7,
            "rapid_repeat_snippet_threshold": 0.2,
            "enable_structural": True,
            "enable_context_mode_recommendations": True,
            "enable_code_review_graph_recommendations": True,
        }
    },
}


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


def cmd_profile_list() -> int:
    print(json.dumps({"profiles": sorted(PROFILE_PRESETS.keys())}, indent=2))
    return 0


def cmd_profile_show(name: str | None) -> int:
    if not name:
        config = load_config()
        active = str(config.get("routing", {}).get("profile", "balanced"))
        print(json.dumps({"active_profile": active}, indent=2))
        return 0
    preset = PROFILE_PRESETS.get(name)
    if preset is None:
        raise SystemExit(f"unknown profile: {name}")
    print(json.dumps({"name": name, "preset": preset}, indent=2))
    return 0


def cmd_profile_apply(name: str) -> int:
    preset = PROFILE_PRESETS.get(name)
    if preset is None:
        raise SystemExit(f"unknown profile: {name}")
    config = load_config()
    for section, value in preset.items():
        if isinstance(value, dict):
            base = config.get(section)
            if not isinstance(base, dict):
                base = {}
                config[section] = base
            base.update(value)
        else:
            config[section] = value
    path = save_config(config)
    print(json.dumps({"applied_profile": name, "config_path": str(path)}, indent=2))
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
    profile_parser = sub.add_parser("profile")
    profile_sub = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_sub.add_parser("list")
    profile_show = profile_sub.add_parser("show")
    profile_show.add_argument("name", nargs="?")
    profile_apply = profile_sub.add_parser("apply")
    profile_apply.add_argument("name")
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
    if args.command == "profile":
        if args.profile_command == "list":
            return cmd_profile_list()
        if args.profile_command == "show":
            return cmd_profile_show(args.name)
        if args.profile_command == "apply":
            return cmd_profile_apply(args.name)
        return 2
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
