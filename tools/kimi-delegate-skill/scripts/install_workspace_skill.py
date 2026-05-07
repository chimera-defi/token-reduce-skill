#!/usr/bin/env python3
"""Install kimi-delegate into workspace repos and inject routing instructions."""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


BLOCK_START = "<!-- kimi-delegate:begin -->"
BLOCK_END = "<!-- kimi-delegate:end -->"
KIMI_BLOCK = f"""{BLOCK_START}
## Kimi Delegate Routing

- For bounded side tasks (search/summarize/draft/review), prefer `./skills/kimi-delegate/scripts/delegate.py --task \"...\"`.
- Always produce an envelope first with `./skills/kimi-delegate/scripts/plan_prompt.py --task \"...\"`.
- Keep delegation scoped and include acceptance criteria.
- If Kimi fails, keep fallback enabled and inspect telemetry (`scripts/kimi_delegate_telemetry.py summary --days 14`).
{BLOCK_END}
"""
BLOCK_RE = re.compile(rf"{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}", re.DOTALL)


@dataclass
class RepoInstallResult:
    repo: str
    skill_link: str
    doc_file: str
    doc_action: str
    changed: bool


def is_repo_root(path: Path) -> bool:
    return (path / ".git").exists()


def iter_repos(workspace_root: Path) -> list[Path]:
    return [child for child in sorted(workspace_root.iterdir()) if child.is_dir() and is_repo_root(child)]


def ensure_skill_link(repo: Path, skill_source: Path, force_relink: bool, dry_run: bool) -> tuple[str, bool]:
    skills_dir = repo / "skills"
    target = skills_dir / "kimi-delegate"

    if target.is_symlink() and target.exists() and target.resolve() == skill_source.resolve():
        return "already-linked", False

    if target.exists() or target.is_symlink():
        if not force_relink:
            return "conflict-existing-path", False
        if not dry_run:
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
            else:
                for p in sorted(target.rglob("*"), reverse=True):
                    if p.is_file() or p.is_symlink():
                        p.unlink(missing_ok=True)
                    elif p.is_dir():
                        p.rmdir()
                target.rmdir()

    if not dry_run:
        skills_dir.mkdir(parents=True, exist_ok=True)
        target.symlink_to(skill_source)
    return "linked", True


def target_doc(repo: Path) -> Path:
    agents = repo / "AGENTS.md"
    if agents.exists():
        return agents
    claude = repo / "CLAUDE.md"
    if claude.exists():
        return claude
    return agents


def ensure_doc_block(path: Path, dry_run: bool) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    block = KIMI_BLOCK.strip()

    if BLOCK_RE.search(text):
        updated = BLOCK_RE.sub(block, text)
        changed = updated != text
        if changed and not dry_run:
            path.write_text(updated.rstrip() + "\n", encoding="utf-8")
        return "block-replaced", changed

    if text.strip():
        updated = text.rstrip() + "\n\n" + block + "\n"
        action = "block-added"
    else:
        updated = "# Agent Instructions\n\n" + block + "\n"
        action = "file-created"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action, True


def install_workspace(workspace_root: Path, skill_source: Path, include_self: bool, force_relink: bool, dry_run: bool) -> dict:
    rows: list[RepoInstallResult] = []
    source = skill_source.resolve()

    for repo in iter_repos(workspace_root):
        if not include_self and repo.resolve() == source:
            continue
        link_action, link_changed = ensure_skill_link(repo, source, force_relink, dry_run)
        doc = target_doc(repo)
        doc_action, doc_changed = ensure_doc_block(doc, dry_run)
        rows.append(
            RepoInstallResult(
                repo=repo.name,
                skill_link=link_action,
                doc_file=doc.name,
                doc_action=doc_action,
                changed=bool(link_changed or doc_changed),
            )
        )

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "skill_source": str(source),
        "repo_count": len(rows),
        "repos_changed": sum(1 for row in rows if row.changed),
        "dry_run": dry_run,
        "results": [asdict(row) for row in rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default=os.environ.get("KIMI_DELEGATE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"))
    parser.add_argument("--skill-source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--force-relink", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = install_workspace(
        workspace_root=Path(args.workspace_root).resolve(),
        skill_source=Path(args.skill_source).resolve(),
        include_self=args.include_self,
        force_relink=args.force_relink,
        dry_run=args.dry_run,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
