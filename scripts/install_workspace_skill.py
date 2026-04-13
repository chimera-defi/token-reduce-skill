#!/usr/bin/env python3
"""Install token-reduce into sibling repos and enforce first-move guidance."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


BLOCK_START = "<!-- token-reduce:begin -->"
BLOCK_END = "<!-- token-reduce:end -->"
TOKEN_REDUCE_BLOCK = f"""{BLOCK_START}
## Token-Reduce Routing

- If file location is unknown, your first discovery command MUST be `./skills/token-reduce/scripts/token-reduce-paths.sh topic words`.
- Use the user’s literal nouns from the prompt in that first query (feature name, file stem, hook name, symbol).
- Use `./skills/token-reduce/scripts/token-reduce-snippet.sh topic words` only if one ranked excerpt is needed after the path list.
- Do not start repo discovery with `find .`, `ls -R`, `grep -R`, `rg --files .`, or broad `Glob` patterns.
- Use scoped `rg -g` and targeted reads only after helper output.
{BLOCK_END}
"""
BLOCK_RE = re.compile(rf"{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}", re.DOTALL)
HELPER_RE = re.compile(r"token-reduce-paths(?:\.sh)?", re.IGNORECASE)


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
    repos: list[Path] = []
    for child in sorted(workspace_root.iterdir()):
        if child.is_dir() and is_repo_root(child):
            repos.append(child)
    return repos


def canonical_skill_repo_root(skill_source: Path) -> Path:
    parts = skill_source.resolve().parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        if idx > 0:
            return Path(*parts[:idx])
    return skill_source.resolve()


def is_placeholder_skill_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    allowed_top = {".cursor"}
    top_entries = list(path.iterdir())
    if not top_entries:
        return True
    if {entry.name for entry in top_entries} - allowed_top:
        return False
    for entry in top_entries:
        if entry.is_file():
            return False
        for nested in entry.rglob("*"):
            if nested.is_file():
                return False
    return True


def backup_name() -> str:
    return f"token-reduce.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def ensure_skill_link(
    repo: Path, skill_source: Path, dry_run: bool, force_relink: bool
) -> tuple[str, bool]:
    skills_dir = repo / "skills"
    target = skills_dir / "token-reduce"
    changed = False

    if target.exists() or target.is_symlink():
        if target.is_symlink():
            try:
                resolved = target.resolve(strict=True)
            except OSError:
                resolved = None
            if resolved == skill_source.resolve():
                return "already-linked", changed
            if force_relink:
                if not dry_run:
                    target.unlink(missing_ok=True)
                    target.symlink_to(skill_source)
                changed = True
                return "relinked-existing-symlink", changed
            return "conflict-existing-symlink", changed
        if (target / "SKILL.md").exists():
            if force_relink:
                backup = skills_dir / backup_name()
                if backup.exists():
                    return "conflict-backup-exists", changed
                if not dry_run:
                    shutil.move(str(target), str(backup))
                    target.symlink_to(skill_source)
                changed = True
                return f"relinked-from-dir-backup:{backup.name}", changed
            return "already-present", changed
        if is_placeholder_skill_dir(target):
            if not dry_run:
                shutil.rmtree(target)
                target.symlink_to(skill_source)
            changed = True
            return "replaced-placeholder-dir", changed
        return "conflict-existing-path", changed

    if not dry_run:
        skills_dir.mkdir(parents=True, exist_ok=True)
        target.symlink_to(skill_source)
    changed = True
    return "linked", changed


def target_doc(repo: Path) -> Path:
    agents = repo / "AGENTS.md"
    if agents.exists():
        return agents
    claude = repo / "CLAUDE.md"
    if claude.exists():
        return claude
    return agents


def ensure_doc_block(path: Path, dry_run: bool) -> tuple[str, bool]:
    changed = False
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        text = ""

    block = TOKEN_REDUCE_BLOCK.strip()

    if BLOCK_RE.search(text):
        updated = BLOCK_RE.sub(block, text)
        if updated != text:
            if not dry_run:
                path.write_text(updated.rstrip() + "\n", encoding="utf-8")
            changed = True
        return "block-replaced", changed

    if HELPER_RE.search(text):
        return "already-present", changed

    if text.strip():
        updated = text.rstrip() + "\n\n" + block + "\n"
        action = "block-added"
    else:
        heading = "# Agent Instructions"
        updated = f"{heading}\n\n{block}\n"
        action = "file-created"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    changed = True
    return action, changed


def install_workspace(
    workspace_root: Path,
    skill_source: Path,
    include_self: bool,
    dry_run: bool,
    force_relink: bool,
) -> dict:
    repo_results: list[RepoInstallResult] = []
    total_changed = 0
    source_root = skill_source.resolve()
    canonical_root = canonical_skill_repo_root(source_root)
    repos = iter_repos(workspace_root)

    for repo in repos:
        if not include_self and repo.resolve() in {source_root, canonical_root}:
            continue

        skill_link, changed_link = ensure_skill_link(repo, source_root, dry_run, force_relink)
        doc_path = target_doc(repo)
        doc_action, changed_doc = ensure_doc_block(doc_path, dry_run)
        changed = changed_link or changed_doc
        if changed:
            total_changed += 1
        repo_results.append(
            RepoInstallResult(
                repo=repo.name,
                skill_link=skill_link,
                doc_file=doc_path.name,
                doc_action=doc_action,
                changed=changed,
            )
        )

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "skill_source": str(source_root),
        "dry_run": dry_run,
        "force_relink": force_relink,
        "repo_count": len(repo_results),
        "repos_changed": total_changed,
        "results": [asdict(row) for row in repo_results],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("TOKEN_REDUCE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"),
    )
    parser.add_argument("--skill-source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--include-self", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-relink", action="store_true")
    args = parser.parse_args()

    payload = install_workspace(
        workspace_root=Path(args.workspace_root).resolve(),
        skill_source=Path(args.skill_source).resolve(),
        include_self=args.include_self,
        dry_run=args.dry_run,
        force_relink=args.force_relink,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
