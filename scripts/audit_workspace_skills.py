#!/usr/bin/env python3
"""Audit token-reduce installation and usage across sibling repositories."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


TOKEN_REDUCE_DOC_RE = re.compile(r"token-reduce|token-reduce-paths", re.IGNORECASE)
TOKEN_REDUCE_HELPER_RE = re.compile(
    r"(?:skills/token-reduce/scripts/)?token-reduce-(?:paths|snippet|search)(?:\.sh)?",
    re.IGNORECASE,
)
CAVEMAN_RE = re.compile(r"(?:^|[^a-z])caveman(?:[^a-z]|$)|/caveman", re.IGNORECASE)
AXI_RE = re.compile(r"\b(?:axi|gh-axi|chrome-devtools-axi)\b", re.IGNORECASE)

DOC_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules", "README.md")
SKILL_NAMES = ("token-reduce", "axi", "caveman", "caveman-cn", "caveman-es", "compress")


@dataclass
class RepoSignals:
    repo: str
    local_skill_installed: bool
    token_reduce_docs: bool
    docs_with_token_reduce: list[str]
    session_count: int
    helper_sessions: int
    telemetry_helper_calls: int
    helper_used_recently: bool
    usage_status: str
    install_and_docs_compliant: bool
    fully_compliant: bool


def is_repo_root(path: Path) -> bool:
    return (path / ".git").exists()


def canonical_skill_repo_root(skill_source: Path) -> Path:
    parts = skill_source.resolve().parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        if idx > 0:
            return Path(*parts[:idx])
    return skill_source.resolve()


def default_excluded_repo(workspace_root: Path) -> str | None:
    skill_root = canonical_skill_repo_root(Path(__file__).resolve().parents[1])
    if skill_root.parent == workspace_root:
        return skill_root.name
    return None


def workspace_repos(workspace_root: Path, excluded: set[str] | None = None) -> list[Path]:
    excluded = excluded or set()
    repos: list[Path] = []
    for child in sorted(workspace_root.iterdir()):
        if child.is_dir() and is_repo_root(child) and child.name not in excluded:
            repos.append(child)
    return repos


def repo_from_cwd(cwd: str, workspace_root: Path) -> str | None:
    try:
        resolved = Path(cwd).resolve()
    except OSError:
        return None
    try:
        rel = resolved.relative_to(workspace_root)
    except ValueError:
        return None
    if not rel.parts:
        return None
    repo_name = rel.parts[0]
    if not is_repo_root(workspace_root / repo_name):
        return None
    return repo_name


def doc_signals(repo: Path) -> tuple[list[str], bool, bool]:
    refs: list[str] = []
    saw_caveman = False
    saw_axi = False
    for filename in DOC_FILES:
        doc = repo / filename
        if not doc.exists():
            continue
        try:
            text = doc.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if TOKEN_REDUCE_DOC_RE.search(text):
            refs.append(filename)
        if CAVEMAN_RE.search(text):
            saw_caveman = True
        if AXI_RE.search(text):
            saw_axi = True
    return refs, saw_caveman, saw_axi


def local_skill_state(repo: Path) -> bool:
    skill_dir = repo / "skills" / "token-reduce"
    return (skill_dir / "SKILL.md").exists() and (skill_dir / "scripts" / "token-reduce-paths.sh").exists()


def skill_state(home: Path) -> dict[str, dict[str, bool]]:
    agents_dir = home / ".agents" / "skills"
    codex_dir = home / ".codex" / "skills"
    payload: dict[str, dict[str, bool]] = {}
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


def parse_claude_file_for_helper(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        message = event.get("message", {})
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") != "tool_use" or item.get("name") != "Bash":
                continue
            command = item.get("input", {}).get("command", "")
            if isinstance(command, str) and TOKEN_REDUCE_HELPER_RE.search(command):
                return True
    return False


def claude_usage_by_repo(workspace_root: Path, repos: list[Path], cutoff: datetime) -> dict[str, dict[str, int]]:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return {}

    cutoff_ts = cutoff.timestamp()
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "helper_sessions": 0})

    for repo in repos:
        slug = "-" + repo.resolve().as_posix().lstrip("/").replace("/", "-")
        for root in base.glob(f"{slug}*"):
            for session_file in sorted(root.glob("*.jsonl")):
                try:
                    if session_file.stat().st_mtime < cutoff_ts:
                        continue
                except OSError:
                    continue

                files = [session_file]
                subagent_dir = session_file.with_suffix("") / "subagents"
                if subagent_dir.exists():
                    files.extend(sorted(subagent_dir.glob("*.jsonl")))

                helper_used = any(parse_claude_file_for_helper(path) for path in files)
                stats[repo.name]["sessions"] += 1
                if helper_used:
                    stats[repo.name]["helper_sessions"] += 1

    return stats


def parse_codex_session_usage(path: Path, workspace_root: Path) -> tuple[str | None, bool]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None, False

    repo_name: str | None = None
    helper_used = False
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = event.get("payload", {})
        if repo_name is None:
            cwd = payload.get("cwd")
            if isinstance(cwd, str):
                repo_name = repo_from_cwd(cwd, workspace_root)

        if payload.get("type") != "function_call" or payload.get("name") != "exec_command":
            continue
        arguments_raw = payload.get("arguments", "{}")
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
        command = arguments.get("cmd", "") if isinstance(arguments, dict) else ""
        if isinstance(command, str) and TOKEN_REDUCE_HELPER_RE.search(command):
            helper_used = True

    return repo_name, helper_used


def codex_usage_by_repo(workspace_root: Path, cutoff: datetime) -> dict[str, dict[str, int]]:
    root = Path.home() / ".codex" / "sessions"
    if not root.exists():
        return {}

    cutoff_ts = cutoff.timestamp()
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "helper_sessions": 0})
    for session_file in sorted(root.rglob("*.jsonl")):
        try:
            if session_file.stat().st_mtime < cutoff_ts:
                continue
        except OSError:
            continue
        repo_name, helper_used = parse_codex_session_usage(session_file, workspace_root)
        if not repo_name:
            continue
        stats[repo_name]["sessions"] += 1
        if helper_used:
            stats[repo_name]["helper_sessions"] += 1
    return stats


def merge_usage_stats(*payloads: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "helper_sessions": 0})
    for payload in payloads:
        for repo, values in payload.items():
            merged[repo]["sessions"] += int(values.get("sessions", 0))
            merged[repo]["helper_sessions"] += int(values.get("helper_sessions", 0))
    return merged


def telemetry_helper_calls(repo: Path, cutoff: datetime) -> int:
    path = repo / "artifacts" / "token-reduction" / "events.jsonl"
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "helper_invocation":
            continue
        if str(event.get("status", "")).lower() == "error":
            continue
        raw_ts = event.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts is not None and ts < cutoff:
                continue
        count += 1
    return count


def build_rows(workspace_root: Path, days: int, include_source_repo: bool) -> tuple[list[RepoSignals], dict[str, int]]:
    excluded: set[str] = set()
    if not include_source_repo:
        source_repo = default_excluded_repo(workspace_root)
        if source_repo:
            excluded.add(source_repo)
    repos = workspace_repos(workspace_root, excluded=excluded)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    claude_usage = claude_usage_by_repo(workspace_root, repos, cutoff)
    codex_usage = codex_usage_by_repo(workspace_root, cutoff)
    usage = merge_usage_stats(claude_usage, codex_usage)

    rows: list[RepoSignals] = []
    caveman_docs = 0
    axi_docs = 0
    for repo in repos:
        refs, caveman, axi = doc_signals(repo)
        if caveman:
            caveman_docs += 1
        if axi:
            axi_docs += 1
        stats = usage.get(repo.name, {"sessions": 0, "helper_sessions": 0})
        session_count = int(stats["sessions"])
        helper_sessions = int(stats["helper_sessions"])
        telemetry_helper = telemetry_helper_calls(repo, cutoff)
        helper_used_recently = helper_sessions > 0 or telemetry_helper > 0
        if helper_sessions > 0:
            usage_status = "used"
        elif telemetry_helper > 0:
            usage_status = "telemetry_only"
        else:
            usage_status = "no_recent_sessions" if session_count == 0 else "no_helper_usage"
        installed = local_skill_state(repo)
        docs_ok = bool(refs)
        install_and_docs = installed and docs_ok
        fully_compliant = install_and_docs and helper_used_recently
        rows.append(
            RepoSignals(
                repo=repo.name,
                local_skill_installed=installed,
                token_reduce_docs=docs_ok,
                docs_with_token_reduce=refs,
                session_count=session_count,
                helper_sessions=helper_sessions,
                telemetry_helper_calls=telemetry_helper,
                helper_used_recently=helper_used_recently,
                usage_status=usage_status,
                install_and_docs_compliant=install_and_docs,
                fully_compliant=fully_compliant,
            )
        )
    return rows, {"caveman_docs": caveman_docs, "axi_docs": axi_docs}


def summarize(rows: list[RepoSignals], extra: dict[str, int]) -> dict:
    total = len(rows)
    installed = sum(int(r.local_skill_installed) for r in rows)
    docs = sum(int(r.token_reduce_docs) for r in rows)
    install_docs = sum(int(r.install_and_docs_compliant) for r in rows)
    sessions = sum(r.session_count for r in rows)
    repos_with_sessions = sum(int(r.session_count > 0) for r in rows)
    helper_used_repos = sum(int(r.helper_used_recently) for r in rows)
    active_repos_with_helper = sum(int(r.helper_used_recently and r.session_count > 0) for r in rows)
    telemetry_only_repos = sum(int(r.telemetry_helper_calls > 0 and r.helper_sessions == 0) for r in rows)
    fully_compliant = sum(int(r.fully_compliant) for r in rows)
    pct = lambda n: round((n * 100.0 / total), 1) if total else 0.0
    pct_active = lambda n: round((n * 100.0 / repos_with_sessions), 1) if repos_with_sessions else 0.0
    return {
        "repo_count": total,
        "local_skill_installed": installed,
        "token_reduce_docs": docs,
        "install_and_docs_compliant": install_docs,
        "repos_with_recent_sessions": repos_with_sessions,
        "repos_with_helper_usage": helper_used_repos,
        "active_repos_with_helper_usage": active_repos_with_helper,
        "repos_with_telemetry_only_usage": telemetry_only_repos,
        "fully_compliant_repos": fully_compliant,
        "total_recent_sessions": sessions,
        "caveman_docs": int(extra.get("caveman_docs", 0)),
        "axi_docs": int(extra.get("axi_docs", 0)),
        "local_skill_installed_pct": pct(installed),
        "token_reduce_docs_pct": pct(docs),
        "install_and_docs_compliant_pct": pct(install_docs),
        "repos_with_helper_usage_pct": pct(helper_used_repos),
        "active_repos_with_helper_usage_pct": pct_active(active_repos_with_helper),
        "repos_with_telemetry_only_usage_pct": pct(telemetry_only_repos),
        "fully_compliant_repos_pct": pct(fully_compliant),
    }


def build_payload(workspace_root: Path, days: int, include_source_repo: bool) -> dict:
    rows, extra = build_rows(workspace_root, days, include_source_repo=include_source_repo)
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "lookback_days": days,
        "include_source_repo": include_source_repo,
        "commands": command_state(),
        "skills": skill_state(Path.home()),
        "summary": summarize(rows, extra),
        "gaps": {
            "missing_local_skill": [r.repo for r in rows if not r.local_skill_installed],
            "missing_doc_guidance": [r.repo for r in rows if not r.token_reduce_docs],
            "active_without_helper_usage": [r.repo for r in rows if r.session_count > 0 and not r.helper_used_recently],
            "fully_compliant": [r.repo for r in rows if r.fully_compliant],
        },
        "repos": [asdict(r) for r in rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("TOKEN_REDUCE_WORKSPACE_ROOT", "/root/.openclaw/workspace/dev"),
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--include-source-repo", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    payload = build_payload(
        Path(args.workspace_root).resolve(),
        args.days,
        include_source_repo=args.include_source_repo,
    )
    encoded = json.dumps(payload, indent=2)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
