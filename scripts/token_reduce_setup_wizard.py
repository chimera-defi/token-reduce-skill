#!/usr/bin/env python3
"""Interactive setup wizard for token-reduce skill.

Detects available tools, prompts user for preferences, and saves the shared
config path from token_reduce_config.py. Supports --non-interactive for CI.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from token_reduce_config import DEFAULT_CONFIG, load_config, save_config


_DELEGATES = {
    "devin": ("devin-delegate", "Browser, UI, screenshot, sandbox, adversarial review"),
    "kimi": ("kimi-delegate", "Cheap research, review, summarize"),
    "grok": ("grok-delegate", "Multi-file refactor, large codebase"),
    "spark": ("spark", "Local Codex write-mode implementation"),
}

_COMPANIONS = {
    "headroom": ("headroom", "Context compression — save tokens on large outputs"),
    "qmd": ("qmd", "QMD semantic search"),
    "caveman": ("caveman", "Budget/token estimation"),
    "context_mode": (None, "Context-mode adaptive routing"),
    "code_review_graph": (None, "Code-review graph companion"),
}

_ENFORCEMENT_CHOICES = {
    "1": ("warn_first", "Warn first (recommended) — allow on first occurrence, block on repeat"),
    "2": ("hard_block", "Hard block — immediately block all broad scans"),
    "3": ("advisory", "Advisory only — never block, only recommend helpers"),
}

_PROFILE_CHOICES = {
    "1": ("balanced", "Balanced (recommended) — use all helpers"),
    "2": ("minimal-load", "Minimal-load — QMD/rg only, no structural"),
    "3": ("max-savings", "Max-savings — all helpers including context-mode"),
}


def _detect(cmd: str | None) -> bool:
    if cmd is None:
        return False
    return shutil.which(cmd) is not None


def _ask(prompt: str, default: str) -> str:
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer if answer else default
    except (EOFError, KeyboardInterrupt):
        return default


def run_wizard(non_interactive: bool = False) -> dict:
    config = load_config()
    config.setdefault("delegates", DEFAULT_CONFIG["delegates"].copy())
    config.setdefault("companions", DEFAULT_CONFIG["companions"].copy())
    config.setdefault("enforcement", DEFAULT_CONFIG["enforcement"])

    if not non_interactive:
        print("\n=== Token-Reduce Skill Setup ===\n")

    # --- Delegates ---
    if not non_interactive:
        print("Checking delegates...")
    for name, (cmd, desc) in _DELEGATES.items():
        detected = _detect(cmd)
        default_enabled = detected
        config["delegates"].setdefault(name, {})
        if non_interactive:
            config["delegates"][name]["enabled"] = default_enabled
        else:
            status = "found" if detected else "not found"
            answer = _ask(
                f"  {name} ({desc}) [{status}] — enable?",
                "y" if default_enabled else "n",
            )
            config["delegates"][name]["enabled"] = answer.lower().startswith("y")
        config["delegates"][name].setdefault(
            "mode", DEFAULT_CONFIG["delegates"].get(name, {}).get("mode", "recommend_only")
        )
        config["delegates"][name].setdefault(
            "description", DEFAULT_CONFIG["delegates"].get(name, {}).get("description", desc)
        )

    # --- Companions ---
    if not non_interactive:
        print("\nChecking companions...")
    for name, (cmd, desc) in _COMPANIONS.items():
        detected = _detect(cmd)
        default_enabled = detected
        config["companions"].setdefault(name, {})
        if non_interactive:
            config["companions"][name]["enabled"] = default_enabled
        else:
            status = "found" if (cmd and detected) else ("built-in" if cmd is None else "not found")
            answer = _ask(
                f"  {name} ({desc}) [{status}] — enable?",
                "y" if (detected or cmd is None) else "n",
            )
            config["companions"][name]["enabled"] = answer.lower().startswith("y")

    # --- Enforcement ---
    if not non_interactive:
        print("\nEnforcement preference:")
        for k, (_, label) in _ENFORCEMENT_CHOICES.items():
            print(f"  {k}) {label}")
        choice = _ask("Choose", "1")
        config["enforcement"] = _ENFORCEMENT_CHOICES.get(choice, _ENFORCEMENT_CHOICES["1"])[0]

    # --- Profile ---
    if not non_interactive:
        print("\nRouting profile:")
        for k, (_, label) in _PROFILE_CHOICES.items():
            print(f"  {k}) {label}")
        choice = _ask("Choose", "1")
        config.setdefault("routing", {})
        config["routing"]["profile"] = _PROFILE_CHOICES.get(choice, _PROFILE_CHOICES["1"])[0]

    # --- Save ---
    path = save_config(config)

    # --- Summary ---
    enabled_delegates = [n for n, cfg in config["delegates"].items() if cfg.get("enabled")]
    enabled_companions = [n for n, cfg in config["companions"].items() if cfg.get("enabled")]
    if not non_interactive:
        print(
            f"\nConfigured {len(enabled_delegates)} delegate(s): {', '.join(enabled_delegates) or 'none'}"
        )
        print(
            f"Configured {len(enabled_companions)} companion(s): {', '.join(enabled_companions) or 'none'}"
        )
        print(f"Enforcement: {config['enforcement']}")
        print(f"Saved to {path}\n")

    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Token-Reduce Skill Setup Wizard")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use auto-detected defaults without prompting (for CI)",
    )
    args = parser.parse_args()
    run_wizard(non_interactive=args.non_interactive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
