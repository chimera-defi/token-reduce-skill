#!/usr/bin/env python3
"""PreToolUse hook: hint when `find <symlinked dir>` (no trailing slash) returns nothing."""
import json, os, re, shlex, sys


def expand(p):
    p = re.sub(r"^\$\{?HOME\}?(?=/|$)", lambda m: os.environ.get("HOME", ""), p)
    return os.path.expanduser(p) if p.startswith("~") else p


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n.*?\n\s*\2[ \t]*(?=\n|$)", re.S)


def segments(cmd):
    cmd = HEREDOC.sub(lambda m: m.group(3), cmd)  # heredoc bodies are data, not commands
    lex = shlex.shlex(re.sub(r"\$\(|`|\n", " ; ", cmd), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    seg = []
    for t in lex:
        if set(t) <= set(";&|()"):
            yield seg
            seg = []
        else:
            seg.append(t)
    yield seg


LEAD = ("rtk", "proxy", "sudo", "xargs", "env", "time", "nice", "command", "timeout")


def check(cmd):
    cmd = re.sub(r"^\s*rtk\s+(proxy\s+)?", "", cmd)
    for seg in segments(cmd):
        for i, t in enumerate(seg[1:-1], 1):  # recurse into `bash -c '...'`
            if t == "-c" and os.path.basename(seg[i - 1]) in ("bash", "sh", "zsh"):
                inner = check(seg[i + 1])
                if inner:
                    return inner
        i = next((i for i, t in enumerate(seg) if os.path.basename(t) == "find"
                  and (i == 0 or seg[i - 1] in LEAD or seg[i - 1].isdigit() or "=" in seg[i - 1])), None)
        if i is None or any(a in ("-L", "-H", "-follow") for a in seg):
            continue
        for a in seg[i + 1:]:
            if a.startswith(("-", "(", "!")):
                break
            p = expand(a)
            if not p.endswith("/") and os.path.islink(p) and os.path.isdir(p):
                msg = (f"find hint: '{a}' is a symlink to a directory; find does not descend it, so "
                       f"-name/-type tests find nothing. Use '{a}/' (trailing slash) or find -L.")
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
