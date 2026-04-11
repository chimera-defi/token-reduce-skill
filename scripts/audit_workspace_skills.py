#!/usr/bin/env python3
"""Audit token-reduce companion installation and doc-level adoption across a workspace."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TOKEN_REDUCE_RE = re.compile(r"token-reduce|token-reduce-paths", re.IGNORECASE)
CAVEMAN_RE = re.compile(r"(?:^|[^a-z])caveman(?:[^a-z]|$)|/caveman", re.IGNORECASE)
AXI_RE = re.compile(r"\b(?:axi|gh-axi|chrome-devtools-axi)\b", re.IGNORECASE)

DOC_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules", "README.md")
SKILL_NAMES = ("token-reduce", "axi", "caveman", "caveman-cn", "caveman-es", "compress")


@dataclass
class RepoSignals:
    repo: str
    token_reduce: bool
    caveman: bool
    axi: bool


def is_repo_root(path: Path) -> bool:
    git_entry = path / ".git"
    if git_entry.exists():
        return True
    return False


def read_doc_text(repo: Path) -> str:
    chunks: list[str] = []
    for filename in DOC_FILES:
        doc = repo / filename
        if not doc.exists():
            continue
        try:
            chunks.append(doc.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def scan_workspace(workspace_root: Path) -> list[RepoSignals]:
    rows: list[RepoSignals] = []
    for child in sorted(workspace_root.iterdir()):
        if not child.is_dir():
            continue
        if not is_repo_root(child):
            continue
        text = read_doc_text(child)
        rows.append(
            RepoSignals(
                repo=child.name,
                token_reduce=bool(TOKEN_REDUCE_RE.search(text)),
                caveman=bool(CAVEMAN_RE.search(text)),
                axi=bool(AXI_RE.search(text)),
            )
        )
    return rows


def skill_state(home: Path) -> dict[str, dict[str, bool | str]]:
    agents_dir = home / ".agents" / "skills"
    codex_dir = home / ".codex" / "skills"
    payload: dict[str, dict[str, bool | str]] = {}
    for skill in SKILL_NAMES:
        agents_path = agents_dir / skill
        codex_path = codex_dir / skill
        payload[skill] = {
            "agents_present": agents_path.exists(),
            "codex_present": codex_path.exists(),
            "codex_symlink": codex_path.is_symlink(),
        }
    return payload


def command_state() -> dict[str, bool]:
    return {
        "token-reduce-paths": shutil.which("token-reduce-paths") is not None,
        "qmd": shutil.which("qmd") is not None,
        "rtk": shutil.which("rtk") is not None,
        "gh-axi": shutil.which("gh-axi") is not None,
        "chrome-devtools-axi": shutil.which("chrome-devtools-axi") is not None,
    }


def summarize(rows: list[RepoSignals]) -> dict:
    total = len(rows)
    token_reduce = sum(int(r.token_reduce) for r in rows)
    caveman = sum(int(r.caveman) for r in rows)
    axi = sum(int(r.axi) for r in rows)
    pct = lambda n: round((n * 100.0 / total), 1) if total else 0.0
    return {
        "repo_count": total,
        "token_reduce_docs": token_reduce,
        "caveman_docs": caveman,
        "axi_docs": axi,
        "token_reduce_docs_pct": pct(token_reduce),
        "caveman_docs_pct": pct(caveman),
        "axi_docs_pct": pct(axi),
    }


def build_payload(workspace_root: Path) -> dict:
    rows = scan_workspace(workspace_root)
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "commands": command_state(),
        "skills": skill_state(Path.home()),
        "summary": summarize(rows),
        "repos": [r.__dict__ for r in rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("TOKEN_REDUCE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"),
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    payload = build_payload(Path(args.workspace_root).resolve())
    encoded = json.dumps(payload, indent=2)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
