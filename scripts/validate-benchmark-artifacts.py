#!/usr/bin/env python3
"""Validate benchmark artifact freshness and README token-table sync."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from token_reduce_config import load_config


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_artifact_freshness(path: Path, max_age_days: int) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{path}: missing benchmark artifact"]
    payload = load_json(path)
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str):
        return [f"{path}: missing generated_at timestamp"]
    timestamp = parse_timestamp(generated_at)
    if timestamp is None:
        return [f"{path}: invalid generated_at timestamp: {generated_at}"]
    now = datetime.now(timezone.utc)
    age_days = (now - timestamp.astimezone(timezone.utc)).total_seconds() / 86400
    if age_days > max_age_days:
        errors.append(
            f"{path}: stale benchmark artifact ({age_days:.1f} days old, max {max_age_days} days)"
        )
    return errors


def validate_readme_token_rows(readme: str, artifact_path: Path) -> list[str]:
    payload = load_json(artifact_path)
    rows = payload.get("benchmarks", [])
    if not isinstance(rows, list):
        return [f"{artifact_path}: benchmarks must be a list"]

    errors: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        tokens = item.get("tokens")
        if not isinstance(name, str) or not isinstance(tokens, int):
            continue
        row_prefix = f"| `{name}` | `{tokens}` |"
        if row_prefix not in readme:
            errors.append(
                f"README.md: benchmark row missing or stale for `{name}` tokens `{tokens}` from {artifact_path.name}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(repo_root()))
    parser.add_argument("--max-age-days", type=int)
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    config = load_config()
    configured_max_age = int(config.get("benchmark", {}).get("max_age_days", 14) or 14)
    max_age_days = args.max_age_days if args.max_age_days is not None else configured_max_age

    local_path = root / "references" / "benchmarks" / "local-benchmark.json"
    composite_path = root / "references" / "benchmarks" / "composite-benchmark.json"
    readme_path = root / "README.md"

    errors: list[str] = []
    errors.extend(validate_artifact_freshness(local_path, max_age_days))
    errors.extend(validate_artifact_freshness(composite_path, max_age_days))

    if not readme_path.exists():
        errors.append("README.md: missing")
    else:
        readme = readme_path.read_text(encoding="utf-8")
        errors.extend(validate_readme_token_rows(readme, local_path))
        errors.extend(validate_readme_token_rows(readme, composite_path))

    if errors:
        for error in errors:
            print(error)
        return 1

    print("benchmark artifact validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
