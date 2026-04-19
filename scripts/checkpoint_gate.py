#!/usr/bin/env python3
"""Run a consistent checkpoint suite and write auditable artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


CHECKPOINT_COMMANDS: list[tuple[str, list[str]]] = [
    ("release_gate", ["./scripts/token-reduce-manage.sh", "release-gate"]),
    ("validate", ["./scripts/token-reduce-manage.sh", "validate"]),
    ("test_adaptive", ["./scripts/token-reduce-manage.sh", "test-adaptive"]),
    ("measure_repo", ["./scripts/token-reduce-manage.sh", "measure"]),
    ("review_repo", ["./scripts/token-reduce-manage.sh", "review"]),
    ("measure_global", ["./scripts/token-reduce-manage.sh", "measure-global"]),
    ("review_global", ["./scripts/token-reduce-manage.sh", "review-global"]),
    ("workspace_audit", ["./scripts/token-reduce-manage.sh", "workspace-audit"]),
    ("telemetry_sync_dry_run", ["./scripts/token-reduce-manage.sh", "telemetry-sync", "--dry-run"]),
]


def tail_lines(text: str, max_lines: int = 20) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def run_step(name: str, command: list[str], cwd: Path) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "name": name,
        "command": command,
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        "status": "pass" if proc.returncode == 0 else "fail",
        "stdout_tail": tail_lines(proc.stdout or ""),
        "stderr_tail": tail_lines(proc.stderr or ""),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Checkpoint Gate",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Repo root: `{report['repo_root']}`",
        f"- Overall pass: `{str(report['overall_pass']).lower()}`",
        "",
        "| Step | Status | Exit | Duration (ms) |",
        "|---|---|---:|---:|",
    ]
    for step in report["steps"]:
        lines.append(
            f"| `{step['name']}` | `{step['status']}` | `{step['exit_code']}` | `{step['duration_ms']}` |"
        )

    failed = [step for step in report["steps"] if step["exit_code"] != 0]
    if failed:
        lines.extend(["", "## Failures"])
        for step in failed:
            lines.append("")
            lines.append(f"### `{step['name']}`")
            lines.append(f"- Command: `{' '.join(step['command'])}`")
            if step["stderr_tail"]:
                lines.append("- stderr (tail):")
                lines.append("```text")
                lines.append(step["stderr_tail"])
                lines.append("```")
            elif step["stdout_tail"]:
                lines.append("- stdout (tail):")
                lines.append("```text")
                lines.append(step["stdout_tail"])
                lines.append("```")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        default=".",
        help="repo root where checkpoint commands are executed",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/token-reduction",
        help="directory for checkpoint JSON/Markdown artifacts",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    stamp = timestamp.strftime("%Y-%m-%dT%H%M%SZ")
    json_path = output_dir / f"checkpoint-{stamp}.json"
    md_path = output_dir / f"checkpoint-{stamp}.md"

    steps = [run_step(name, command, repo_root) for name, command in CHECKPOINT_COMMANDS]
    overall_pass = all(step["exit_code"] == 0 for step in steps)

    report = {
        "generated_at": timestamp.isoformat(),
        "repo_root": str(repo_root),
        "overall_pass": overall_pass,
        "steps": steps,
        "artifacts": {
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
