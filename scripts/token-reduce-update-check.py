#!/usr/bin/env python3
"""Check for token-reduce updates and optionally apply safe fast-forward updates."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_workspace_skills import build_payload
from install_workspace_skill import install_workspace
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


def parse_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def run_workspace_sync(
    *,
    root: Path,
    workspace_root: Path,
    workspace_days: int,
    include_source_repo: bool,
    force_relink: bool,
    audit_output: str,
) -> dict[str, Any]:
    if not workspace_root.exists() or not workspace_root.is_dir():
        return {
            "action": "skipped",
            "ok": False,
            "detail": f"workspace root not found: {workspace_root}",
        }

    install_payload = install_workspace(
        workspace_root=workspace_root,
        skill_source=root,
        include_self=include_source_repo,
        dry_run=False,
        force_relink=force_relink,
    )
    audit_payload = build_payload(
        workspace_root=workspace_root,
        days=workspace_days,
        include_source_repo=include_source_repo,
    )

    if audit_output:
        output_path = Path(audit_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(audit_payload, indent=2) + "\n", encoding="utf-8")
    summary = audit_payload.get("summary", {}) if isinstance(audit_payload, dict) else {}
    gaps = audit_payload.get("gaps", {}) if isinstance(audit_payload, dict) else {}
    version_drift = int(summary.get("repos_with_skill_version_drift", 0) or 0)
    commit_drift = int(summary.get("repos_with_skill_commit_drift", 0) or 0)
    missing_local = len(gaps.get("missing_local_skill", [])) if isinstance(gaps, dict) else 0
    ok = version_drift == 0 and commit_drift == 0 and missing_local == 0
    return {
        "action": "completed",
        "ok": ok,
        "detail": "",
        "install": install_payload,
        "audit_summary": summary,
        "audit_expected_skill": audit_payload.get("expected_skill", {}),
        "audit_gaps": gaps,
        "audit_output": str(Path(audit_output).expanduser().resolve()) if audit_output else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notify", action="store_true", help="Print human-readable update message")
    parser.add_argument("--quiet-if-current", action="store_true", help="With --notify, suppress 'up to date' message (used by automated preambles)")
    parser.add_argument("--auto-update", action="store_true", help="Attempt safe ff-only update now")
    parser.add_argument("--no-fetch", action="store_true", help="Skip git fetch before checking")
    parser.add_argument("--workspace-sync", action="store_true", help="Also relink and audit sibling repos")
    parser.add_argument("--workspace-root", default="", help="Workspace root for sibling repo syncing")
    parser.add_argument("--workspace-days", type=int, default=None, help="Session window days for workspace audit")
    parser.add_argument(
        "--workspace-include-source-repo",
        action="store_true",
        help="Include the token-reduce source repo in workspace install/audit",
    )
    parser.add_argument(
        "--workspace-no-force-relink",
        action="store_true",
        help="Do not relink existing token-reduce dirs/symlinks in sibling repos",
    )
    parser.add_argument("--workspace-audit-output", default="", help="Optional path to write workspace audit JSON")
    args = parser.parse_args()

    root = repo_root()
    config = load_config()
    updates_cfg: dict[str, Any] = config.get("updates", {})
    telemetry_cfg: dict[str, Any] = config.get("telemetry", {})
    auto_update_enabled = bool(updates_cfg.get("auto_update", False))
    workspace_auto_update_enabled = bool(updates_cfg.get("workspace_auto_update", False))
    workspace_force_relink_default = bool(updates_cfg.get("workspace_force_relink", True))
    default_workspace_root = str(telemetry_cfg.get("workspace_root") or "/root/.openclaw/workspace/dev")
    default_workspace_days = parse_int(telemetry_cfg.get("workspace_days", 14), 14)
    default_include_source_repo = bool(telemetry_cfg.get("workspace_include_source_repo", False))

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

    workspace_sync_requested = args.workspace_sync or (workspace_auto_update_enabled and attempted_auto_update)
    workspace_root = Path(args.workspace_root or default_workspace_root).expanduser().resolve()
    workspace_days = args.workspace_days if args.workspace_days is not None else default_workspace_days
    include_source_repo = args.workspace_include_source_repo or default_include_source_repo
    force_relink = workspace_force_relink_default and not args.workspace_no_force_relink
    if not args.workspace_audit_output:
        date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        args.workspace_audit_output = str(
            root / "artifacts" / "token-reduction" / f"workspace-audit-{date_stamp}-auto-update.json"
        )
    workspace_payload: dict[str, Any] = {}
    if workspace_sync_requested:
        workspace_payload = run_workspace_sync(
            root=root,
            workspace_root=workspace_root,
            workspace_days=workspace_days,
            include_source_repo=include_source_repo,
            force_relink=force_relink,
            audit_output=args.workspace_audit_output,
        )

    payload = {
        "repo_root": str(root),
        "branch": current_branch,
        "upstream": upstream_ref,
        "ahead": ahead,
        "behind": behind,
        "dirty": is_dirty,
        "update_available": behind > 0,
        "auto_update_enabled": auto_update_enabled,
        "workspace_auto_update_enabled": workspace_auto_update_enabled,
        "auto_update_attempted": attempted_auto_update,
        "auto_update_action": update_action,
        "auto_update_detail": update_detail,
        "workspace_sync_requested": workspace_sync_requested,
        "workspace_sync": workspace_payload,
    }

    if args.notify:
        import sys as _sys
        if payload["update_available"]:
            print(f"[token-reduce] update available: {behind} commit(s) behind on {current_branch}", file=_sys.stderr)
            print("[token-reduce] run: ./scripts/token-reduce-manage.sh auto-update", file=_sys.stderr)
        elif not args.quiet_if_current:
            print("token-reduce is up to date.", file=_sys.stderr)
        if workspace_sync_requested:
            action = str(workspace_payload.get("action", "unknown"))
            if action == "completed":
                summary = workspace_payload.get("audit_summary", {})
                changed = int(workspace_payload.get("install", {}).get("repos_changed", 0) or 0)
                print(
                    "workspace sync completed: "
                    f"repos_changed={changed}, "
                    f"version_drift={int(summary.get('repos_with_skill_version_drift', 0) or 0)}, "
                    f"commit_drift={int(summary.get('repos_with_skill_commit_drift', 0) or 0)}",
                    file=_sys.stderr,
                )
            else:
                detail = workspace_payload.get("detail", "")
                print(f"workspace sync skipped: {detail or action}", file=_sys.stderr)

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
