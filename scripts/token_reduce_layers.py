#!/usr/bin/env python3
"""Session policy and read-only status. Never edits host integrations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import urllib.request

from token_reduce_config import DEFAULT_CONFIG, config_path, layer_mode, load_config


CONTROLS = {
    "rtk": "run argv wrapper; existing global rewrite hooks are external",
    "search_qmd": "search backend gate; off uses existing rg fallback",
    "memory": "semantic memory hints; no memory reads/writes performed",
    "headroom_compress": "agent MCP action policy; existing proxy is external",
    "headroom_retrieve": "agent MCP action policy; existing proxy is external",
    "mcp_trim": "approval-only recommendation; server settings are external",
    "context_audit": "on-load report policy; auto preserves legacy no report",
}


def command_json(argv: list[str]) -> dict:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        if proc.returncode:
            return {"available": False, "reason": "command failed", "exit_code": proc.returncode}
        value = json.loads(proc.stdout)
        return value if isinstance(value, dict) else {"available": False, "reason": "unexpected format"}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"available": False, "reason": "unavailable or invalid response"}


def headroom_stats() -> dict:
    # Fixed loopback endpoint: no credentials, remote probes, or setup mutations.
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/stats", timeout=2) as response:
            data = json.load(response)
        summary = data.get("summary", {})
        return {"available": True, "source": "loopback /stats", "summary": summary}
    except (OSError, ValueError):
        return {"available": False, "reason": "loopback stats unavailable"}


def status(events_file: Path | None = None) -> dict:
    cfg = load_config()
    rtk = command_json(["rtk", "gain", "--format", "json"]) if shutil.which("rtk") else {"available": False}
    hr = headroom_stats()
    summary = rtk.get("summary", {})
    compression = hr.get("summary", {}).get("compression", {})
    mcp = hr.get("summary", {}).get("mcp", {})
    rows = {}
    for name in CONTROLS:
        override = f"TOKEN_REDUCE_LAYER_{name.upper()}"
        rows[name] = {"mode": layer_mode(name, cfg),
                      "source": "environment" if override in os.environ else "config/default",
                      "control": CONTROLS[name], "tokens_saved": None, "measurement": "unmeasured"}
    rows["rtk"].update(invocations=summary.get("total_commands"), tokens_saved=summary.get("total_saved"),
                       measurement="RTK reported token estimates; host-wide, not skill-attributed")
    rows["headroom_compress"].update(invocations=compression.get("requests_compressed"),
                                     tokens_saved=compression.get("total_tokens_removed"),
                                     measurement="proxy reported; lifetime of running process; not skill-attributed",
                                     mcp_invocations=mcp.get("compressions"))
    rows["headroom_retrieve"].update(invocations=mcp.get("retrievals"))
    rows["mcp_trim"].update(tokens_saved=compression.get("tool_schema_tokens_saved"),
                           measurement="proxy schema compaction reported; not disabled-server savings")
    if events_file:
        count, last = 0, None
        try:
            with events_file.open() as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("event") == "helper_invocation" and event.get("meta", {}).get("context", "runtime") == "runtime":
                        count += 1
                        timestamp = event.get("timestamp")
                        if isinstance(timestamp, str):
                            last = max(last or timestamp, timestamp)
            rows["search_qmd"].update(helper_invocations=count, last_used=last,
                                     measurement="runtime helper events; savings unmeasured, not all calls use QMD")
        except OSError:
            rows["search_qmd"]["events_available"] = False
    return {"config_path": str(config_path()), "layers": rows,
            "rtk_available": bool(summary), "headroom_available": hr.get("available", False),
            "note": "auto inherits legacy behavior; off controls only the stated scope. Unknown savings stay null; counters overlap and must not be summed."}


def run_command(argv: list[str]) -> int:
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise ValueError("run requires an argv command after --")
    if layer_mode("rtk") == "on":
        if not shutil.which("rtk"):
            raise ValueError("RTK enabled but not installed; no auto-install")
        rewritten = subprocess.run(["rtk", "rewrite", shlex.join(argv)], capture_output=True, text=True, timeout=5)
        if rewritten.returncode == 0 and rewritten.stdout.strip():
            candidate = shlex.split(rewritten.stdout)
            # This API accepts argv, never shell programs or command substitution.
            if candidate and candidate[0] == "rtk":
                argv = candidate
        elif rewritten.returncode != 1:
            raise ValueError("RTK rewrite failed")
    return subprocess.run(argv, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    mode = sub.add_parser("mode")
    mode.add_argument("layer", choices=list(DEFAULT_CONFIG["layers"]))
    st = sub.add_parser("status")
    st.add_argument("--events-file", type=Path)
    run = sub.add_parser("run")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    action = sub.add_parser("layer-action")
    action.add_argument("layer", choices=["headroom_compress", "headroom_retrieve", "mcp_trim"])
    args = parser.parse_args()
    try:
        if args.command == "mode":
            print(layer_mode(args.layer))
        elif args.command == "run":
            return run_command(args.argv)
        elif args.command == "layer-action":
            mode = layer_mode(args.layer)
            print(json.dumps({"layer": args.layer, "mode": mode, "allowed": mode != "off",
                              "control": CONTROLS[args.layer], "requires_operator_approval": args.layer == "mcp_trim"}))
        else:
            print(json.dumps(status(args.events_file), indent=2))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
