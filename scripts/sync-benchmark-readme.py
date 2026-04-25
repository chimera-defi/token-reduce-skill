#!/usr/bin/env python3
"""Sync README benchmark token cells with benchmark artifacts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sync_rows(readme_text: str, artifact_path: Path) -> tuple[str, int]:
    payload = load_json(artifact_path)
    rows = payload.get("benchmarks", [])
    if not isinstance(rows, list):
        return readme_text, 0

    updates = 0
    text = readme_text
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        tokens = row.get("tokens")
        savings_pct = row.get("savings_vs_broad_pct")
        if not isinstance(name, str) or not isinstance(tokens, int):
            continue

        # Sync token count column
        token_pattern = re.compile(rf"^\| `{re.escape(name)}` \| `\d+` \|", re.MULTILINE)
        token_replacement = f"| `{name}` | `{tokens}` |"
        text, count = token_pattern.subn(token_replacement, text, count=1)
        updates += count

        # Sync savings percentage column (e.g. "70.8% saved" or "baseline")
        if isinstance(savings_pct, (int, float)) and savings_pct > 0.0:
            savings_str = f"{round(float(savings_pct), 1)}%"
            savings_pattern = re.compile(
                rf"(^\| `{re.escape(name)}` \| `\d+` \| )`[\d.]+%` saved",
                re.MULTILINE,
            )
            savings_replacement = rf"\g<1>`{savings_str}` saved"
            new_text, scount = savings_pattern.subn(savings_replacement, text, count=1)
            if scount:
                text = new_text
                updates += scount

    return text, updates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    readme_path = root / "README.md"
    if not readme_path.exists():
        raise SystemExit("README.md not found")

    artifact_paths = [
        root / "references" / "benchmarks" / "local-benchmark.json",
        root / "references" / "benchmarks" / "composite-benchmark.json",
    ]
    missing = [path for path in artifact_paths if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing benchmark artifacts: {missing_text}")

    readme = readme_path.read_text(encoding="utf-8")
    updated = readme
    total_updates = 0
    for artifact_path in artifact_paths:
        updated, count = sync_rows(updated, artifact_path)
        total_updates += count

    if updated != readme:
        readme_path.write_text(updated, encoding="utf-8")

    print(
        json.dumps(
            {
                "readme": str(readme_path),
                "updated_rows": total_updates,
                "artifacts": [str(path) for path in artifact_paths],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
