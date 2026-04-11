#!/usr/bin/env python3
"""Check companion dependency freshness and optionally apply updates."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Dependency:
    name: str
    command: list[str]
    source_type: str
    source_value: str
    update_hint: str


DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency(
        name="qmd",
        command=["qmd", "--version"],
        source_type="github",
        source_value="tobi/qmd",
        update_hint="bun install -g https://github.com/tobi/qmd",
    ),
    Dependency(
        name="rtk",
        command=["rtk", "--version"],
        source_type="github",
        source_value="rtk-ai/rtk",
        update_hint="brew upgrade rtk  # or re-run RTK installer",
    ),
    Dependency(
        name="gh-axi",
        command=["gh-axi", "--version"],
        source_type="npm",
        source_value="gh-axi",
        update_hint="npm install -g gh-axi chrome-devtools-axi",
    ),
    Dependency(
        name="chrome-devtools-axi",
        command=["chrome-devtools-axi", "--version"],
        source_type="npm",
        source_value="chrome-devtools-axi",
        update_hint="npm install -g gh-axi chrome-devtools-axi",
    ),
)

SEMVER_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def parse_semver(text: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def semver_to_str(version: tuple[int, int, int] | None, fallback: str = "") -> str:
    if version is None:
        return fallback
    return ".".join(str(part) for part in version)


def fetch_json(url: str, timeout_seconds: int = 5) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "token-reduce-dependency-health"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def latest_npm_version(package: str) -> str:
    payload = fetch_json(f"https://registry.npmjs.org/{package}/latest")
    if isinstance(payload, dict):
        value = payload.get("version")
        if isinstance(value, str):
            return value.strip()
    return ""


def latest_github_version(repo: str) -> str:
    latest_release = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    if isinstance(latest_release, dict):
        tag_name = latest_release.get("tag_name")
        if isinstance(tag_name, str) and tag_name.strip():
            return tag_name.strip()

    tags = fetch_json(f"https://api.github.com/repos/{repo}/tags?per_page=1")
    if isinstance(tags, list) and tags:
        first = tags[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str):
                return name.strip()
    return ""


def read_local_version(dep: Dependency) -> tuple[bool, str]:
    if shutil.which(dep.command[0]) is None:
        return False, ""
    code, out, err = run(dep.command)
    text = out or err
    if dep.name == "qmd" and text.startswith("Usage:"):
        return True, "installed (version unavailable)"
    if "\n" in text:
        text = text.splitlines()[0].strip()
    if code != 0 and not text:
        return True, ""
    return True, text


def latest_version(dep: Dependency) -> str:
    if dep.source_type == "npm":
        return latest_npm_version(dep.source_value)
    if dep.source_type == "github":
        return latest_github_version(dep.source_value)
    return ""


def dependency_status(dep: Dependency) -> dict[str, Any]:
    installed, local_raw = read_local_version(dep)
    latest_raw = latest_version(dep)
    local_semver = parse_semver(local_raw)
    latest_semver = parse_semver(latest_raw)

    state = "unknown"
    if not installed:
        state = "missing"
    elif latest_semver is None or local_semver is None:
        state = "unknown"
    elif local_semver < latest_semver:
        state = "outdated"
    else:
        state = "up_to_date"

    return {
        "name": dep.name,
        "installed": installed,
        "state": state,
        "local_version_raw": local_raw,
        "local_version": semver_to_str(local_semver, fallback=local_raw),
        "latest_version_raw": latest_raw,
        "latest_version": semver_to_str(latest_semver, fallback=latest_raw),
        "source": {"type": dep.source_type, "value": dep.source_value},
        "update_hint": dep.update_hint,
    }


def needs_action(state: str) -> bool:
    return state in {"missing", "outdated"}


def apply_updates(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    qmd_status = next((item for item in statuses if item["name"] == "qmd"), None)
    if qmd_status and needs_action(str(qmd_status.get("state"))):
        if shutil.which("bun"):
            code, out, err = run(["bun", "install", "-g", "https://github.com/tobi/qmd"])
            actions.append(
                {
                    "target": "qmd",
                    "command": "bun install -g https://github.com/tobi/qmd",
                    "status": "updated" if code == 0 else "failed",
                    "detail": out or err,
                }
            )
        else:
            actions.append(
                {
                    "target": "qmd",
                    "command": "bun install -g https://github.com/tobi/qmd",
                    "status": "skipped",
                    "detail": "bun not installed",
                }
            )

    rtk_status = next((item for item in statuses if item["name"] == "rtk"), None)
    if rtk_status and needs_action(str(rtk_status.get("state"))):
        if shutil.which("brew"):
            cmd = ["brew", "upgrade", "rtk"]
            code, out, err = run(cmd)
            actions.append(
                {
                    "target": "rtk",
                    "command": "brew upgrade rtk",
                    "status": "updated" if code == 0 else "failed",
                    "detail": out or err,
                }
            )
        else:
            cmd = ["bash", "-lc", "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh"]
            code, out, err = run(cmd)
            actions.append(
                {
                    "target": "rtk",
                    "command": "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh",
                    "status": "updated" if code == 0 else "failed",
                    "detail": out or err,
                }
            )

    needs_axi_update = any(
        item["name"] in {"gh-axi", "chrome-devtools-axi"} and needs_action(str(item.get("state")))
        for item in statuses
    )
    if needs_axi_update:
        if shutil.which("npm"):
            code, out, err = run(["npm", "install", "-g", "gh-axi", "chrome-devtools-axi"])
            actions.append(
                {
                    "target": "axi_companions",
                    "command": "npm install -g gh-axi chrome-devtools-axi",
                    "status": "updated" if code == 0 else "failed",
                    "detail": out or err,
                }
            )
        else:
            actions.append(
                {
                    "target": "axi_companions",
                    "command": "npm install -g gh-axi chrome-devtools-axi",
                    "status": "skipped",
                    "detail": "npm not installed",
                }
            )
    return actions


def print_human(statuses: list[dict[str, Any]], actions: list[dict[str, Any]]) -> None:
    print("dependency health:")
    for status in statuses:
        latest = status.get("latest_version") or "unknown"
        local = status.get("local_version") or "missing"
        print(f"- {status['name']}: {status['state']} (local={local}, latest={latest})")
        if status["state"] in {"missing", "outdated"}:
            print(f"  update: {status['update_hint']}")
    if actions:
        print("")
        print("update actions:")
        for action in actions:
            print(f"- {action['target']}: {action['status']} ({action['command']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--apply", action="store_true", help="Attempt dependency updates")
    args = parser.parse_args()

    statuses = [dependency_status(dep) for dep in DEPENDENCIES]
    actions: list[dict[str, Any]] = []
    if args.apply:
        actions = apply_updates(statuses)
        statuses = [dependency_status(dep) for dep in DEPENDENCIES]

    payload = {
        "dependencies": statuses,
        "actions": actions,
        "summary": {
            "up_to_date": sum(1 for item in statuses if item["state"] == "up_to_date"),
            "outdated": sum(1 for item in statuses if item["state"] == "outdated"),
            "missing": sum(1 for item in statuses if item["state"] == "missing"),
            "unknown": sum(1 for item in statuses if item["state"] == "unknown"),
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_human(statuses, actions)
        print("")
        print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
