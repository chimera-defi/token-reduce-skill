#!/usr/bin/env python3
"""Plan + delegate execution through Kimi with fallback and telemetry."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import shutil
import re
from pathlib import Path


def script_root() -> Path:
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    return script_root().parent


def current_repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return Path.cwd()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def call(cmd: list[str], timeout: int) -> tuple[int, str, str, float]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return proc.returncode, proc.stdout, proc.stderr, latency_ms
    except subprocess.TimeoutExpired:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return 124, "", f"timeout after {timeout}s", latency_ms


def output_is_valid(text: str, required_sections: list[str]) -> bool:
    if not text.strip():
        return False
    lower = text.lower()
    for section in required_sections:
        section = section.strip()
        if not section:
            continue
        heading = re.compile(rf"(?im)^#{1,6}\s*{re.escape(section)}\s*$")
        if not heading.search(text) and section.lower() not in lower:
            return False
    return True


def build_envelope(task: str, context_file: str | None) -> dict:
    cmd = [
        str(script_root() / "plan_prompt.py"),
        "--task",
        task,
    ]
    if context_file:
        cmd += ["--context-file", context_file]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--context-file")
    parser.add_argument("--task-class")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-envelope", action="store_true")
    args = parser.parse_args()

    repo_root = current_repo_root()
    skill = skill_root()
    config = load_json(skill / "config" / "kimi-delegate.json")
    routing = load_json(skill / "config" / "routing.json")

    envelope = build_envelope(args.task, args.context_file)
    if args.task_class:
        envelope["task_class"] = args.task_class

    task_class = envelope.get("task_class", "default")
    route = routing.get("task_classes", {}).get(task_class, routing.get("default", {}))
    timeout_seconds = int(route.get("timeout_seconds", config.get("timeout_seconds", 120)))
    model = str(route.get("model", config.get("model", "k2p6")))

    if args.print_envelope or args.dry_run:
        print(json.dumps(envelope, indent=2))
        if args.dry_run:
            return 0

    envelope_text = json.dumps(envelope, indent=2)
    prompt = (
        "Execute delegated envelope strictly. "
        "Return concise output with sections: Result, Evidence, Next steps.\n\n"
        + envelope_text
    )

    if shutil.which("pi-kimi-subagent") is not None:
        cmd = ["pi-kimi-subagent", prompt]
        primary_model_used = "pi-kimi-subagent:default"
    else:
        if shutil.which("pi") is None:
            print("error: neither `pi-kimi-subagent` nor `pi` was found", flush=True)
            return 127
        cmd = [
            "pi",
            "--provider",
            str(config.get("provider", "kimi-coding")),
            "--model",
            model,
            "--thinking",
            str(config.get("thinking", "medium")),
            "--print",
            prompt,
        ]
        primary_model_used = f"{config.get('provider', 'kimi-coding')}:{model}"

    rc, out, err, latency_ms = call(cmd, timeout=timeout_seconds)

    fallback_used = False
    fallback_reason = ""
    status = "ok"
    required_sections = list(envelope.get("output_schema", {}).get("required_sections", []))
    schema_valid = output_is_valid(out, required_sections)
    max_retries = int(route.get("retry", config.get("max_retries", 1)))

    retry_count = 0
    while rc == 0 and not schema_valid and retry_count < max_retries:
        retry_count += 1
        rc, out, err, extra_latency_ms = call(cmd, timeout=timeout_seconds)
        latency_ms += extra_latency_ms
        schema_valid = output_is_valid(out, required_sections)

    if rc != 0 or not schema_valid:
        fallback_used = True
        if rc == 124:
            fallback_reason = "timeout"
        elif rc != 0:
            fallback_reason = "provider_error"
        else:
            fallback_reason = "schema_invalid"

        envelope_path = repo_root / "artifacts" / "kimi-delegate" / "last-envelope.json"
        envelope_path.parent.mkdir(parents=True, exist_ok=True)
        envelope_path.write_text(envelope_text + "\n", encoding="utf-8")

        fallback_cmd = [
            str(script_root() / "fallback.py"),
            "--envelope-file",
            str(envelope_path),
            "--fallback-engine",
            str(config.get("fallback_engine", "codex")),
            "--model",
            str(config.get("fallback_model", "gpt-5.3-codex")),
            "--provider",
            str(config.get("fallback_provider", "openai")),
        ]
        f_rc, f_out, f_err, f_latency_ms = call(fallback_cmd, timeout=max(timeout_seconds, 180))
        latency_ms += f_latency_ms
        rc = f_rc
        out = f_out
        err = f_err

    if rc != 0:
        status = "error"

    parent_tokens = int(envelope.get("metrics", {}).get("parent_context_tokens", 0))
    delegate_input_tokens = estimate_tokens(prompt)
    delegate_output_tokens = estimate_tokens(out)
    saved = max(0, parent_tokens - delegate_output_tokens)

    telemetry_cmd = [
        str(script_root() / "kimi_delegate_telemetry.py"),
        "record",
        "--status",
        status,
        "--task-class",
        str(task_class),
        "--model-used",
        primary_model_used if not fallback_used else f"fallback:{config.get('fallback_engine')}:{config.get('fallback_model')}",
        "--parent-context-tokens",
        str(parent_tokens),
        "--delegate-input-tokens",
        str(delegate_input_tokens),
        "--delegate-output-tokens",
        str(delegate_output_tokens),
        "--estimated-tokens-saved",
        str(saved),
        "--latency-ms",
        str(round(latency_ms, 2)),
    ]

    if fallback_used:
        telemetry_cmd += ["--fallback-used", "--fallback-reason", fallback_reason]

    subprocess.run(telemetry_cmd, capture_output=True, text=True, check=False)

    if rc != 0:
        if err:
            print(err)
        return rc

    print(out.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
