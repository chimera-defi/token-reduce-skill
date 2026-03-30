#!/usr/bin/env python3
"""
Quick validation script for the token-reduce skill.
Thin wrapper around validate_skill_package.py using the Anthropic skill-creator interface.

Usage: uv run scripts/quick_validate.py <skill_directory>
       uv run --with pyyaml scripts/quick_validate.py .
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml required: uv run --with pyyaml scripts/quick_validate.py <path>")
    sys.exit(1)

ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}


def validate_skill(skill_path: str) -> tuple[bool, str]:
    root = Path(skill_path).resolve()

    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text()
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        return False, f"Invalid YAML: {e}"

    if not isinstance(fm, dict):
        return False, "Frontmatter must be a YAML dict"

    unexpected = set(fm.keys()) - ALLOWED_FRONTMATTER_KEYS
    if unexpected:
        return False, f"Unexpected frontmatter keys: {', '.join(sorted(unexpected))}"

    if "name" not in fm:
        return False, "Missing 'name' in frontmatter"
    if "description" not in fm:
        return False, "Missing 'description' in frontmatter"

    name = str(fm["name"]).strip()
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, f"Name '{name}' must be kebab-case"
    if len(name) > 64:
        return False, f"Name too long ({len(name)} chars, max 64)"

    desc = str(fm["description"]).strip()
    if "<" in desc or ">" in desc:
        return False, "Description cannot contain angle brackets"
    if len(desc) > 1024:
        return False, f"Description too long ({len(desc)} chars, max 1024)"

    # Check evals exist
    evals_path = root / "evals" / "evals.json"
    if not evals_path.exists():
        return False, "evals/evals.json not found — add test cases"

    return True, "skill package validation passed"


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    ok, msg = validate_skill(path)
    print(msg)
    sys.exit(0 if ok else 1)
