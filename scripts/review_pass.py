#!/usr/bin/env python3
"""Report-only diagnostic pass for the token-reduce hook stack.

This is the reusable regression harness for the 2026-09-12 hook-pathology
diagnostic pass (three root causes: cold-start pending-gate over-blocking +
cross-session `default.json` state poisoning; cost-blind broad-scan counting
doubled by dual global+repo hook wiring; a silent-empty `find` caused by
`~/.claude/projects` being a symlink). Fixes F1-F9 landed in this repo's
`scripts/`; this tool exists so drift between that fixed repo copy and the
two separate deploy targets (`.worktrees/main` and the live
`~/.claude/hooks/token-reduce/` copy -- see
`references/worktree-deploy-sync.md`) gets caught automatically instead of
re-discovered the hard way.

Every subcommand is READ-ONLY: hashing, `git show`/`git fetch`, subprocess
calls to hook scripts with `TOKEN_REDUCE_REPO_ROOT` pointed at a throwaway
tmp directory, and telemetry reads. Nothing here writes to live state,
`~/.claude/hooks/`, `.worktrees/main`, or `~/.claude/skills/`. Redeploying a
fix is a separate, human-approved step.

Exit codes (per subcommand, and for `all` as the worst of all five):
    0 = healthy, no findings
    1 = findings (drift / regressions / gaps detected -- the tool is WORKING)
    2 = tool error (the check itself could not run, e.g. missing script)

Subcommands: deploy-drift, hook-contract, env-sanity, adoption-snapshot,
inventory-staleness, all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Reuse the hooks' own canonical helpers instead of re-implementing their
# session-key/state-path/telemetry logic here -- a hand-rolled copy can
# silently drift from the real implementation and mask the exact regressions
# this tool exists to catch (see round2-P1-P6 notes).
import token_reduce_state as _trs  # noqa: E402
import token_reduce_telemetry as _trt  # noqa: E402

ENTRYPOINTS = ["enforce-token-reduce-first.py", "remind-token-reduce.py"]
HELPER_MODULES = [
    "token_reduce_state.py",
    "token_reduce_telemetry.py",
    "token_reduce_config.py",
    "command_rewrites.py",
    "coverage_patterns.py",
]
WATCHED_FILES = ENTRYPOINTS + HELPER_MODULES

DEFAULT_DEPLOYED_ROOT = Path("~/.claude/hooks/token-reduce").expanduser()
DEFAULT_SKILLS_SYMLINK = Path("~/.claude/skills/token-reduce").expanduser()
DEFAULT_PROJECTS_PATH = Path("~/.claude/projects").expanduser()

EXIT_HEALTHY = 0
EXIT_FINDINGS = 1
EXIT_TOOL_ERROR = 2


# --------------------------------------------------------------------------- #
# Shared result shape
# --------------------------------------------------------------------------- #


@dataclass
class CheckResult:
    name: str
    ok: bool
    tool_error: bool = False
    lines: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        if self.tool_error:
            return EXIT_TOOL_ERROR
        if not self.ok:
            return EXIT_FINDINGS
        return EXIT_HEALTHY

    @property
    def status(self) -> str:
        if self.tool_error:
            return "TOOL ERROR"
        if not self.ok:
            return "FINDINGS"
        return "HEALTHY"

    def render_text(self) -> str:
        out = [f"=== {self.name} ===", f"status: {self.status}"]
        out.extend(self.lines)
        if self.findings:
            out.append("findings:")
            out.extend(f"  - {f_}" for f_ in self.findings)
        return "\n".join(out)

    def render_markdown(self) -> str:
        out = [f"## {self.name}", "", f"**Status:** {self.status}", ""]
        out.extend(self.lines)
        if self.findings:
            out.append("")
            out.append("**Findings:**")
            out.extend(f"- {f_}" for f_ in self.findings)
        out.append("")
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #


def _default_repo_root() -> Path:
    # P3: delegate to the hooks' own repo_root() so --repo-root defaulting
    # (TOKEN_REDUCE_REPO_ROOT / CLAUDE_PROJECT_DIR / cwd git-toplevel) matches
    # exactly what the hooks being audited use, instead of a parallel
    # SCRIPT_DIR-anchored reimplementation that could disagree with them.
    return _trs.repo_root()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_oid(data: bytes, algo: str) -> str:
    """Hash bytes the way git hashes a blob object: <algo>(b"blob <len>\\0" + data).
    Matching git's own object-hash format lets local file content be
    compared directly against `git ls-tree` OIDs, with no per-file
    subprocess needed for the local side (P5)."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.new(algo, header + data).hexdigest()


def _blob_oid_of_file(path: Path, algo: str) -> str | None:
    try:
        return _git_blob_oid(path.read_bytes(), algo)
    except OSError:
        return None


_OID_LEN_TO_ALGO = {40: "sha1", 64: "sha256"}


def _origin_blob_oids(repo_root: Path, subpath: str) -> dict[str, str] | None:
    """P5: ONE `git ls-tree -r origin/main -- <subpath>` call covering every
    watched file, replacing a `git show origin/main:<file>` subprocess per
    file. Returns {relpath: blob_oid} or None if origin/main is unreadable."""
    rc, out, _err = _git(repo_root, "ls-tree", "-r", "origin/main", "--", subpath)
    if rc != 0:
        return None
    oids: dict[str, str] = {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        meta, relpath = line.split("\t", 1)
        parts = meta.split()
        if len(parts) != 3:
            continue
        _mode, _type, oid = parts
        oids[relpath] = oid
    return oids


def _detect_blob_algo(oids: dict[str, str]) -> str:
    """Infer sha1 vs sha256 object format from an observed OID's hex length
    instead of assuming -- git defaults to sha1 almost universally, but a
    repo configured with extensions.objectFormat=sha256 would break a
    hardcoded assumption."""
    for oid in oids.values():
        algo = _OID_LEN_TO_ALGO.get(len(oid))
        if algo:
            return algo
    return "sha1"


def _git(git_dir: Path, *args: str, timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(git_dir), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


@contextmanager
def _scratch_repo() -> Iterator[Path]:
    """A throwaway tmp git repo used ONLY as TOKEN_REDUCE_REPO_ROOT scratch
    space for hook subprocess invocations -- never the real repo/telemetry."""
    d = Path(tempfile.mkdtemp(prefix="review-pass-hc-"))
    try:
        _git(d, "-c", "init.defaultBranch=main", "init", "-q")
        _git(d, "config", "user.email", "review-pass@example.com")
        _git(d, "config", "user.name", "review-pass")
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =========================================================================== #
# 1. deploy-drift
# =========================================================================== #


def git_fetch_origin(repo_root: Path, *, no_fetch: bool, timeout: int = 20) -> tuple[bool, str]:
    if no_fetch:
        return True, "skipped (--no-fetch)"
    rc, _out, err = _git(repo_root, "fetch", "origin", "--quiet", timeout=timeout)
    if rc != 0:
        return False, (err or "fetch failed").strip()[:200]
    return True, "ok"


def _resolve_worktree_main(skills_symlink: Path, override: Path | None) -> tuple[Path | None, str | None]:
    """Returns (resolved worktree/main path or None, raw readlink target or None)."""
    if override is not None:
        return (override if override.is_dir() else None), str(override)
    if not skills_symlink.is_symlink():
        return None, None
    try:
        raw_target = os.readlink(skills_symlink)
    except OSError:
        return None, None
    candidate = Path(raw_target)
    if not candidate.is_absolute():
        candidate = skills_symlink.parent / candidate
    resolved = candidate if candidate.is_dir() else None
    return resolved, raw_target


def check_deploy_drift(args: argparse.Namespace) -> CheckResult:
    repo_root: Path = args.repo_root
    repo_scripts: Path = args.repo_scripts
    deployed_root: Path = args.deployed_root
    skills_symlink: Path = args.skills_symlink

    lines: list[str] = []
    findings: list[str] = []
    data: dict[str, Any] = {"files": {}}

    fetch_ok, fetch_msg = git_fetch_origin(repo_root, no_fetch=args.no_fetch)
    origin_ref_ok = False
    if not fetch_ok:
        lines.append(f"origin/main fetch: UNKNOWN ({fetch_msg}) -- tolerating offline")
    else:
        rc, out, _err = _git(repo_root, "rev-parse", "origin/main")
        origin_commit = out.strip()
        origin_ref_ok = rc == 0 and bool(origin_commit)
        lines.append(f"origin/main fetch: {fetch_msg}" + (f" ({origin_commit[:12]})" if origin_ref_ok else " (ref unresolved)"))
    data["origin_available"] = origin_ref_ok

    # skills symlink + .worktrees/main
    worktree_main, raw_target = _resolve_worktree_main(skills_symlink, args.worktree_main)
    if skills_symlink.is_symlink():
        lines.append(f"skills symlink: {skills_symlink} -> {raw_target or '?'}")
    elif args.worktree_main is not None:
        lines.append(f".worktrees/main override: {args.worktree_main}")
    else:
        lines.append(f"skills symlink not found: {skills_symlink} (marking .worktrees/main unknown)")
    data["worktree_main"] = str(worktree_main) if worktree_main else None

    worktree_commit = None
    worktree_detached = None
    if worktree_main is not None:
        rc_ref, head_ref, _e = _git(worktree_main, "rev-parse", "--abbrev-ref", "HEAD")
        rc_commit, head_commit, _e2 = _git(worktree_main, "rev-parse", "HEAD")
        if rc_ref == 0 and rc_commit == 0:
            worktree_commit = head_commit.strip()
            worktree_detached = head_ref.strip() == "HEAD"
            lines.append(
                f".worktrees/main: {worktree_main} @ {worktree_commit[:12]}"
                + (" (DETACHED HEAD)" if worktree_detached else f" (branch={head_ref.strip()})")
            )
            if worktree_detached:
                findings.append(
                    f".worktrees/main is in detached HEAD state ({worktree_commit[:12]}) -- "
                    "expected per references/worktree-deploy-sync.md's 'Root anomaly' note, "
                    "but still flagged so it isn't missed"
                )
        else:
            lines.append(f".worktrees/main: {worktree_main} (git state unreadable -- marking unknown)")
    else:
        lines.append(".worktrees/main: unresolvable (marking unknown)")

    if origin_ref_ok and worktree_commit:
        rc, origin_commit_full, _e = _git(repo_root, "rev-parse", "origin/main")
        if rc == 0 and origin_commit_full.strip() and origin_commit_full.strip() != worktree_commit:
            findings.append(
                f".worktrees/main ({worktree_commit[:12]}) is behind origin/main "
                f"({origin_commit_full.strip()[:12]})"
            )

    # per-file hash comparison. P5: one batched `git ls-tree` call covers the
    # whole origin/main side (was one `git show` subprocess per watched
    # file); local files (repo/worktree-main/deployed) are hashed in-process
    # as git blobs in the SAME OID space so all four columns stay directly
    # comparable, with no added subprocess cost for the local side.
    origin_oids = _origin_blob_oids(repo_root, "scripts") if origin_ref_ok else None
    blob_algo = _detect_blob_algo(origin_oids) if origin_oids else "sha1"

    lines.append("")
    lines.append("| file | repo (working tree) | origin/main | .worktrees/main | deployed | drift |")
    lines.append("|---|---|---|---|---|---|")
    for name in WATCHED_FILES:
        repo_sha = _blob_oid_of_file(repo_scripts / name, blob_algo)
        origin_sha = origin_oids.get(f"scripts/{name}") if origin_oids is not None else None
        worktree_sha = _blob_oid_of_file(worktree_main / "scripts" / name, blob_algo) if worktree_main else None
        deployed_sha = _blob_oid_of_file(deployed_root / name, blob_algo)

        def short(sha: str | None) -> str:
            return sha[:10] if sha else "?"

        drift_bits = []
        if repo_sha is not None and deployed_sha is not None and repo_sha != deployed_sha:
            drift_bits.append("deployed")
        if repo_sha is not None and worktree_sha is not None and repo_sha != worktree_sha:
            drift_bits.append("worktree-main")
        drift_label = ", ".join(drift_bits) if drift_bits else "-"
        lines.append(
            f"| `{name}` | `{short(repo_sha)}` | `{short(origin_sha)}` | `{short(worktree_sha)}` "
            f"| `{short(deployed_sha)}` | {drift_label} |"
        )
        data["files"][name] = {
            "repo": repo_sha,
            "origin_main": origin_sha,
            "worktree_main": worktree_sha,
            "deployed": deployed_sha,
        }
        if repo_sha is None:
            findings.append(f"{name}: missing from repo copy at {repo_scripts}")
            continue
        if deployed_sha is None:
            findings.append(f"{name}: missing from deployed copy at {deployed_root}")
        elif repo_sha != deployed_sha:
            findings.append(f"{name}: deployed copy differs from repo working tree (deployed copy behind repo)")
        if worktree_main is not None and worktree_sha is None:
            findings.append(f"{name}: missing from .worktrees/main at {worktree_main}")
        elif worktree_sha is not None and repo_sha != worktree_sha:
            findings.append(f"{name}: .worktrees/main skill copy differs from repo working tree")

    ok = not findings
    return CheckResult(name="deploy-drift", ok=ok, lines=lines, findings=findings, data=data)


# =========================================================================== #
# 2. hook-contract
# =========================================================================== #


@dataclass
class HookCopy:
    label: str
    root: Path

    @property
    def enforce_path(self) -> Path:
        return self.root / "enforce-token-reduce-first.py"

    @property
    def remind_path(self) -> Path:
        return self.root / "remind-token-reduce.py"

    def available(self) -> bool:
        return self.enforce_path.is_file() and self.remind_path.is_file()


@dataclass
class StepResult:
    hook: str  # "enforce" | "remind"
    ok: bool  # subprocess executed (infra-level, not a pass/fail verdict)
    returncode: int | None
    stdout: str
    error: str | None


@dataclass
class ScenarioResult:
    id: str
    description: str
    passed: bool
    detail: str


def _run_script(script: Path, root: Path, payload: dict, *, env_extra: dict | None = None, timeout: int = 20) -> dict:
    if not script.is_file():
        return {"ok": False, "returncode": None, "stdout": "", "error": f"missing script: {script}"}
    env = os.environ.copy()
    env["TOKEN_REDUCE_REPO_ROOT"] = str(root)
    env["PYTHONPATH"] = str(script.parent) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("TOKEN_REDUCE_ENFORCE_MODE", None)
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            cwd=str(root),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "stdout": "", "error": "timeout"}
    except OSError as exc:
        return {"ok": False, "returncode": None, "stdout": "", "error": str(exc)}
    return {"ok": True, "returncode": proc.returncode, "stdout": proc.stdout, "error": None}


def _run_enforce(copy: HookCopy, root: Path, command: str, session_id: str, *, tool_use_id: str | None = None) -> StepResult:
    payload: dict[str, object] = {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}}
    if tool_use_id:
        payload["tool_use_id"] = tool_use_id
    r = _run_script(copy.enforce_path, root, payload)
    return StepResult(hook="enforce", ok=r["ok"], returncode=r["returncode"], stdout=r["stdout"], error=r["error"])


def _run_remind(copy: HookCopy, root: Path, prompt: str, session_id: str) -> StepResult:
    payload = {"session_id": session_id, "prompt": prompt}
    r = _run_script(copy.remind_path, root, payload)
    return StepResult(hook="remind", ok=r["ok"], returncode=r["returncode"], stdout=r["stdout"], error=r["error"])


DISCOVERY_PROMPT = "where is the auth hook defined in this repo"


def _fail(sid: str, desc: str, detail: str, steps: list[StepResult]) -> tuple[ScenarioResult, list[StepResult]]:
    return ScenarioResult(id=sid, description=desc, passed=False, detail=detail), steps


def _scenario_s1(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S1", "cold-start: discovery prompt then `which rg` MUST allow"
    with _scratch_repo() as root:
        session_id = "hc-s1"
        remind = _run_remind(copy, root, DISCOVERY_PROMPT, session_id)
        if not remind.ok:
            return _fail(sid, desc, f"remind hook failed to execute: {remind.error}", [remind])
        enforce = _run_enforce(copy, root, "which rg", session_id)
        steps = [remind, enforce]
        if not enforce.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {enforce.error}", steps)
        passed = enforce.returncode == 0
        detail = f"`which rg` after discovery prompt -> rc={enforce.returncode}, stdout={enforce.stdout[:160]!r}"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s2(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S2", "pending + targeted `ls -la <specific dir>` MUST allow"
    with _scratch_repo() as root:
        session_id = "hc-s2"
        (root / "scripts").mkdir(exist_ok=True)
        remind = _run_remind(copy, root, DISCOVERY_PROMPT, session_id)
        if not remind.ok:
            return _fail(sid, desc, f"remind hook failed to execute: {remind.error}", [remind])
        enforce = _run_enforce(copy, root, "ls -la scripts", session_id)
        steps = [remind, enforce]
        if not enforce.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {enforce.error}", steps)
        passed = enforce.returncode == 0
        detail = f"`ls -la scripts` while pending -> rc={enforce.returncode}, stdout={enforce.stdout[:160]!r}"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s3(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S3", "pending + broad `grep -R foo .` MUST block with a helper hint"
    with _scratch_repo() as root:
        session_id = "hc-s3"
        remind = _run_remind(copy, root, DISCOVERY_PROMPT, session_id)
        if not remind.ok:
            return _fail(sid, desc, f"remind hook failed to execute: {remind.error}", [remind])
        enforce = _run_enforce(copy, root, "grep -R foo .", session_id)
        steps = [remind, enforce]
        if not enforce.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {enforce.error}", steps)
        if enforce.returncode != 2:
            return _fail(sid, desc, f"expected block (rc=2), got rc={enforce.returncode}", steps)
        try:
            decision = json.loads(enforce.stdout)
        except json.JSONDecodeError:
            return _fail(sid, desc, f"block stdout is not valid JSON: {enforce.stdout[:160]!r}", steps)
        reason = str(decision.get("reason", ""))
        has_hint = "token-reduce" in reason.lower() or "qmd" in reason.lower()
        passed = bool(reason.strip()) and has_hint
        detail = f"reason={reason[:200]!r}"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s4(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S4", "compound cheap `ls; find -maxdepth 1 | wc -l; date` MUST allow"
    with _scratch_repo() as root:
        session_id = "hc-s4"
        target = root / "projects_like_dir"
        target.mkdir()
        cmd = f"ls -la {target}; find {target} -maxdepth 1 -type d | wc -l; date"
        enforce = _run_enforce(copy, root, cmd, session_id)
        steps = [enforce]
        if not enforce.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {enforce.error}", steps)
        passed = enforce.returncode == 0
        detail = f"compound cheap command -> rc={enforce.returncode}, stdout={enforce.stdout[:160]!r}"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s5(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S5", "quoted payload with embedded `find /...` text MUST allow, twice, no escalation"
    with _scratch_repo() as root:
        session_id = "hc-s5"
        cmd = 'echo \'{"c":"find /home/x -name y"}\' | some-tool'
        first = _run_enforce(copy, root, cmd, session_id, tool_use_id="hc-s5-a")
        second = _run_enforce(copy, root, cmd, session_id, tool_use_id="hc-s5-b")
        steps = [first, second]
        if not first.ok or not second.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {first.error or second.error}", steps)
        # Different tool_use_id => a genuine second attempt, not a dedup replay. If
        # the quoted text were mistaken for a real broad scan, the second attempt
        # would escalate to a hard block (see F5's real-retry semantics). Both
        # staying at rc=0 is the observable proof that it was never counted broad.
        passed = first.returncode == 0 and second.returncode == 0 and first.stdout == "" and second.stdout == ""
        detail = f"call1 rc={first.returncode} call2 rc={second.returncode} (no escalation = never classified broad)"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s6(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S6", "double-run dedup: same broad payload twice within 1s -> counter +1 total, identical decisions"
    with _scratch_repo() as root:
        session_id = "hc-s6"
        cmd = "tree ."
        first = _run_enforce(copy, root, cmd, session_id, tool_use_id="hc-s6-dup")
        second = _run_enforce(copy, root, cmd, session_id, tool_use_id="hc-s6-dup")
        steps = [first, second]
        if not first.ok or not second.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {first.error or second.error}", steps)
        identical = first.returncode == second.returncode and first.stdout == second.stdout
        # P1: read the counter through the hooks' own broad_attempt_count(),
        # not a hand-rolled session-key-slug + state-path reimplementation --
        # a hand-rolled copy that drifts from the real path/schema would
        # silently read a missing file, return 0, and let count<=1 pass even
        # during an actual double-increment regression. Also require
        # count >= 1 (the counter file must exist at all) so that same class
        # of path drift fails loudly instead of masking as "healthy".
        count = _trs.broad_attempt_count(root, session_id)
        events = _trt.load_events(root)
        dedup_seen = any(e.get("event") == "hook_dedup_replay" for e in events)
        passed = identical and count == 1 and dedup_seen
        detail = (
            f"call1 rc={first.returncode} call2 rc={second.returncode} identical={identical} "
            f"broad_attempt_count={count} hook_dedup_replay_seen={dedup_seen}"
        )
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s7(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S7", "find on symlink root MUST block loudly with 'symlink'; trailing-slash form allowed"
    with _scratch_repo() as root:
        session_id = "hc-s7"
        link_dir = Path(tempfile.mkdtemp(prefix="review-pass-hc-s7-"))
        real_dir = link_dir / "real_target"
        real_dir.mkdir()
        link = link_dir / "the_link"
        try:
            link.symlink_to(real_dir)
            first = _run_enforce(copy, root, f"find {link} -name x", session_id, tool_use_id="hc-s7-a")
            second = _run_enforce(copy, root, f"find {link}/ -name x", session_id, tool_use_id="hc-s7-b")
        finally:
            shutil.rmtree(link_dir, ignore_errors=True)
        steps = [first, second]
        if not first.ok or not second.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {first.error or second.error}", steps)
        if first.returncode != 2:
            return _fail(sid, desc, f"bare symlink `find` expected block (rc=2), got rc={first.returncode}", steps)
        try:
            decision = json.loads(first.stdout)
        except json.JSONDecodeError:
            return _fail(sid, desc, f"block stdout not valid JSON: {first.stdout[:160]!r}", steps)
        reason = str(decision.get("reason", ""))
        first_ok = "symlink" in reason.lower()
        # Never silent: the trailing-slash form must produce an explicit decision
        # (allow, or a block unrelated to the symlink guard) -- not a crash.
        second_ok = second.returncode in (0, 2)
        if second.returncode == 2:
            try:
                second_decision = json.loads(second.stdout)
                second_ok = "symlink" not in str(second_decision.get("reason", "")).lower()
            except json.JSONDecodeError:
                second_ok = False
        passed = first_ok and second_ok
        detail = f"bare reason={reason[:160]!r}; trailing-slash rc={second.returncode}"
        return ScenarioResult(sid, desc, passed, detail), steps


def _scenario_s8(copy: HookCopy) -> tuple[ScenarioResult, list[StepResult]]:
    sid, desc = "S8", "catastrophic `find / -name x` MUST block, reason contains 'catastrophic'"
    with _scratch_repo() as root:
        session_id = "hc-s8"
        enforce = _run_enforce(copy, root, "find / -name x", session_id)
        steps = [enforce]
        if not enforce.ok:
            return _fail(sid, desc, f"enforce hook failed to execute: {enforce.error}", steps)
        if enforce.returncode != 2:
            return _fail(sid, desc, f"expected block (rc=2), got rc={enforce.returncode}", steps)
        try:
            decision = json.loads(enforce.stdout)
        except json.JSONDecodeError:
            return _fail(sid, desc, f"block stdout not valid JSON: {enforce.stdout[:160]!r}", steps)
        reason = str(decision.get("reason", ""))
        passed = "catastrophic" in reason.lower()
        detail = f"reason={reason[:160]!r}"
        return ScenarioResult(sid, desc, passed, detail), steps


SCENARIO_FUNCS: list[Callable[[HookCopy], tuple[ScenarioResult, list[StepResult]]]] = [
    _scenario_s1,
    _scenario_s2,
    _scenario_s3,
    _scenario_s4,
    _scenario_s5,
    _scenario_s6,
    _scenario_s7,
    _scenario_s8,
]


def _scenario_s9(all_steps: list[StepResult]) -> ScenarioResult:
    sid = "S9"
    desc = "block-shape: every block's stdout is JSON with non-empty reason; every allow's stdout is empty"
    bad: list[str] = []
    enforce_steps = [s for s in all_steps if s.hook == "enforce" and s.ok]
    for step in enforce_steps:
        if step.returncode == 2:
            try:
                decision = json.loads(step.stdout)
            except json.JSONDecodeError:
                bad.append(f"block stdout not valid JSON: {step.stdout[:120]!r}")
                continue
            if not str(decision.get("reason", "")).strip():
                bad.append("block stdout has empty reason")
        elif step.returncode == 0:
            if step.stdout != "":
                bad.append(f"allow stdout not empty: {step.stdout[:120]!r}")
    passed = not bad
    detail = "ok" if passed else "; ".join(bad[:5])
    return ScenarioResult(sid, desc, passed, detail)


def run_hook_contract_for_copy(copy: HookCopy) -> dict[str, Any]:
    if not copy.available():
        return {
            "available": False,
            "passed": False,
            "scenarios": {},
            "summary": f"{copy.label} copy missing enforce/remind scripts at {copy.root}",
        }
    scenario_results: dict[str, ScenarioResult] = {}
    all_steps: list[StepResult] = []
    for fn in SCENARIO_FUNCS:
        try:
            result, steps = fn(copy)
        except Exception as exc:  # never let one scenario crash the whole pass
            result = ScenarioResult(id=fn.__name__, description=fn.__name__, passed=False, detail=f"scenario raised: {exc}")
            steps = []
        scenario_results[result.id] = result
        all_steps.extend(steps)
    s9 = _scenario_s9(all_steps)
    scenario_results[s9.id] = s9
    passed = all(r.passed for r in scenario_results.values())
    return {"available": True, "passed": passed, "scenarios": scenario_results, "summary": None}


SCENARIO_IDS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]


def _compose_hook_contract_result(
    repo_result: dict[str, Any],
    deployed_result: dict[str, Any],
    scenario_ids: list[str] = SCENARIO_IDS,
) -> CheckResult:
    """Pure verdict logic: turn two per-copy scenario-result dicts (as produced
    by run_hook_contract_for_copy, or fabricated directly in tests) into the
    matrix table + finding attribution + exit-code shape. No subprocess calls,
    no I/O -- unit-testable in isolation from the real hook scripts."""
    lines: list[str] = []
    lines.append("| scenario | repo | deployed |")
    lines.append("|---|---|---|")
    for sid in scenario_ids:
        repo_r = repo_result["scenarios"].get(sid)
        dep_r = deployed_result["scenarios"].get(sid)
        repo_cell = "PASS" if (repo_r and repo_r.passed) else ("FAIL" if repo_r else "N/A")
        dep_cell = "PASS" if (dep_r and dep_r.passed) else ("FAIL" if dep_r else "N/A")
        lines.append(f"| `{sid}` | {repo_cell} | {dep_cell} |")
    lines.append("")
    for sid in scenario_ids:
        repo_r = repo_result["scenarios"].get(sid)
        dep_r = deployed_result["scenarios"].get(sid)
        if repo_r:
            lines.append(f"- `{sid}` {repo_r.description}")
            lines.append(f"  - repo: {'PASS' if repo_r.passed else 'FAIL'} -- {repo_r.detail}")
        if dep_r:
            lines.append(f"  - deployed: {'PASS' if dep_r.passed else 'FAIL'} -- {dep_r.detail}")

    findings: list[str] = []
    tool_error = False

    if not repo_result["available"]:
        tool_error = True
        findings.append(repo_result["summary"])
    elif not repo_result["passed"]:
        failing = [sid for sid in scenario_ids if not repo_result["scenarios"].get(sid, ScenarioResult(sid, "", False, "")).passed]
        findings.append(
            "repo copy FAILED hook-contract scenario(s) "
            f"{failing} -- this is a regression in scripts/, not a deploy-drift signal "
            "(if it's a `which`-argument-position scenario, cross-check against any in-flight "
            "fix to enforce-token-reduce-first.py/command_rewrites.py before treating it as new)"
        )

    if not deployed_result["available"]:
        findings.append(f"deployed copy unavailable: {deployed_result['summary']}")
    elif not deployed_result["passed"]:
        failing = [sid for sid in scenario_ids if not deployed_result["scenarios"].get(sid, ScenarioResult(sid, "", False, "")).passed]
        if repo_result.get("passed"):
            findings.append(
                f"deployed copy FAILED scenario(s) {failing} that the repo copy PASSES -- "
                "deployed copy behind repo (drift). Redeploy via references/worktree-deploy-sync.md "
                "(a separate, human-approved step)."
            )
        else:
            findings.append(
                f"deployed copy also failed scenario(s) {failing}, and the repo copy fails too -- "
                "cannot cleanly attribute this to drift alone."
            )

    ok = not findings
    data = {"repo": repo_result, "deployed": deployed_result}
    return CheckResult(name="hook-contract", ok=ok, tool_error=tool_error, lines=lines, findings=findings, data=data)


def check_hook_contract(args: argparse.Namespace) -> CheckResult:
    repo_copy = HookCopy("repo", args.repo_scripts)
    deployed_copy = HookCopy("deployed", args.deployed_root)

    try:
        repo_result = run_hook_contract_for_copy(repo_copy)
    except Exception as exc:
        return CheckResult(
            name="hook-contract",
            ok=False,
            tool_error=True,
            lines=[f"repo copy runner crashed: {exc}"],
            findings=[f"repo copy runner crashed: {exc}"],
        )
    try:
        deployed_result = run_hook_contract_for_copy(deployed_copy)
    except Exception as exc:
        deployed_result = {"available": False, "passed": False, "scenarios": {}, "summary": f"deployed copy runner crashed: {exc}"}

    return _compose_hook_contract_result(repo_result, deployed_result, SCENARIO_IDS)


# =========================================================================== #
# 3. env-sanity
# =========================================================================== #


def _find_line_count(path_str: str, *, maxdepth: int | None, timeout: int = 15) -> int:
    # NOTE: takes a raw string, not a Path -- Path() silently strips a trailing
    # "/", which is exactly the byte that distinguishes the two sides of the
    # symlink-find trap this check exists to demonstrate.
    cmd = ["find", path_str]
    if maxdepth is not None:
        cmd.extend(["-maxdepth", str(maxdepth)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return -1
    if proc.returncode not in (0, 1):
        return -1
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def _with_trailing_sep(path_str: str) -> str:
    """P6: guarantee exactly one trailing os.sep regardless of whether
    path_str already ends in one. Naive `path_str + "/"` would double up on
    an already-trailing-sep input (or, from a differently-normalized
    caller, fail to add one at all) -- either failure mode collapses the
    bare-vs-slash distinction this check exists to demonstrate."""
    return os.path.join(path_str, "")


def _guard_status_for_copy(copy: HookCopy, target: Path) -> str:
    if not copy.available():
        return "unavailable"
    with _scratch_repo() as root:
        step = _run_enforce(copy, root, f"find {target} -maxdepth 1", f"env-sanity-{copy.label}")
    if not step.ok:
        return f"error ({step.error})"
    if step.returncode == 2:
        try:
            decision = json.loads(step.stdout)
        except json.JSONDecodeError:
            return "blocked (unparseable reason)"
        reason = str(decision.get("reason", ""))
        return "guarded" if "symlink" in reason.lower() else f"blocked (not symlink-attributed: {reason[:80]!r})"
    if step.returncode == 0:
        return "unguarded (silently allowed)"
    return f"unexpected rc={step.returncode}"


def _rg_hidden_demo() -> dict[str, Any]:
    if shutil.which("rg") is None:
        return {"ok": True, "skipped": True, "summary": "rg hidden-dir demo: skipped (rg not installed)"}
    d = Path(tempfile.mkdtemp(prefix="review-pass-rg-demo-"))
    try:
        (d / "visible.txt").write_text("hi\n")
        (d / ".hidden.txt").write_text("hi\n")
        (d / ".gitignore").write_text("ignored.txt\n")
        (d / "ignored.txt").write_text("hi\n")
        try:
            default = subprocess.run(["rg", "--files"], cwd=d, capture_output=True, text=True, timeout=15)
            full = subprocess.run(["rg", "--files", "--hidden", "--no-ignore"], cwd=d, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "skipped": False, "summary": f"rg hidden-dir demo: tool error running rg ({exc})"}
        default_n = len([line for line in default.stdout.splitlines() if line.strip()])
        full_n = len([line for line in full.stdout.splitlines() if line.strip()])
        ok = full_n > default_n
        summary = (
            f"rg hidden-dir demo: default `rg --files` finds {default_n} file(s); "
            f"`--hidden --no-ignore` finds {full_n} file(s) "
            f"({'confirms silent gap' if ok else 'UNEXPECTED: no gap observed'})"
        )
        return {"ok": ok, "skipped": False, "summary": summary, "default_count": default_n, "full_count": full_n}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_env_sanity(args: argparse.Namespace) -> CheckResult:
    lines: list[str] = []
    findings: list[str] = []
    data: dict[str, Any] = {}

    projects_path: Path = args.projects_path
    lines.append(f"projects path: {projects_path}")
    is_symlink = projects_path.is_symlink()
    data["is_symlink"] = is_symlink

    if not is_symlink:
        lines.append("not a symlink on this host/fixture -- trap not applicable")
    else:
        try:
            target = os.readlink(projects_path)
        except OSError:
            target = None
        lines.append(f"symlink target: {target or '?'}")

        bare = _find_line_count(str(projects_path), maxdepth=1)
        with_slash = _find_line_count(_with_trailing_sep(str(projects_path)), maxdepth=1)
        lines.append(f"`find {projects_path} -maxdepth 1` -> {bare} line(s); trailing-slash form -> {with_slash} line(s)")
        trap_live = 0 <= bare <= 1 and with_slash > 1
        data["trap_live"] = trap_live
        if trap_live:
            lines.append("silent-empty find trap: CONFIRMED live on this host")
        else:
            findings.append(f"expected find-on-symlink trap not reproduced (bare={bare}, slash={with_slash})")

        data["guard_status"] = {}
        for copy in (HookCopy("repo", args.repo_scripts), HookCopy("deployed", args.deployed_root)):
            status = _guard_status_for_copy(copy, projects_path)
            lines.append(f"guard status ({copy.label}): {status}")
            data["guard_status"][copy.label] = status
            if copy.label == "repo" and status != "guarded":
                findings.append(f"repo copy does not guard the symlink-find trap (status={status})")
            if copy.label == "deployed" and status != "guarded":
                findings.append(
                    f"deployed copy is UNGUARDED against the symlink-find trap (status={status}) -- "
                    "see references/worktree-deploy-sync.md"
                )

    rg_demo = _rg_hidden_demo()
    lines.append(rg_demo["summary"])
    data["rg_hidden_demo"] = rg_demo
    if not rg_demo["ok"]:
        findings.append(rg_demo["summary"])

    ok = not findings
    return CheckResult(name="env-sanity", ok=ok, lines=lines, findings=findings, data=data)


# =========================================================================== #
# 4. adoption-snapshot
# =========================================================================== #


INTERESTING_EVENTS = [
    "hook_block",
    "hook_warn",
    "post_block_compliance",
    "post_block_escape",
    "post_block_abandon",
    "hook_error",
    "hook_dedup_replay",
]


def check_adoption_snapshot(args: argparse.Namespace) -> CheckResult:
    # P2: reuse token_reduce_telemetry.load_events(days=...) instead of a
    # parallel reimplementation of the same cutoff/parse logic.
    events = _trt.load_events(args.repo_root, days=args.days)
    lines: list[str] = [f"telemetry window: last {args.days} day(s)", f"total events: {len(events)}"]
    findings: list[str] = []
    data: dict[str, Any] = {}

    by_event: Counter[str] = Counter(str(e.get("event", "unknown")) for e in events)
    data["by_event"] = dict(by_event)
    lines.append("counts by event:")
    for name in INTERESTING_EVENTS:
        lines.append(f"  {name}: {by_event.get(name, 0)}")
    other = {k: v for k, v in by_event.items() if k not in INTERESTING_EVENTS}
    if other:
        lines.append(f"  other ({sum(other.values())}): {', '.join(sorted(other))}")

    # P4: a hook_block EVENT is not necessarily a real block -- in warn mode
    # (TOKEN_REDUCE_ENFORCE_MODE=warn) the decision is downgraded to an
    # allow and recorded with status="warn", not status="blocked". Only
    # status=="blocked" events represent an actual block for these metrics.
    def _is_real_block(e: dict) -> bool:
        return e.get("event") == "hook_block" and e.get("status") == "blocked"

    block_cmds: Counter[str] = Counter()
    for e in events:
        if _is_real_block(e):
            cmd = (e.get("meta") or {}).get("command")
            if cmd:
                block_cmds[str(cmd)] += 1
    top_blocked = block_cmds.most_common(5)
    data["top_blocked_commands"] = top_blocked
    lines.append("top blocked commands:")
    if top_blocked:
        for cmd, n in top_blocked:
            lines.append(f"  {n}x {cmd[:100]}")
    else:
        lines.append("  (none)")

    # Storm sessions: >=2 REAL blocks (status=="blocked", not warn-mode
    # telemetry) among a session's first 5 RECORDED hook events
    # (chronological). Caveat: only decision-worthy events (block/warn/
    # dedup/error/compliance/escape/abandon) are ever written to events.jsonl --
    # clean allows are not -- so "first 5 calls" is approximated as "first 5
    # recorded telemetry events for that session_key", not literally the first
    # 5 tool calls of the session.
    per_session: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        sk = (e.get("meta") or {}).get("session_key")
        if sk:
            per_session[str(sk)].append(e)
    storms: list[tuple[str, int, int]] = []
    for sk, evs in per_session.items():
        evs_sorted = sorted(evs, key=lambda e: str(e.get("timestamp") or ""))
        first5 = evs_sorted[:5]
        blocks_in_first5 = sum(1 for e in first5 if _is_real_block(e))
        if blocks_in_first5 >= 2:
            storms.append((sk, blocks_in_first5, len(evs_sorted)))
    data["storm_sessions"] = storms
    lines.append(
        f"storm sessions (>=2 hook_block within first 5 recorded hook events for that session; "
        f"approximation -- see code comment): {len(storms)}"
    )
    for sk, n, total in storms[:10]:
        lines.append(f"  {sk}: {n} blocks in first 5 (of {total} recorded events)")
    if storms:
        findings.append(f"{len(storms)} storm session(s) detected in the last {args.days}d window")

    dedup_replays = by_event.get("hook_dedup_replay", 0)
    decisions = by_event.get("hook_block", 0) + by_event.get("hook_warn", 0)
    if dedup_replays:
        denom = decisions + dedup_replays
        ratio = dedup_replays / denom if denom else 0.0
        lines.append(f"dedup ratio: {ratio:.1%} ({dedup_replays} replayed / {denom} total decisions)")
        data["dedup_ratio"] = ratio
    else:
        lines.append("dedup ratio: no hook_dedup_replay telemetry in window (F5 meta not present)")
        data["dedup_ratio"] = None

    hook_errors = by_event.get("hook_error", 0)
    if hook_errors:
        findings.append(f"{hook_errors} hook_error event(s) in window -- check fail-open paths")

    ok = not findings
    return CheckResult(name="adoption-snapshot", ok=ok, lines=lines, findings=findings, data=data)


# =========================================================================== #
# 5. inventory-staleness
# =========================================================================== #


def _git_last_touch_days(repo_root: Path, path: Path) -> float | None:
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        rel = path
    rc, out, _err = _git(repo_root, "log", "-1", "--format=%ct", "--", str(rel))
    out = out.strip()
    if rc != 0 or not out.isdigit():
        return None
    return (time.time() - int(out)) / 86400.0


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def check_inventory_staleness(args: argparse.Namespace) -> CheckResult:
    repo_root: Path = args.repo_root
    scripts_dir: Path = args.repo_scripts

    lines: list[str] = []
    findings: list[str] = []
    data: dict[str, Any] = {}

    if not scripts_dir.is_dir():
        return CheckResult(
            name="inventory-staleness",
            ok=False,
            tool_error=True,
            lines=[f"scripts dir not found: {scripts_dir}"],
            findings=[f"scripts dir not found: {scripts_dir}"],
        )

    wiring_sources = [
        scripts_dir / "token-reduce-manage.sh",
        scripts_dir / "setup.sh",
        scripts_dir / "activate-token-reduce-stack.sh",
        repo_root / "README.md",
        repo_root / "CLAUDE.md",
        repo_root / "SKILL.md",
    ]
    refs_dir = repo_root / "references"
    if refs_dir.is_dir():
        wiring_sources.extend(sorted(refs_dir.glob("*.md")))
    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        wiring_sources.extend(sorted(skills_dir.glob("*/SKILL.md")))
    wiring_text = "\n".join(_safe_read(p) for p in wiring_sources if p.is_file())

    py_files = sorted(scripts_dir.glob("*.py"))
    sh_files = sorted(scripts_dir.glob("*.sh"))
    all_files = py_files + sh_files
    tests_dir = scripts_dir / "tests"
    tests_text = ""
    if tests_dir.is_dir():
        tests_text = "\n".join(_safe_read(p) for p in tests_dir.glob("*.py"))

    file_contents = {p.name: _safe_read(p) for p in all_files}

    candidates = []
    checked = 0
    for p in all_files:
        checked += 1
        base = p.stem
        cross_text = "\n".join(text for name, text in file_contents.items() if name != p.name)
        haystack = wiring_text + "\n" + cross_text
        pattern = re.compile(r"(?<![\w.-])" + re.escape(base) + r"(?![\w-])")
        wired = bool(pattern.search(haystack)) or bool(pattern.search(wiring_text))
        tested = bool(pattern.search(tests_text))
        last_touch_days = _git_last_touch_days(repo_root, p)
        stale = last_touch_days is not None and last_touch_days > 30
        if not wired and stale:
            candidates.append(
                {
                    "file": str(p.relative_to(repo_root)) if p.is_relative_to(repo_root) else p.name,
                    "last_touch_days": round(last_touch_days, 1) if last_touch_days is not None else None,
                    "tested": tested,
                }
            )

    data["checked"] = checked
    data["demote_candidates"] = candidates
    lines.append(f"scripts inventoried: {checked}")
    lines.append(f"unwired AND untouched>30d demote candidates: {len(candidates)}")
    for c in sorted(candidates, key=lambda c: c.get("last_touch_days") or 0, reverse=True):
        tested_note = " (has unit tests)" if c["tested"] else ""
        lines.append(f"  {c['file']}: last touched {c['last_touch_days']}d ago{tested_note}")

    if candidates:
        findings.append(
            f"{len(candidates)} script(s) appear unwired (no reference in manage.sh/setup.sh/docs/other "
            f"scripts) and untouched for 30+ days -- demote candidates: "
            f"{', '.join(c['file'] for c in candidates[:10])}"
        )

    ok = not findings
    return CheckResult(name="inventory-staleness", ok=ok, lines=lines, findings=findings, data=data)


# =========================================================================== #
# all
# =========================================================================== #


def cmd_all(args: argparse.Namespace) -> int:
    checks = [
        check_deploy_drift(args),
        check_hook_contract(args),
        check_env_sanity(args),
        check_adoption_snapshot(args),
        check_inventory_staleness(args),
    ]
    worst = max((c.exit_code for c in checks), default=EXIT_HEALTHY)

    verdict_lines = []
    for c in checks:
        suffix = f" -- {len(c.findings)} finding(s)" if c.findings else ""
        verdict_lines.append(f"- {c.name}: {c.status}{suffix}")

    report_lines = [
        "# token-reduce review pass",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Repo root: `{args.repo_root}`",
        f"Deployed root: `{args.deployed_root}`",
        "",
        "## Verdict",
        "",
    ]
    report_lines.extend(verdict_lines)
    report_lines.append("")
    if worst == EXIT_FINDINGS:
        report_lines.append(
            "> Note: exit code 1 (FINDINGS) can be the EXPECTED, correct result -- e.g. when the "
            "repo copy carries fixes not yet deployed. That means this tool is working, not that "
            "it is broken. Cross-check each finding against "
            "`references/worktree-deploy-sync.md` before treating it as a surprise. Redeploying a "
            "fix is a separate, human-approved step -- this tool never writes to deploy targets."
        )
        report_lines.append("")
    for c in checks:
        report_lines.append(c.render_markdown())
    report_text = "\n".join(report_lines) + "\n"

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")

    print("\n".join(verdict_lines))
    print(f"\nfull report: {report_path}")
    return worst


# =========================================================================== #
# CLI
# =========================================================================== #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_pass.py",
        description=(
            "Report-only diagnostic pass for the token-reduce hook stack: deploy drift, "
            "hook-contract regressions, environment sanity, adoption telemetry, and inventory "
            "staleness. All checks are read-only."
        ),
    )
    parser.add_argument("--repo-root", default=None, help="repo root to evaluate (default: git toplevel of this script)")
    parser.add_argument("--repo-scripts", default=None, help="path to the repo's scripts/ dir (default: <repo-root>/scripts)")
    parser.add_argument(
        "--deployed-root", default=str(DEFAULT_DEPLOYED_ROOT), help="deployed hook copy dir (default: ~/.claude/hooks/token-reduce)"
    )
    parser.add_argument(
        "--skills-symlink", default=str(DEFAULT_SKILLS_SYMLINK), help="path to the ~/.claude/skills/token-reduce symlink"
    )
    parser.add_argument("--worktree-main", default=None, help="override .worktrees/main path (default: resolved from --skills-symlink)")
    parser.add_argument(
        "--projects-path", default=str(DEFAULT_PROJECTS_PATH), help="path to check for the symlink-find trap (default: ~/.claude/projects)"
    )
    parser.add_argument("--days", type=int, default=7, help="telemetry window in days for adoption-snapshot (default: 7)")
    parser.add_argument("--no-fetch", action="store_true", help="skip `git fetch origin` in deploy-drift (offline/test mode)")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deploy-drift", help="Compare hashes of hook entrypoints/helpers across origin/main, .worktrees/main, and the deployed copy")
    sub.add_parser("hook-contract", help="Run the S1-S9 canned scenarios against the repo and deployed hook copies")
    sub.add_parser("env-sanity", help="Check the ~/.claude/projects symlink-find trap and the rg hidden-file demo")
    sub.add_parser("adoption-snapshot", help="Summarize recent hook/telemetry adoption signals")
    sub.add_parser("inventory-staleness", help="Flag unwired, long-untouched scripts as demote candidates")
    p_all = sub.add_parser("all", help="Run every check and write a combined markdown report")
    p_all.add_argument("--report", required=True, help="path to write the combined markdown report")
    return parser


def _resolve_paths(args: argparse.Namespace) -> None:
    args.repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    args.repo_scripts = Path(args.repo_scripts).resolve() if args.repo_scripts else (args.repo_root / "scripts")
    args.deployed_root = Path(args.deployed_root).expanduser()
    args.skills_symlink = Path(args.skills_symlink).expanduser()
    args.worktree_main = Path(args.worktree_main).resolve() if args.worktree_main else None
    args.projects_path = Path(args.projects_path).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _resolve_paths(args)

    single_checks: dict[str, Callable[[argparse.Namespace], CheckResult]] = {
        "deploy-drift": check_deploy_drift,
        "hook-contract": check_hook_contract,
        "env-sanity": check_env_sanity,
        "adoption-snapshot": check_adoption_snapshot,
        "inventory-staleness": check_inventory_staleness,
    }

    if args.command == "all":
        try:
            return cmd_all(args)
        except Exception as exc:
            print(f"review_pass.py: tool error running all: {exc}", file=sys.stderr)
            return EXIT_TOOL_ERROR

    try:
        result = single_checks[args.command](args)
    except Exception as exc:  # report-only tool must never crash the caller
        print(f"review_pass.py: tool error running {args.command}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    print(result.render_text())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
