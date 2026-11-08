#!/usr/bin/env python3
"""PreToolUse hook: hint when `find <symlinked dir>` (no trailing slash) returns nothing."""
import json, os, re, shlex, sys


def expand(p):
    p = re.sub(r"^\$\{?HOME\}?(?=/|$)", os.environ.get("HOME", ""), p)
    return os.path.expanduser(p) if p.startswith("~") else p


def segments(cmd):
    lex = shlex.shlex(re.sub(r"\$\(|`", " ; ", cmd), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    seg = []
    for t in lex:
        if set(t) <= set(";&|()"):
            yield seg
            seg = []
        else:
            seg.append(t)
    yield seg


def check(cmd):
    cmd = re.sub(r"^\s*rtk\s+(proxy\s+)?", "", cmd)
    for seg in segments(cmd):
        for i, t in enumerate(seg[1:-1], 1):  # recurse into `bash -c '...'`
            if t == "-c" and os.path.basename(seg[i - 1]) in ("bash", "sh", "zsh"):
                inner = check(seg[i + 1])
                if inner:
                    return inner
        if "find" not in seg or any(a in ("-L", "-H", "-follow") for a in seg):
            continue
        for a in seg[seg.index("find") + 1:]:
            if a.startswith(("-", "(", "!")):
                break
            p = expand(a)
            if not p.endswith("/") and os.path.islink(p) and os.path.isdir(p):
                msg = (f"find hint: '{a}' is a symlink to a directory; find does not descend it and "
                       f"returns nothing. Use '{a}/' (trailing slash) or find -L.")
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}


try:
    data = json.load(sys.stdin)
    if data.get("tool_name") == "Bash":
        out = check(str((data.get("tool_input") or {}).get("command", "")))
        if out:
            print(json.dumps(out))
except BaseException:
    pass
sys.exit(0)
