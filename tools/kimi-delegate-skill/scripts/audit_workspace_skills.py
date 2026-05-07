#!/usr/bin/env python3
"""Audit kimi-delegate links and doc adoption across repos."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DOC_FILES = ("AGENTS.md", "CLAUDE.md", "README.md")


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def iter_repos(root: Path) -> list[Path]:
    return [p for p in sorted(root.iterdir()) if p.is_dir() and is_repo(p)]


def has_doc_block(repo: Path) -> tuple[bool, list[str]]:
    hits: list[str] = []
    for filename in DOC_FILES:
        path = repo / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "kimi-delegate" in text:
            hits.append(filename)
    return bool(hits), hits


def audit(root: Path, skill_source: Path) -> dict:
    rows = []
    for repo in iter_repos(root):
        skill_link = repo / "skills" / "kimi-delegate"
        linked = skill_link.exists() and (skill_link / "SKILL.md").exists()
        mode = "symlink" if skill_link.is_symlink() else "directory" if skill_link.exists() else "missing"
        resolved = str(skill_link.resolve()) if skill_link.exists() else ""
        doc_present, doc_hits = has_doc_block(repo)
        rows.append(
            {
                "repo": repo.name,
                "skill_installed": linked,
                "install_mode": mode,
                "skill_source_path": resolved,
                "source_match": bool(resolved and Path(resolved) == skill_source.resolve()),
                "docs_with_kimi_delegate": doc_hits,
                "docs_compliant": doc_present,
                "fully_compliant": linked and doc_present,
            }
        )

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "skill_source": str(skill_source.resolve()),
        "repo_count": len(rows),
        "fully_compliant": sum(1 for r in rows if r["fully_compliant"]),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default="/root/.openclaw/workspace/dev")
    parser.add_argument("--skill-source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    payload = audit(Path(args.workspace_root).resolve(), Path(args.skill_source).resolve())
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
