#!/usr/bin/env python3
"""Check for token-reduce updates and optionally apply safe fast-forward updates."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from token_reduce_config import load_config


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def branch(root: Path) -> str:
    _, out, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    return out or "unknown"


def upstream(root: Path) -> str:
    code, out, _ = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root)
    return out if code == 0 else ""


def dirty(root: Path) -> bool:
    _, out, _ = run(["git", "status", "--porcelain"], root)
    return bool(out.strip())


def ahead_behind(root: Path, upstream_ref: str) -> tuple[int, int]:
    if not upstream_ref:
        return 0, 0
    code, out, _ = run(["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"], root)
    if code != 0 or not out:
        return 0, 0
    parts = out.split()
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notify", action="store_true", help="Print human-readable update message")
    parser.add_argument("--auto-update", action="store_true", help="Attempt safe ff-only update now")
    parser.add_argument("--no-fetch", action="store_true", help="Skip git fetch before checking")
    args = parser.parse_args()

    root = repo_root()
    config = load_config()
    updates_cfg: dict[str, Any] = config.get("updates", {})
    auto_update_enabled = bool(updates_cfg.get("auto_update", False))

    if not args.no_fetch:
        run(["git", "fetch", "origin", "--prune"], root)

    current_branch = branch(root)
    upstream_ref = upstream(root)
    is_dirty = dirty(root)
    ahead, behind = ahead_behind(root, upstream_ref)

    attempted_auto_update = args.auto_update or auto_update_enabled
    update_action = "none"
    update_detail = ""
    if attempted_auto_update:
        if not upstream_ref:
            update_action = "skipped"
            update_detail = "no upstream configured"
        elif is_dirty:
            update_action = "skipped"
            update_detail = "working tree is dirty"
        elif ahead > 0:
            update_action = "skipped"
            update_detail = "branch has local commits ahead of upstream"
        elif behind <= 0:
            update_action = "skipped"
            update_detail = "already up to date"
        else:
            code, out, err = run(["git", "pull", "--ff-only"], root)
            update_action = "updated" if code == 0 else "failed"
            update_detail = out or err
            if code == 0:
                ahead, behind = ahead_behind(root, upstream(root))

    payload = {
        "repo_root": str(root),
        "branch": current_branch,
        "upstream": upstream_ref,
        "ahead": ahead,
        "behind": behind,
        "dirty": is_dirty,
        "update_available": behind > 0,
        "auto_update_enabled": auto_update_enabled,
        "auto_update_attempted": attempted_auto_update,
        "auto_update_action": update_action,
        "auto_update_detail": update_detail,
    }

    if args.notify:
        if payload["update_available"]:
            print(f"update available: behind by {behind} commit(s) on {current_branch}")
            print("run: ./scripts/token-reduce-manage.sh auto-update")
        else:
            print("token-reduce is up to date.")

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
