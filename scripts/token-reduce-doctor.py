#!/usr/bin/env python3
"""Run a compact health pass for token-reduce tooling and configuration."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run(cmd: list[str], root: Path) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=root, check=False, capture_output=True, text=True)
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def parse_json_output(result: dict[str, Any]) -> dict[str, Any] | None:
    out = str(result.get("stdout", "")).strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-deps", action="store_true", help="Fail when dependency health is not clean")
    args = parser.parse_args()

    root = repo_root()

    skill_validation = run(["uv", "run", "scripts/validate_skill_package.py"], root)
    benchmark_validation = run(["uv", "run", "scripts/validate-benchmark-artifacts.py"], root)
    deps = run(["uv", "run", "scripts/token-reduce-dependency-health.py", "--json"], root)
    updates = run(["uv", "run", "scripts/token-reduce-update-check.py", "--no-fetch"], root)
    settings = run(["uv", "run", "scripts/token-reduce-settings.py", "show"], root)

    deps_json = parse_json_output(deps) or {}
    updates_json = parse_json_output(updates) or {}
    settings_json = parse_json_output(settings) or {}

    deps_summary = deps_json.get("summary", {}) if isinstance(deps_json, dict) else {}
    dep_outdated = int(deps_summary.get("outdated", 0) or 0)
    dep_missing = int(deps_summary.get("missing", 0) or 0)

    checks = {
        "skill_package": {"ok": skill_validation["exit_code"] == 0, **skill_validation},
        "benchmark_artifacts": {"ok": benchmark_validation["exit_code"] == 0, **benchmark_validation},
        "dependency_health": {
            "ok": deps["exit_code"] == 0 and dep_missing == 0 and (dep_outdated == 0 or not args.strict_deps),
            **deps,
            "summary": deps_summary,
        },
        "repo_update_status": {
            "ok": updates["exit_code"] == 0,
            **updates,
            "parsed": updates_json,
        },
        "settings": {
            "ok": settings["exit_code"] == 0,
            **settings,
            "parsed": settings_json,
        },
    }

    overall_ok = all(bool(item.get("ok", False)) for item in checks.values())
    payload = {
        "overall_ok": overall_ok,
        "strict_deps": args.strict_deps,
        "checks": checks,
    }
    print(json.dumps(payload, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
