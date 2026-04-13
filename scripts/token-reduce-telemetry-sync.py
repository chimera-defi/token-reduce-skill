#!/usr/bin/env python3
"""Aggregate opt-in telemetry and optionally upload anonymized summaries."""
from __future__ import annotations

import argparse
import hmac
import json
import hashlib
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_workspace_skills import build_payload as workspace_payload
from measure_token_reduction import measure
from token_reduce_config import load_config


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip() or "unknown"


def host_fingerprint() -> str:
    machine_id = Path("/etc/machine-id")
    seed = ""
    if machine_id.exists():
        seed = machine_id.read_text(encoding="utf-8", errors="ignore").strip()
    if not seed:
        seed = socket.gethostname()
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def payload_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    *,
    api_key: str = "",
    signing_secret: str = "",
) -> tuple[bool, str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-token-reduce-key"] = api_key
    if signing_secret:
        headers["x-token-reduce-signature"] = payload_signature(body, signing_secret)

    req = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return True, f"http {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)


def build_remote_payload(
    measured: dict[str, Any], workspace: dict[str, Any], commit_sha: str
) -> dict[str, Any]:
    efficiency = measured.get("telemetry", {}).get("efficiency", {})
    workspace_summary = workspace.get("summary", {})
    workspace_gaps = workspace.get("gaps", {})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host_id": host_fingerprint(),
        "tool": {
            "name": "token-reduce",
            "commit": commit_sha,
        },
        "metrics": {
            "session_count": measured.get("session_count", 0),
            "helper_sessions_pct": measured.get("adoption", {}).get("helper_sessions_pct", 0.0),
            "helper_sessions_pct_observed_discovery": measured.get("adoption", {}).get(
                "helper_sessions_pct_observed_discovery", 0.0
            ),
            "discovery_compliance_pct": measured.get("compliance", {}).get("discovery_compliance_pct", 0.0),
            "discovery_compliance_pct_observed": measured.get("compliance", {}).get(
                "discovery_compliance_pct_observed", 0.0
            ),
            "broad_scan_sessions": measured.get("compliance", {}).get("sessions_with_broad_scan_violation", 0),
            "caveman_command_pct": measured.get("adoption", {}).get("caveman_command_pct", 0.0),
            "axi_tool_sessions_pct": measured.get("adoption", {}).get("axi_tool_sessions_pct", 0.0),
            "telemetry_event_count_14d": measured.get("telemetry", {}).get("event_count", 0),
            "telemetry_excluded_event_count_14d": measured.get("telemetry", {}).get("excluded_event_count", 0),
            "helper_error_rate_pct": efficiency.get("helper_error_rate_pct", 0.0),
            "helper_failure_overhead_pct": efficiency.get("failure_overhead_pct", 0.0),
            "helper_rapid_repeat_calls": efficiency.get("rapid_repeat_calls", 0),
            "helper_error_recovery_retries": efficiency.get("error_recovery_retries", 0),
            "hook_error_count": efficiency.get("hook_error_count", 0),
            "pending_leak_count": efficiency.get("pending_leak_count", 0),
            "workspace": workspace_summary,
            "workspace_active_without_helper_usage_count": len(
                workspace_gaps.get("active_without_helper_usage", [])
            ),
            "workspace_missing_local_skill_count": len(workspace_gaps.get("missing_local_skill", [])),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Run even when telemetry.enabled=false")
    parser.add_argument("--dry-run", action="store_true", help="Do not POST even if endpoint is set")
    args = parser.parse_args()

    root = repo_root()
    config = load_config()
    telemetry_cfg = config.get("telemetry", {})
    enabled = bool(telemetry_cfg.get("enabled", False))
    endpoint = str(telemetry_cfg.get("endpoint", "") or "").strip()
    api_key = str(telemetry_cfg.get("api_key", "") or "").strip()
    signing_secret = str(telemetry_cfg.get("signing_secret", "") or "").strip()
    workspace_root = str(telemetry_cfg.get("workspace_root", "/root/.openclaw/workspace/dev"))
    workspace_days = int(telemetry_cfg.get("workspace_days", 14) or 14)
    workspace_include_source_repo = bool(telemetry_cfg.get("workspace_include_source_repo", False))
    timeout_seconds = int(telemetry_cfg.get("upload_timeout_seconds", 10) or 10)

    if not enabled and not args.force:
        print("telemetry disabled (enable via: token-reduce-manage settings set telemetry.enabled true)")
        return 0

    measured = measure("global", str(root))
    workspace = workspace_payload(
        Path(workspace_root).resolve(),
        workspace_days,
        workspace_include_source_repo,
    )
    commit_sha = git_head(root)
    remote_payload = build_remote_payload(measured, workspace, commit_sha)

    local_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "enabled": enabled,
            "endpoint_configured": bool(endpoint),
            "api_key_configured": bool(api_key),
            "signing_secret_configured": bool(signing_secret),
            "workspace_root": workspace_root,
            "workspace_days": workspace_days,
            "workspace_include_source_repo": workspace_include_source_repo,
        },
        "remote_payload": remote_payload,
        "global_measure_summary": {
            "session_count": measured.get("session_count", 0),
            "helper_sessions_pct": measured.get("adoption", {}).get("helper_sessions_pct", 0.0),
            "helper_sessions_pct_observed_discovery": measured.get("adoption", {}).get(
                "helper_sessions_pct_observed_discovery", 0.0
            ),
            "discovery_compliance_pct": measured.get("compliance", {}).get("discovery_compliance_pct", 0.0),
            "discovery_compliance_pct_observed": measured.get("compliance", {}).get(
                "discovery_compliance_pct_observed", 0.0
            ),
        },
    }

    output_dir = root / "artifacts" / "token-reduction"
    append_jsonl(output_dir / "telemetry-optin.jsonl", local_payload)
    snapshot_path = output_dir / f"telemetry-optin-{datetime.now().date()}.json"
    snapshot_path.write_text(json.dumps(local_payload, indent=2) + "\n", encoding="utf-8")

    upload_status = "skipped"
    if endpoint and enabled and not args.dry_run:
        ok, detail = post_json(
            endpoint,
            remote_payload,
            timeout_seconds,
            api_key=api_key,
            signing_secret=signing_secret,
        )
        upload_status = f"uploaded ({detail})" if ok else f"failed ({detail})"
    elif endpoint and args.dry_run:
        upload_status = "dry-run"

    print(
        json.dumps(
            {
                "enabled": enabled,
                "endpoint_configured": bool(endpoint),
                "upload_status": upload_status,
                "snapshot": str(snapshot_path),
                "summary": local_payload["global_measure_summary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
