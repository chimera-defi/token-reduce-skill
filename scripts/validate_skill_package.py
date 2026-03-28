#!/usr/bin/env python3
"""Validate local skill packaging against a lightweight JSM-style shape."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_FRONTMATTER = ("name", "license", "description")
REQUIRED_METADATA_FIELDS = ("author", "category")
REQUIRED_SECTIONS = ("# Token Reduction Skill", "## Description", "## Triggers")


def repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    try:
        root = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return script_dir.parents[1]
    return Path(root)


def parse_frontmatter(text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter")
    return match.group(1)


def validate(skill_path: Path, openai_yaml: Path) -> list[str]:
    errors: list[str] = []
    text = skill_path.read_text(encoding="utf-8")
    try:
        frontmatter = parse_frontmatter(text)
    except ValueError as exc:
        return [f"SKILL.md: {exc}"]

    for field in REQUIRED_FRONTMATTER:
        if not re.search(rf"(?m)^{re.escape(field)}:", frontmatter):
            errors.append(f"SKILL.md: missing frontmatter field `{field}`")

    metadata_match = re.search(r"(?ms)^metadata:\n((?:[ \t]+.+\n?)*)", frontmatter)
    metadata_block = metadata_match.group(1) if metadata_match else ""
    for field in REQUIRED_METADATA_FIELDS:
        if not re.search(rf"(?m)^[ \t]+{re.escape(field)}:", metadata_block):
            errors.append(f"SKILL.md: missing metadata field `metadata.{field}`")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"SKILL.md: missing required section `{section}`")

    if "## Trigger\n" in text:
        errors.append("SKILL.md: use `## Triggers` instead of `## Trigger` for JSM-style compatibility")

    if not openai_yaml.exists():
        errors.append("agents/openai.yaml: missing UI metadata file")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(repo_root()))
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    errors = validate(root / "SKILL.md", root / "agents" / "openai.yaml")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("skill package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
