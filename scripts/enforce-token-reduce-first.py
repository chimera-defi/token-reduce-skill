#!/usr/bin/env python3
"""PreToolUse hook: require token-reduce helper before exploratory Grep/Glob/Read/Bash."""
from __future__ import annotations

import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path

try:
    from command_rewrites import (
        FIND_ROOT_ARG_RE,
        command_scan_surfaces,
        estimate_output_tokens,
        format_block_message,
        is_broad_find,
        is_catastrophic,
        suggest_rewrite,
    )
    from coverage_patterns import matches_any_broad_pattern
    from token_reduce_state import (
        broad_attempt_count,
        clear_pending,
        consume_block,
        discovery_hint,
        is_pending,
        record_block,
        record_broad_attempt,
        record_decision,
        recent_decision,
        repo_root,
        session_key,
    )
    from token_reduce_telemetry import record_event
except Exception:
    # Fail-open: this hook is non-blocking by contract. A partial deploy
    # (entrypoint updated without its helper modules) -- or any other import-time
    # error -- must degrade to a silent allow, never a per-command traceback on
    # every tool call. Catch broadly, not just ImportError, so a syntax/attribute
    # error inside a helper module can't wedge the session either.
    try:
        sys.stdin.read()
    except Exception:
        pass
    sys.exit(0)


BROAD_BASH_PATTERNS = [
    # `find` is handled separately by matches_broad_bash() via is_broad_find()
    # (F4) so a cost-bounded `find <specific-dir> -maxdepth <=2>` isn't
    # flagged even though it starts with the same `find .`/`find /` shape.
    # `fd`/`tree` are handled separately too, via _bare_command_matches()
    # below: unlike the other patterns here, they need no characteristic
    # flag/arg to be recognized as a scanner, so a bare \b...\b search
    # matches them in ARGUMENT position too (`which fd`, `cargo install fd`,
    # `echo tree`) -- they must only count in COMMAND position.
    r"\bls\s+-R\b",
    r"\bgrep\s+-R\b",
    r"\bgrep\s+--recursive\b",
    r"\bdu\s+-a\b",
    r"\brg\b.*\s--files\b",
]

# fd/tree bare-command-name patterns, command-position only (see comment
# above). A shell segment boundary is `;`, `&&`, `||`, or `|`; the pattern
# must match starting at the beginning of a segment (after stripping
# leading whitespace), not merely appear anywhere in it.
_SHELL_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|]")
_FD_COMMAND_RE = re.compile(r"^fd\b(?:\s|$)")
_TREE_COMMAND_RE = re.compile(r"^tree\b(?:\s+\.|\s*$)")

# R4: sudo/time/nohup/command/env prefixes and VAR=val assignments decorate
# the front of a segment without changing what actually runs -- `sudo fd .`,
# `env FOO=1 fd .`, `time fd` must still count fd/tree as the leading
# command, not evade the ^fd/^tree anchor. `env` is included alongside the
# literal sudo|time|nohup|command list because `env FOO=1 fd .` is exactly
# this shape (env sets vars then execs its trailing argument list).
_LEADING_WRAPPER_WORD_RE = re.compile(r"^(?:sudo|time|nohup|command|env)\b\s*")
_LEADING_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s*")


def _shell_segments(text: str) -> list[str]:
    """Split `text` into individual shell command segments on `;`, `&&`,
    `||`, `|` -- the boundaries after which a NEW command begins. Used
    wherever a broad/scan pattern must be evaluated per-segment, not
    against the whole (possibly compound) line: a -maxdepth exception or a
    "wait loop" allowance for one segment must not leak into a sibling
    segment joined by one of these operators (R2/R3)."""
    return [seg.strip() for seg in _SHELL_SEGMENT_SPLIT_RE.split(text) if seg.strip()]


def _strip_leading_wrappers(segment: str) -> str:
    """Strip leading sudo/time/nohup/command/env words and VAR=val
    assignments (in any order/combination) so the leading-command check
    below sees the real command (R4)."""
    changed = True
    while changed:
        changed = False
        m = _LEADING_WRAPPER_WORD_RE.match(segment)
        if m:
            segment = segment[m.end() :]
            changed = True
            continue
        m = _LEADING_ASSIGNMENT_RE.match(segment)
        if m:
            segment = segment[m.end() :]
            changed = True
    return segment


def _bare_command_matches(line: str) -> bool:
    for segment in _shell_segments(line):
        segment = _strip_leading_wrappers(segment)
        if _FD_COMMAND_RE.match(segment) or _TREE_COMMAND_RE.match(segment):
            return True
    return False


def matches_broad_bash(line: str) -> bool:
    return (
        any(re.search(pattern, line) for pattern in BROAD_BASH_PATTERNS)
        or is_broad_find(line)
        or _bare_command_matches(line)
    )


# Commands that are safe orchestrators — they may have broad-looking args in --body/--message,
# but are never themselves filesystem scanners.
_SAFE_TOOL_RE = re.compile(
    r"^\s*(gh|git|npm|bun|node|uv|curl|wget|python(?:\d+(?:\.\d+)?)?|ruby|perl|cargo|go\s+run)\b"
)
_PYTHON_MODULE_OR_COMMAND_RE = re.compile(r"^\s*python(?:\d+(?:\.\d+)?)?\s+(-c|-m)\b")
HELPER_COMMAND_RE = re.compile(
    r"token-reduce-(?:adaptive|paths|snippet|structural)(?:\.(?:sh|py))?\b|qmd\s+search\b"
)
RG_OPTIONS_WITH_VALUE = {
    "-e",
    "--regexp",
    "-f",
    "--file",
    "-g",
    "--glob",
    "-t",
    "--type",
    "-T",
    "--type-not",
    "-m",
    "--max-count",
    "-A",
    "-B",
    "-C",
    "--max-filesize",
    "--max-columns",
    "--max-depth",
    "--threads",
    "--sort",
    "--sortr",
}
RG_PATTERN_OPTIONS_WITH_VALUE = {"-e", "--regexp", "-f", "--file"}


def _decision_fingerprint_source(data: dict[str, object]) -> str:
    """Stable, tool-agnostic fingerprint input for the F5 decision cache.

    R5 extends dedup to every block()/warn_and_allow() caller (Glob, Grep,
    Read, symlink guard -- not just Bash), so this can't be Bash's
    ``command`` string; it has to work for any tool_input shape.
    """
    tool_name = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input", {})
    try:
        tool_input_json = json.dumps(tool_input, sort_keys=True, default=str)
    except Exception:
        tool_input_json = str(tool_input)
    return f"{tool_name}:{tool_input_json}"


def _record_decision_for(data: dict[str, object], *, blocked: bool, stdout: str) -> None:
    """R5: cache this invocation's decision under (session, tool_use_id) so
    a second hook-wiring layer for the SAME tool call can replay it
    verbatim (main() checks this at the very top, before any other side
    effect). Called from block() and warn_and_allow() -- the only two
    outcomes a replay needs to reproduce; a plain non-broad allow needs no
    marker at all. A payload with no tool_use_id (e.g. a test harness, or
    some other caller) records nothing -- there is no per-call id to key
    on, so dedup for that call is simply not attempted.
    """
    tool_use_id = str(data.get("tool_use_id") or "")
    if not tool_use_id:
        return
    try:
        repo = repo_root()
        record_decision(
            repo,
            session_key(data),
            tool_use_id,
            _decision_fingerprint_source(data),
            blocked=blocked,
            stdout=stdout,
        )
    except Exception:
        pass


def block(
    reason: str,
    data: dict[str, object] | None = None,
    *,
    extra_meta: dict[str, object] | None = None,
) -> int:
    # F9: TOKEN_REDUCE_ENFORCE_MODE=warn downgrades every would-be block to a
    # telemetry-only warning instead of an actual exit-2 block. This
    # codifies, as a supported first-class mode, a hand-written and never-
    # committed escape hatch someone had already added at the deploy site
    # after an over-blocking incident (a wrapper that turned blocks into
    # stderr warnings). Normal mode (env unset/anything else) is unchanged.
    warn_mode = os.environ.get("TOKEN_REDUCE_ENFORCE_MODE") == "warn"
    # Compute the exact bytes/exit-code up front so both the real emission
    # below AND the R5 decision marker record the SAME actual outcome (a
    # replay must reproduce what really happened, not what the policy
    # nominally wanted before an F9 warn-mode downgrade).
    stdout_payload = "" if warn_mode else json.dumps({"decision": "block", "reason": reason}) + "\n"
    rc = 0 if warn_mode else 2

    if data is not None:
        repo = repo_root()
        tool_name = str(data.get("tool_name", "unknown"))
        tool_input = data.get("tool_input", {}) or {}
        meta: dict[str, object] = {}
        if isinstance(tool_input, dict):
            for key in ("command", "pattern", "path", "glob"):
                value = str(tool_input.get(key, "") or "")[:240]
                if value:
                    meta[key] = value
        meta["session_key"] = session_key(data)
        meta["reason"] = reason
        if extra_meta:
            meta.update(extra_meta)
        if warn_mode:
            meta["mode"] = "warn"
        # B4: cost-aware telemetry — log estimated tokens this block prevented
        command = str(meta.get("command", ""))
        if command:
            est = estimate_output_tokens(command)
            if est is not None:
                meta["estimated_output_tokens"] = est
        if not warn_mode:
            # In warn mode nothing was actually blocked, so there is no
            # "did the next tool call comply" question for post-block-
            # compliance tracking to answer -- recording it would falsely
            # flag the agent's very next (unrelated, allowed) tool call as
            # an escape/abandon.
            record_block(repo, tool_name, reason, meta.get("command"))  # type: ignore[arg-type]
        record_event(
            repo,
            event="hook_block",
            source="hook",
            tool=tool_name,
            # R6: warn mode never actually blocked anything -- status must
            # say so, or a consumer counting status=="blocked" is polluted
            # by decisions that were really just telemetry-only warnings.
            status="warn" if warn_mode else "blocked",
            meta=meta or None,
        )
        # R5: record the decision marker for EVERY block() caller (pending
        # gate, Glob, Grep, symlink guard, catastrophic, repeat-broad) so a
        # second hook-wiring layer for the same tool_use_id replays this
        # exact outcome instead of recomputing it.
        _record_decision_for(data, blocked=(rc == 2), stdout=stdout_payload)

    if stdout_payload:
        sys.stdout.write(stdout_payload)
    return rc


def warn_and_allow(
    data: dict[str, object],
    *,
    command: str,
    reason: str,
    attempt_count: int,
) -> int:
    """B3 first-attempt path: emit a warn event but allow the command through.

    The block message would have cost tokens on a failed attempt; we trade
    that for a single advisory event and trust the agent to switch to the
    helper next time. Repeat attempts then hit the hard-block branch.
    """
    repo = repo_root()
    est = estimate_output_tokens(command)
    rewrite = suggest_rewrite(command) or ""
    record_event(
        repo,
        event="hook_warn",
        source="hook",
        tool=str(data.get("tool_name", "unknown")),
        status="warn",
        meta={
            "command": command[:240],
            "reason": reason,
            "attempt_count": attempt_count,
            "estimated_output_tokens": est,
            "rewrite": rewrite[:200],
            "session_key": session_key(data),
        },
    )
    # R5: this decision incremented the broad-attempt counter (the caller
    # just called record_broad_attempt before reaching here) -- record a
    # marker so a second hook-wiring layer for the same tool_use_id
    # replays "allow" without incrementing the counter a second time.
    _record_decision_for(data, blocked=False, stdout="")
    return 0


def is_broad_glob(pattern: str) -> bool:
    if not pattern:
        return False
    p = pattern.lstrip("./")
    if p.startswith("**/"):
        return True
    if p.count("*") >= 2:
        return True
    if p.endswith("/**") or p.endswith("/**/*"):
        return True
    parts = p.split("/")
    return len(parts) > 1 and all(seg.startswith("*") for seg in parts[:2])


def is_exploratory_glob(pattern: str) -> bool:
    if not pattern:
        return False
    return any(char in pattern for char in "*?[")


def is_exploratory_grep(tool_input: dict[str, object], repo: Path) -> bool:
    path_value = str(tool_input.get("path", "") or "")
    glob_value = str(tool_input.get("glob", "") or "")

    # Broad glob filter always exploratory
    if any(char in glob_value for char in "*?["):
        return True

    # No path or root path = exploratory
    if not path_value or path_value in {".", "./"}:
        return True

    candidate = (repo / path_value).resolve()
    if candidate.exists():
        if candidate.is_dir():
            return True
        # It's a specific file — allow files_with_matches on exact files
        return False

    # Unknown path: exploratory if no extension (likely a dir name)
    return "." not in Path(path_value).name


def rg_paths(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if not tokens or tokens[0] != "rg":
        return []

    paths: list[str] = []
    saw_pattern = False
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            tail = tokens[i + 1 :]
            if not saw_pattern and tail:
                saw_pattern = True
                tail = tail[1:]
            paths.extend(tail)
            break

        if token.startswith("-"):
            if token in RG_OPTIONS_WITH_VALUE:
                if token in RG_PATTERN_OPTIONS_WITH_VALUE:
                    saw_pattern = True
                i += 2
                continue
            if (
                token.startswith("--glob=")
                or token.startswith("--regexp=")
                or token.startswith("--type=")
                or token.startswith("--type-not=")
                or token.startswith("--file=")
                or token.startswith("-g")
                or token.startswith("-e")
            ):
                if token.startswith("--regexp=") or token.startswith("--file=") or token.startswith("-e") or token.startswith("-f"):
                    saw_pattern = True
                i += 1
                continue
            i += 1
            continue

        if not saw_pattern:
            saw_pattern = True
        else:
            paths.append(token)
        i += 1

    return paths


def is_exploratory_rg(command: str, repo: Path) -> bool:
    first = command.strip()
    if not first.startswith("rg "):
        return False
    if re.search(r"(?:^|\s)(?:-g|--glob)(?:\s|=)", first):
        return False
    if re.search(r"(?:^|\s)(?:--files|--files-with-matches|--files-without-match)\b", first):
        return True

    paths = rg_paths(first)
    if not paths:
        return True

    for raw_path in paths:
        if raw_path in {".", "./"}:
            return True
        if any(ch in raw_path for ch in "*?["):
            return True

        candidate = (repo / raw_path).resolve()
        if candidate.exists():
            if candidate.is_dir():
                return True
            continue

        if "." not in Path(raw_path).name:
            return True

    return False


def uv_run_inner_command(command: str) -> str:
    """Return the command wrapped by `uv run`, or empty when not applicable."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""
    if len(tokens) < 3 or tokens[0] != "uv" or tokens[1] != "run":
        return ""

    # Skip common uv-run flags before the actual command. Keep this conservative:
    # unknown flags with values are skipped one token at a time until we find a
    # command-looking token such as python, pytest, or a script path.
    options_with_value = {
        "--with",
        "--with-editable",
        "--from",
        "--project",
        "--directory",
        "--env-file",
        "--index-url",
        "--extra-index-url",
        "--python",
    }
    i = 2
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            i += 1
            break
        if token in options_with_value:
            i += 2
            continue
        if token.startswith("--") and "=" in token:
            i += 1
            continue
        if token.startswith("-"):
            i += 1
            continue
        break
    return shlex.join(tokens[i:]) if i < len(tokens) else ""


def uv_run_needs_scan(command: str) -> bool:
    """True when a safe-looking uv launcher wraps a command we must inspect."""
    inner = uv_run_inner_command(command)
    if not inner:
        return False
    if _PYTHON_MODULE_OR_COMMAND_RE.match(inner):
        return True
    return matches_any_broad_pattern(inner)


def helper_required_reason() -> str:
    hint = discovery_hint()
    return (
        f"Broad/exploratory discovery. Run {hint} first, or delegate directly: "
        'Agent(subagent_type="Explore", ...) for read-only search, or '
        '"builder"/model="sonnet" for implementation -- have it return '
        "conclusions + evidence instead of reading everything yourself. "
        "Targeted Grep, Glob, and Read on an exact, known path are not gated by this."
    )


# Leading commands that are session/process control, tmux inspection, or message
# relays — they never scan the repo, so a pending discovery prompt must not gate
# them. Matched against the first token of the first line.
_NON_DISCOVERY_LEADING_RE = re.compile(
    r"^(?:tmux|session-handoff|session-send|session-handoff-send|sleep|wait|kill|"
    r"pkill|jobs|disown|caffeinate|clear|reset)\b"
)
# Wait/poll loops: `until/while/for ... ; do sleep N; done`. Allowed only when a
# sleep is present (a genuine poll) and the loop carries no repo-scan (checked
# separately), so a `while read ...; do rg ...; done` discovery loop can't slip
# through.
_WAIT_LOOP_LEADING_RE = re.compile(r"^(?:until|while|for)\b")


def is_non_discovery_command(command: str, repo: Path) -> bool:
    """True for command shapes that clearly aren't repo discovery — session/tmux
    control, message relays, and wait/poll loops — so the pending-discovery gate
    should let them through without a fresh helper call.

    A repo-scan anywhere in the command disqualifies it, so this can never be
    used to smuggle a scan (e.g. ``tmux new-session 'rg -R .'``) past the gate.
    """
    lines = [
        line_.rstrip("\\").strip()
        for line_ in command.split("\n")
        if line_.strip() and line_.strip() != "\\"
    ]
    if not lines:
        return False

    # Any actual scan pattern disqualifies the whole command. Broad-bash and
    # coverage patterns already match anywhere in a line (so `grep -R`/`find .`
    # hidden inside a tmux arg is caught).
    #
    # F3: match against quote-aware surfaces, not the raw line, so inert
    # quoted data (echo/printf payloads, JSON, commit messages) can't be
    # mistaken for a scan -- but a quoted argument that a command-executor
    # (tmux new-session/send-keys, sh/bash -c, eval, xargs, ...) actually
    # runs is still recursed into and checked for real. command_scan_surfaces
    # emits the recursed body as its OWN surface (leader stripped), so
    # is_exploratory_rg's line-leading `rg` check sees "rg foo ." directly
    # for e.g. `tmux new-session -d 'rg foo .'` -- no separate blunt
    # "rg anywhere" catch-all needed (a prior version of this check used one
    # and it false-positived on unrelated text like `which rg fd rtk`).
    #
    # R3: matches_broad_bash/is_exploratory_rg are evaluated PER SHELL
    # SEGMENT, not against the whole surface -- otherwise a scan smuggled
    # after a wait-loop's leading `sleep` (e.g.
    # `while true; do sleep 5; rg -n foo .; done`) is invisible to
    # is_exploratory_rg (only fires on a segment-leading "rg ") and slips
    # through, since the WHOLE surface starts with "while", not "rg".
    # matches_any_broad_pattern stays on the whole (unsegmented) surface:
    # is_xargs_cat_chain's pattern needs to see the literal `|` that
    # segment-splitting would otherwise consume as a delimiter.
    for line in lines:
        for surface in command_scan_surfaces(line):
            if matches_any_broad_pattern(surface):
                return False
            for segment in _shell_segments(surface):
                if matches_broad_bash(segment):
                    return False
                if is_exploratory_rg(segment, repo):
                    return False

    first = lines[0]
    if _NON_DISCOVERY_LEADING_RE.match(first):
        return True
    if _WAIT_LOOP_LEADING_RE.match(first) and re.search(r"\bsleep\b", " ".join(lines)):
        return True
    return False


def classify_bash_command(lines: list[str], repo: Path) -> tuple[bool, bool, bool, bool]:
    """Quote-aware broad/catastrophic classification for a Bash command's
    lines. Returns (catastrophic, broad_hit, rg_hit, coverage_hit).

    Shared by the pending-gate (F2) and non-pending paths, plus the
    helper-command continuation-line (N2) check, so all three apply
    identical policy to identical (quote-aware, F3) input.
    """
    surfaces: list[str] = []
    for line in lines:
        surfaces.extend(command_scan_surfaces(line))

    # R2: catastrophic/broad/rg-hit are evaluated PER SHELL SEGMENT, not
    # against the whole (possibly compound) surface -- otherwise a
    # -maxdepth exception or catastrophic-root hit on one segment leaks
    # into a sibling segment joined by ;/&&/||/| (confirmed live:
    # `find /a/b/c -maxdepth 1; find /d/e/f -name '*.py'` classified as
    # not-broad, because the FIRST find's -maxdepth was found anywhere in
    # the line and treated as satisfying the whole thing, masking the
    # SECOND find's genuinely-unbounded scan). coverage_hit
    # (matches_any_broad_pattern) is intentionally left on the WHOLE
    # surface: is_xargs_cat_chain's pattern needs to see the literal `|`
    # that segment-splitting would otherwise consume as a delimiter.
    segments: list[str] = []
    for surface in surfaces:
        segments.extend(_shell_segments(surface))

    catastrophic = any(is_catastrophic(s) for s in segments)
    broad_hit = any(matches_broad_bash(s) for s in segments)
    # command_scan_surfaces emits the recursed executor body as its own
    # leader-free surface, so is_exploratory_rg's line-leading `rg` check
    # catches e.g. `tmux new-session -d 'rg -n bar .'` directly via the
    # surface "rg -n bar ." -- no separate "rg anywhere" catch-all needed.
    rg_hit = any(is_exploratory_rg(s, repo) for s in segments)
    coverage_hit = any(matches_any_broad_pattern(s) for s in surfaces)
    return catastrophic, broad_hit, rg_hit, coverage_hit


def find_symlink_guard(command: str) -> str | None:
    """F6: POSIX `find` does not descend into a symlinked root by default,
    so `find <symlink-dir>` silently returns nothing instead of erroring --
    a confident-wrong-answer footgun (verified live: bare `find` on a
    symlinked root prints 0 lines / rc=0; the same path with a trailing
    slash prints the real listing).

    Detect it and fail loud with a precise, actionable message instead of
    letting the caller draw a false conclusion from empty output. This is a
    correctness guard, not a helper-required policy, so callers must NOT
    count it against the broad-attempt counter.

    F3 note: must scan quote-aware surfaces, not raw lines -- a `find
    <path>` substring inside inert quoted data (echo/JSON payloads) is
    real path text on the filesystem, so an ungated raw-line scan here can
    fire a "confident" symlink warning for the wrong reason (matched
    coincidentally-real text inside a quote, not an actual find
    invocation). Verified live: an echoed JSON blob naming a path that is
    a real symlink on the host tripped this guard before the fix.

    R1: root extraction is via FIND_ROOT_ARG_RE, imported from
    command_rewrites (was a byte-identical private copy in this module;
    now one shared, global-opts-tolerant regex). R7(a): cheap substring
    pre-filter before any quote-stripping/regex work, plus a single lstat
    (not the two separate os.path.islink/os.path.isdir convenience calls,
    which independently re-stat) for the symlink+directory check.

    C3: `-H` (follow symlinks named on the command line) and `-L` (follow
    all symlinks) both make `find` descend a symlinked root -- so blocking
    `find -H <symlink>` / `find -L <symlink>` is an infinite advice loop
    (the block message's own recommended remedy is exactly what the caller
    already did). `-P` (never follow, the default) does NOT change
    anything, so the guard still applies with -P or no option at all.
    """
    if "find" not in command:
        return None
    for line in command.split("\n"):
        for surface in command_scan_surfaces(line):
            if "find" not in surface:
                continue
            match = FIND_ROOT_ARG_RE.search(surface)
            if not match:
                continue
            # The global-options text is everything the regex consumed
            # between "find" and the root capture -- check THAT span
            # specifically (not the whole match, which also contains the
            # root) so a coincidental "-H"/"-L"-looking substring inside
            # the path itself can't produce a false skip.
            opts_text = surface[match.start() : match.start(1)]
            if re.search(r"-[HL]\b", opts_text):
                continue
            path = match.group(1)
            if not path.startswith("/"):
                continue
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISLNK(st.st_mode):
                continue
            try:
                target_st = os.stat(path)
            except OSError:
                continue
            if stat.S_ISDIR(target_st.st_mode):
                return (
                    f"find root '{path}' is a symlink; find will not descend it "
                    f"and returns empty. Use 'find {path}/' (trailing slash) or -H/-L."
                )
    return None


def handle_broad_bash(
    data: dict[str, object],
    repo: Path,
    lines: list[str],
    first_line: str,
    *,
    pending: bool,
) -> int:
    """Classify a Bash command's lines and apply the broad/catastrophic
    policy.

    R5: dedup (F5) is no longer this function's concern -- it now happens
    centrally at the very top of main(), before this function (or anything
    else with a side effect) is ever reached for a duplicate invocation.
    Decision recording likewise moved into block()/warn_and_allow()
    themselves, so it covers every caller of those two functions (Glob,
    Grep, Read, symlink guard), not just this Bash-specific path. This
    function is now pure policy.

    Used by both the pending (F2) and non-pending gate paths so they share
    one policy: catastrophic -> hard block; broad/exploratory-rg/coverage
    hit -> warn-once-then-block while NOT pending, or block immediately
    while pending (no warn-grace, since the pending gate's whole purpose is
    "helper first"); anything else -> allow.
    """
    catastrophic, broad_hit, rg_hit, coverage_hit = classify_bash_command(lines, repo)
    if not (broad_hit or rg_hit or coverage_hit):
        return 0

    if catastrophic:
        msg = format_block_message(
            reason="catastrophic scan",
            command=first_line,
            helper_hint=discovery_hint(),
        )
        return block(msg, data, extra_meta={"policy": "catastrophic"})

    if pending:
        return block(helper_required_reason(), data, extra_meta={"policy": "pending_gate"})

    # B3 first attempt → warn + measure, allow. B3 repeat → block.
    sk = session_key(data)
    count = broad_attempt_count(repo, sk)
    if count == 0:
        record_broad_attempt(repo, sk)
        return warn_and_allow(
            data,
            command=first_line,
            reason="broad bash scan" if broad_hit else "exploratory rg scan",
            attempt_count=1,
        )

    record_broad_attempt(repo, sk)
    msg = format_block_message(
        reason=f"broad scan x{count + 1} this session",
        command=first_line,
        helper_hint=discovery_hint(),
    )
    return block(msg, data, extra_meta={"policy": "repeat_broad", "attempt_count": count + 1})


def _record_hook_error(stage: str, exc: Exception, data: object = None) -> None:
    """Best-effort fail-open telemetry. Must NEVER raise: repo_root()/record_event()
    are themselves the kind of call that can throw during a partial/broken deploy,
    so every step here is individually guarded. A silent no-op is preferable to a
    telemetry error re-wedging the very tool call we just decided to allow."""
    try:
        repo = repo_root()
        meta: dict[str, object] = {"stage": stage, "error": str(exc)[:240]}
        try:
            if isinstance(data, dict):
                meta["session_key"] = session_key(data)
        except Exception:
            pass
        record_event(
            repo,
            event="hook_error",
            source="hook",
            tool="enforce-token-reduce-first",
            status="error",
            meta=meta,
        )
    except Exception:
        pass


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        _record_hook_error("stdin_json", exc)
        return 0

    # R5: dedup FIRST, before ANY other side effect (post-block tracking,
    # telemetry, counters) -- moved here (was inside handle_broad_bash,
    # Bash-only) because a second hook-wiring layer invoked for the SAME
    # tool call must touch NOTHING: not consume_block (which would eat the
    # marker the FIRST invocation's block() just wrote via record_block,
    # causing a spurious post_block_escape/abandon classification for the
    # very call that WAS the block), not record_event, not any counter.
    # Only tool_use_id-bearing payloads are checked; a hit replays the
    # exact stdout bytes and exit code the first invocation produced.
    try:
        tool_use_id = str(data.get("tool_use_id") or "")
        if tool_use_id:
            repo = repo_root()
            cached = recent_decision(
                repo, session_key(data), tool_use_id, _decision_fingerprint_source(data)
            )
            if cached is not None:
                stdout = cached.get("stdout") or ""
                if stdout:
                    sys.stdout.write(stdout)
                return 2 if cached.get("blocked") else 0
    except Exception as exc:
        _record_hook_error("dedup", exc, data)

    # Post-block compliance tracking (best-effort telemetry; must never wedge a
    # tool call, so it is guarded independently of the enforcement body below).
    try:
        repo = repo_root()
        last_block = consume_block(repo)
        if last_block is not None:
            tool_name = data.get("tool_name", "unknown")
            tool_input = data.get("tool_input", {}) or {}
            command = ""
            if tool_name == "Bash" and isinstance(tool_input, dict):
                command = str(tool_input.get("command", "")).split("\n")[0]
            is_helper = bool(HELPER_COMMAND_RE.search(command)) if command else False
            if is_helper:
                record_event(
                    repo,
                    event="post_block_compliance",
                    source="hook",
                    tool="enforce-token-reduce-first",
                    status="ok",
                    meta={
                        "blocked_tool": last_block.get("tool"),
                        "blocked_reason": last_block.get("reason"),
                        "next_tool": tool_name,
                        "session_key": session_key(data),
                    },
                )
            else:
                # If the agent is attempting another broad-ish tool right after a block,
                # classify as escape. If it's an innocent tool (Read on a known file,
                # Edit, etc.), classify as abandon/non_discovery.
                is_broad_attempt = False
                if tool_name == "Bash" and isinstance(tool_input, dict):
                    cmd = str(tool_input.get("command", ""))
                    lines = [line_.rstrip("\\").strip() for line_ in cmd.split("\n") if line_.strip() and line_.strip() != "\\"]
                    # R7(c): quote-aware surfaces, not raw lines -- this is
                    # telemetry classification only (never a gate decision),
                    # but it should apply the same F3 quote-handling as
                    # everywhere else so it isn't fooled by inert quoted
                    # text the same way the earlier raw-line version was.
                    surfaces = [s for line_ in lines for s in command_scan_surfaces(line_)]
                    is_broad_attempt = any(matches_broad_bash(s) for s in surfaces) or any(
                        is_exploratory_rg(s, repo) for s in surfaces
                    )
                if tool_name == "Glob" and isinstance(tool_input, dict):
                    pattern = str(tool_input.get("pattern", ""))
                    is_broad_attempt = is_broad_glob(pattern) or is_exploratory_glob(pattern)
                if tool_name == "Grep" and isinstance(tool_input, dict):
                    is_broad_attempt = is_exploratory_grep(tool_input, repo)

                event_type = "post_block_escape" if is_broad_attempt else "post_block_abandon"
                record_event(
                    repo,
                    event=event_type,
                    source="hook",
                    tool="enforce-token-reduce-first",
                    status="ok" if not is_broad_attempt else "blocked",
                    meta={
                        "blocked_tool": last_block.get("tool"),
                        "blocked_reason": last_block.get("reason"),
                        "next_tool": tool_name,
                        "session_key": session_key(data),
                    },
                )
    except Exception as exc:
        _record_hook_error("post_block", exc, data)

    try:
        tool_name = data.get("tool_name")
        tool_input = data.get("tool_input", {}) or {}
        repo = repo_root()
        pending = is_pending(repo, session_key(data))

        # R7(a): Bash handling unified into one call site (was duplicated
        # under the pending and non-pending branches separately), so
        # find_symlink_guard is checked exactly once per invocation instead
        # of once per branch.
        if tool_name == "Bash":
            command = tool_input.get("command", "") or ""
            first_line = command.split("\n")[0]

            guard_msg = find_symlink_guard(command)
            if guard_msg:
                return block(guard_msg, data, extra_meta={"policy": "symlink_root_guard"})

            if pending:
                # C2: the helper must LEAD a shell segment of the first
                # line, not merely appear anywhere in it via a bare
                # .search() -- otherwise `token-reduce-paths auth && find /
                # -name x` ran the scan for real (its rest_lines was empty:
                # everything was on ONE line, so the N2 continuation check
                # below never even saw the `find /` segment), and `echo
                # token-reduce-paths; find / -name x` was credited as
                # compliance without the helper ever having run at all.
                # _strip_leading_wrappers reuses the same wrapper-stripping
                # _bare_command_matches uses, so `uv run token-reduce-paths
                # ...` (and other wrapped invocations) still count.
                first_line_segments = _shell_segments(first_line)
                leading_segment = (
                    _strip_leading_wrappers(first_line_segments[0]) if first_line_segments else ""
                )
                if HELPER_COMMAND_RE.search(leading_segment):
                    # N2 fix: classify every OTHER segment of this line
                    # (not just continuation lines) for broad patterns
                    # before allowing/clearing pending -- any hit blocks.
                    rest_segments = first_line_segments[1:]
                    rest_lines = [line_.strip() for line_ in command.split("\n")[1:] if line_.strip() and line_.strip() != "\\"]
                    _, rest_broad, rest_rg, rest_coverage = classify_bash_command(
                        rest_segments + rest_lines, repo
                    )
                    if rest_broad or rest_rg or rest_coverage:
                        return block(helper_required_reason(), data)
                    # F1 follow-up: the helper actually ran clean -- clear this
                    # session's pending marker so the very next Grep/Glob/Read
                    # isn't gated again (previously pending survived a
                    # compliant helper call and kept blocking follow-ups).
                    clear_pending(repo, session_key(data))
                    return 0
                # Session/tmux control, message relays, and wait/poll loops are
                # not repo discovery — never gate them (they carry no scan, which
                # is_non_discovery_command verifies). This is the fix for the gate
                # over-blocking tmux capture-pane, session-handoff send, and
                # `until ...; do sleep; done` wait loops.
                if is_non_discovery_command(command, repo):
                    return 0
                # F2: apply the SAME broad/catastrophic classification as the
                # non-pending path instead of a blanket default-block, so
                # targeted commands (which, ls <dir>, stat, date, cat <file>)
                # pass while pending and only genuine scans still block.
                lines = [line_.rstrip("\\").strip() for line_ in command.split("\n") if line_.strip() and line_.strip() != "\\"]
                lines.extend(
                    inner for inner in (uv_run_inner_command(line) for line in list(lines)) if inner
                )
                return handle_broad_bash(data, repo, lines, first_line, pending=True)

            # Non-pending. Safe orchestrators: may carry broad-looking
            # strings as arguments. N1 fix: python3 -c/-m must fall through
            # to coverage checks; only plain `python3 script.py` is safe.
            if _PYTHON_MODULE_OR_COMMAND_RE.match(first_line) or uv_run_needs_scan(first_line):
                pass  # fall through to broad-pattern checks below
            elif _SAFE_TOOL_RE.match(first_line):
                return 0
            # Check all lines — broad scans may be on continuation lines
            lines = [line_.rstrip("\\").strip() for line_ in command.split("\n") if line_.strip() and line_.strip() != "\\"]
            lines.extend(
                inner for inner in (uv_run_inner_command(line) for line in list(lines)) if inner
            )
            return handle_broad_bash(data, repo, lines, first_line, pending=False)

        if pending:
            # F10: apply the SAME targeted-vs-exploratory classification the
            # non-pending path already uses for Glob/Grep, instead of a
            # blanket block. Before this fix, `Grep(path="/exact/file.py",
            # pattern="foo")` -- an ordinary, specific grep on a known file --
            # was unconditionally blocked while a session's prompt-triggered
            # "pending" marker was set, regardless of how targeted the call
            # actually was (Read already got this treatment; Glob/Grep did
            # not). Opus 5.5 guidance: targeted work (a known file, a
            # specific grep) must never be blocked -- only genuinely
            # exploratory Glob/Grep calls should still gate on discovery.
            if tool_name == "Read":
                file_path = str(tool_input.get("file_path", "") or "")
                if file_path.startswith("/") and not any(c in file_path for c in "*?["):
                    return 0
                return block(helper_required_reason(), data)
            if tool_name == "Glob":
                pattern = tool_input.get("pattern", "") or ""
                if is_broad_glob(pattern) or is_exploratory_glob(pattern):
                    return block(helper_required_reason(), data)
                return 0
            if tool_name == "Grep":
                if is_exploratory_grep(tool_input, repo):
                    return block(helper_required_reason(), data)
                return 0
            return 0

        if tool_name == "Glob":
            pattern = tool_input.get("pattern", "") or ""
            if is_broad_glob(pattern) or is_exploratory_glob(pattern):
                return block(
                    f"Blocked exploratory Glob pattern. Use {discovery_hint()} for a path-only kickoff, "
                    'or delegate a multi-file sweep to Agent(subagent_type="Explore", ...), '
                    "then switch to Read on an exact file path.",
                    data,
                )
            return 0

        if tool_name == "Grep" and is_exploratory_grep(tool_input, repo):
            return block(
                f"Blocked exploratory Grep before helper kickoff. Run {discovery_hint()} first, "
                'or delegate a multi-file sweep to Agent(subagent_type="Explore", ...), '
                "then use Grep on an exact file path or a much narrower scope.",
                data,
            )

        return 0
    except Exception as exc:
        # Fail-open on any runtime error. Uses best-effort telemetry so a broken
        # repo_root()/record_event() can't turn the fail-open back into a crash.
        _record_hook_error("runtime", exc, data)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        # Preserve the intended exit code, including 2 for a deliberate block.
        raise
    except BaseException:
        # Absolute last resort: nothing should escape main(), but if anything
        # does, never let it become a block. Drain stdin and allow.
        try:
            sys.stdin.read()
        except Exception:
            pass
        raise SystemExit(0)
