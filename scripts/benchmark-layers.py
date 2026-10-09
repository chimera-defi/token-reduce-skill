#!/usr/bin/env python3
"""Per-layer on/off benchmark: real output sizes of a fixed command set.

Run with:
  uv run --no-project --with tiktoken scripts/benchmark-layers.py [--repo PATH ...] [--json]

Tokens are tiktoken cl100k counts of the text an agent would actually read
(a stable proxy, not Claude's tokenizer). Headroom is read from the live proxy
/stats (its own counters over real traffic). Nothing here edits host config.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count(text: str) -> int:
        return len(_ENC.encode(text, disallowed_special=()))
except ImportError:  # chars/4 fallback is labelled in the output
    _ENC = None

    def count(text: str) -> int:
        return len(text) // 4


ROOT = Path(__file__).resolve().parent.parent
PATHS = ROOT / "scripts" / "token-reduce-paths.sh"
DEFAULT_REPOS = [ROOT, Path("/home/agents/workspace/SharedStake-ui")]

# Read-only commands whose output an agent routinely reads. {rtk} marks wrappers.
RTK_CMDS = [
    "git log -n 40",
    "git diff HEAD~5",
    "git status",
    "ls -la",
    "rg -n def .",
    "git log -n 15 --stat",
]
# topic words -> a path substring that must appear in the top results.
SEARCH_TASKS = [
    ("hook enforce fail open", "enforce-token-reduce-first"),
    ("dependency health update", "dependency-health"),
    ("benchmark composite stack", "benchmark-composite"),
    ("session layer policy status", "token_reduce_layers"),
    ("cost ledger spend", "cost_ledger"),
    ("release change gate", "release-change-gate"),
    ("headroom proxy compression", "headroom"),
    ("normalize session key state", "token_reduce_state"),
    ("adaptive tiering profile", "adaptive"),
]
RG_NAIVE = "rg -n -i {words} ."


def run(argv: list[str] | str, cwd: Path, env: dict | None = None, shell: bool = False, timeout: int = 20):
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=cwd, shell=shell, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
            env={**os.environ, **(env or {})},
        )
    except subprocess.TimeoutExpired:
        return "", timeout * 1000, 124
    return proc.stdout + proc.stderr, int((time.monotonic() - start) * 1000), proc.returncode


def bench_rtk(repo: Path) -> list[dict]:
    if not shutil.which("rtk"):
        return []
    rows = []
    for cmd in RTK_CMDS:
        raw, raw_ms, raw_rc = run(cmd, repo, shell=True)
        wrapped, rtk_ms, rtk_rc = run(f"rtk {cmd}", repo, shell=True)
        if 124 in (raw_rc, rtk_rc):
            continue  # a timed-out case has no honest token count
        rows.append({
            "layer": "rtk", "repo": repo.name, "case": cmd, "off_tokens": count(raw), "on_tokens": count(wrapped),
            "off_ms": raw_ms, "on_ms": rtk_ms, "same_exit": raw_rc == rtk_rc,
        })
    return rows


def bench_search(repo: Path) -> list[dict]:
    rows = []
    helper = repo / "scripts" / "token-reduce-paths.sh"
    if repo != ROOT:  # helper is a repo-local script; run ours against the other repo
        helper = PATHS
    for words, expect in SEARCH_TASKS:
        if repo != ROOT:
            continue  # expected files only exist in this repo
        naive, naive_ms, _ = run(RG_NAIVE.format(words=" ".join(f"-e {w}" for w in words.split())), repo, shell=True)
        for mode, env in (("qmd", {"TOKEN_REDUCE_LAYER_SEARCH_QMD": "on"}), ("rg_fallback", {"TOKEN_REDUCE_LAYER_SEARCH_QMD": "off"})):
            out, ms, _ = run([str(helper), *words.split()], repo, env=env)
            # qmd hits look like "#id,score,qmd://repo/path"; the brain-hint line starts "# brain-hint"
            paths = [ln.rsplit(",", 1)[-1] if ln.startswith("#") and "," in ln else ln
                     for ln in out.splitlines() if ln and not ln.startswith("# ")]
            rows.append({
                "layer": f"search/{mode}", "repo": repo.name, "case": words,
                "off_tokens": count(naive), "on_tokens": count(out), "off_ms": naive_ms, "on_ms": ms,
                "hit_top5": any(expect in p for p in paths[:5]),
            })
    return rows


def bench_memory_hint() -> dict:
    out, ms, _ = run(["python3", str(ROOT / "scripts" / "brain_hint.py"), "hook enforce fail open"], ROOT)
    return {"layer": "memory_hint", "case": "one hint line", "on_tokens": count(out), "on_ms": ms, "off_tokens": 0}


def bench_context_audit() -> dict:
    out, ms, rc = run(["python3", str(ROOT / "scripts" / "context_audit.py")], ROOT, timeout=180)
    return {"layer": "context_audit", "case": "report on load", "on_tokens": count(out), "on_ms": ms, "off_tokens": 0, "exit": rc}


def headroom_live() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/stats", timeout=3) as r:
            s = json.load(r)["summary"]
    except Exception as exc:  # noqa: BLE001 - report, never fail the benchmark
        return {"layer": "headroom", "available": False, "reason": str(exc)[:80]}
    c, cost = s["compression"], s["cost"]
    return {
        "layer": "headroom", "available": True, "requests": s["api_requests"],
        "tokens_before": c["total_tokens_before"], "tokens_removed": c["total_tokens_removed"],
        "removed_pct": round(100 * c["total_tokens_removed"] / max(c["total_tokens_before"], 1), 2),
        "measured_saved_usd": cost["measured_saved_usd"], "cache_discount_usd": cost["provider_cache_discount_usd"],
    }


def summarize(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["layer"], []).append(r)
    out = {}
    for layer, rs in groups.items():
        off, on = sum(r["off_tokens"] for r in rs), sum(r["on_tokens"] for r in rs)
        out[layer] = {
            "cases": len(rs), "off_tokens": off, "on_tokens": on,
            "saved_pct": round(100 * (off - on) / off, 1) if off else None,
            "off_ms": sum(r.get("off_ms", 0) for r in rs), "on_ms": sum(r.get("on_ms", 0) for r in rs),
        }
        if any("hit_top5" in r for r in rs):
            out[layer]["quality_hits"] = f"{sum(r['hit_top5'] for r in rs)}/{len(rs)}"
        if any("same_exit" in r for r in rs):
            out[layer]["same_exit"] = all(r["same_exit"] for r in rs)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", action="append", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    wanted = args.repo or DEFAULT_REPOS
    repos = [r for r in wanted if r.is_dir()]
    for missing in set(wanted) - set(repos):
        print(f"note: skipping missing repo {missing}", file=__import__("sys").stderr)
    rows: list[dict] = []
    for repo in repos:
        rows += bench_rtk(repo) + bench_search(repo)
    singles = [bench_memory_hint(), bench_context_audit(), headroom_live()]
    result = {
        "tokenizer": "tiktoken cl100k_base" if _ENC else "chars/4 fallback",
        "summary": summarize(rows), "rows": rows, "singles": singles,
    }
    if args.json:
        print(json.dumps(result, indent=1))
        return 0
    print(f"tokenizer: {result['tokenizer']}")
    for layer, s in result["summary"].items():
        print(f"{layer:18} cases={s['cases']:2} off={s['off_tokens']:>8} on={s['on_tokens']:>8} saved={s['saved_pct']}%"
              f" ms {s['off_ms']}->{s['on_ms']}" + (f" quality={s['quality_hits']}" if "quality_hits" in s else "")
              + (f" same_exit={s['same_exit']}" if "same_exit" in s else ""))
    for s in singles:
        print({k: v for k, v in s.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
