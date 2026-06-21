"""Track A ranking helper.

Re-orders candidate paths produced by ``token-reduce-paths.sh`` /
``token-reduce-search.sh`` using:

- A1 git-recency log-decay over a 90-day window
- A2 symbol-match boost (def / class / function / shell / TS)
- A3 path-relevance demotion (vendor, dist, tests, fixtures, ...)
- A4 query expansion + stopword pruning + bigrams
- A5 click-through learning prior built from telemetry events
"""
from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so",
    "for", "of", "to", "in", "on", "at", "by", "from", "into", "out",
    "with", "as", "is", "are", "be", "was", "were", "this", "that",
    "these", "those", "it", "we", "you", "they", "i", "me", "my",
    "our", "us", "your", "he", "she", "him", "her", "do", "does",
    "did", "can", "could", "should", "would", "will", "shall", "may",
    "might", "must", "what", "which", "who", "whom", "whose", "when",
    "where", "why", "how", "find", "look", "looking", "want", "wanted",
    "need", "needed", "use", "using", "via", "about",
})

# Tokens that double as path-category cues — must survive tokenization.
PATH_CUE_TOKENS = frozenset({
    "test", "tests", "fixture", "fixtures", "vendor", "vendored",
    "dist", "docs", "doc", "build",
})

EXTENSIONS = (
    ".pyi", ".tsx", ".jsx", ".bash", ".zsh", ".json", ".toml",
    ".yaml", ".yml", ".html", ".rst", ".md", ".txt", ".cfg",
    ".ini", ".css", ".py", ".ts", ".js", ".sh",
)

DEMOTE_SEGMENTS: dict[str, tuple[str, ...]] = {
    "tests": ("test", "tests"),
    "test": ("test", "tests"),
    "vendor": ("vendor", "vendored", "vendoring"),
    "dist": ("dist", "distribution", "build"),
    "build": ("build", "builds"),
    "node_modules": ("node_modules", "node"),
    "__pycache__": ("__pycache__", "pycache", "cache"),
    "fixtures": ("fixture", "fixtures"),
    "fixture": ("fixture", "fixtures"),
}

RECENCY_WEIGHT = 1.0
SYMBOL_WEIGHT = 1.0
DEMOTION_WEIGHT = -2.0
CLICK_WEIGHT = 1.0

EVENT_FILE_READ_AFTER_HELPER = "file_read_after_helper"


@dataclass
class PathScore:
    path: str
    total: float
    recency: float = 0.0
    symbol: float = 0.0
    demotion: float = 0.0
    click_through: float = 0.0


# --------------------------------------------------------------------------- #
# A4 — tokenization + expansion
# --------------------------------------------------------------------------- #


def _strip_extension(word: str) -> str:
    lower = word.lower()
    for ext in EXTENSIONS:
        if lower.endswith(ext) and len(lower) > len(ext):
            return word[: -len(ext)]
    return word


def tokenize_query(query: str) -> list[str]:
    """Lowercase, split on punctuation, strip extensions, drop stopwords / short."""
    raw = re.findall(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9]+)*", query.lower())
    tokens: list[str] = []
    for word in raw:
        word = _strip_extension(word)
        word = word.strip(".")
        if not word:
            continue
        if word in PATH_CUE_TOKENS:
            tokens.append(word)
            continue
        if word in STOPWORDS:
            continue
        if len(word) < 3:
            continue
        tokens.append(word)
    return tokens


def expand_query(query: str) -> list[str]:
    """Return singles plus adjacent bigrams (no longer n-grams)."""
    tokens = tokenize_query(query)
    expanded = list(tokens)
    for i in range(len(tokens) - 1):
        expanded.append(f"{tokens[i]} {tokens[i + 1]}")
    return expanded


# --------------------------------------------------------------------------- #
# A1 — git-recency
# --------------------------------------------------------------------------- #


def _git_last_commit_ts(repo_root: Path, path: str) -> int | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%ct", "--", path],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    try:
        return int(output)
    except ValueError:
        return None


def git_recency_score(path: str, *, repo_root: Path, now_epoch: int) -> float:
    """Score in [0, 1] favouring files committed within the 90-day window."""
    ts = _git_last_commit_ts(Path(repo_root), path)
    if ts is None:
        return 0.0
    age_seconds = max(0, now_epoch - ts)
    age_days = age_seconds / 86400.0
    if age_days >= 90.0:
        # Past the active window; exponential decay toward 0 but stay positive.
        return max(0.0, 0.05 * math.exp(-(age_days - 90.0) / 90.0))
    return max(0.0, min(1.0, 1.0 - math.log1p(age_days) / math.log1p(90.0)))


# --------------------------------------------------------------------------- #
# A2 — symbol match
# --------------------------------------------------------------------------- #


def _snake_to_camel(token: str) -> str:
    parts = token.split("_")
    if len(parts) <= 1:
        return token
    head, *tail = parts
    return head + "".join(p[:1].upper() + p[1:] for p in tail if p)


def _camel_to_snake(token: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", token).lower()


def _symbol_variants(token: str) -> list[str]:
    variants = {token}
    if "_" in token:
        variants.add(_snake_to_camel(token))
    if re.search(r"[A-Z]", token):
        variants.add(_camel_to_snake(token))
    return [v for v in variants if v]


_DEFINITION_PATTERNS: tuple[str, ...] = (
    r"(?m)^\s*def\s+{tok}\s*\(",
    r"(?m)^\s*async\s+def\s+{tok}\s*\(",
    r"(?m)^\s*class\s+{tok}\s*[:\(]",
    r"(?m)^\s*{tok}\s*\(\s*\)\s*\{{",
    r"(?m)^\s*function\s+{tok}\s*[\(\{{]",
    r"(?m)^\s*export\s+function\s+{tok}\s*[\(<]",
    r"(?m)^\s*export\s+(?:async\s+)?function\s+{tok}\s*[\(<]",
    r"(?m)^\s*(?:export\s+)?const\s+{tok}\s*=",
    r"(?m)^\s*(?:export\s+)?(?:abstract\s+)?class\s+{tok}\s*[<\(\{{:]",
)


def symbol_match_score(
    path: str, tokens: Iterable[str], *, repo_root: Path
) -> float:
    file_path = Path(repo_root) / path
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0.0
    total = 0.0
    seen: set[str] = set()
    for token in tokens:
        for variant in _symbol_variants(token):
            if variant in seen:
                continue
            seen.add(variant)
            esc = re.escape(variant)
            for pat in _DEFINITION_PATTERNS:
                if re.search(pat.format(tok=esc), text):
                    total += SYMBOL_WEIGHT
                    break
    return total


# --------------------------------------------------------------------------- #
# A3 — path demotion
# --------------------------------------------------------------------------- #


def path_demotion_score(path: str, query_tokens: Iterable[str]) -> float:
    segments = [s for s in re.split(r"[/\\]", path) if s]
    demoted_keys = [s for s in segments if s in DEMOTE_SEGMENTS]
    if not demoted_keys:
        return 0.0
    qset = {t.lower() for t in query_tokens}
    for key in demoted_keys:
        for cue in DEMOTE_SEGMENTS[key]:
            if cue in qset:
                return 0.0
    return DEMOTION_WEIGHT


# --------------------------------------------------------------------------- #
# A5 — click-through learning
# --------------------------------------------------------------------------- #


def _normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


def click_through_score(
    path: str,
    query: str,
    priors: dict[str, dict[str, float]],
) -> float:
    nq = _normalize_query(query)
    for raw_key, table in priors.items():
        if _normalize_query(raw_key) == nq:
            return float(table.get(path, 0.0))
    return 0.0


def aggregate_priors(
    events: Iterable[dict],
) -> dict[str, dict[str, float]]:
    """Build click-through priors from ``file_read_after_helper`` events."""
    priors: dict[str, dict[str, float]] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("event") != EVENT_FILE_READ_AFTER_HELPER:
            continue
        q = ev.get("query") or ev.get("meta", {}).get("query")
        p = ev.get("path") or ev.get("meta", {}).get("path")
        if not q or not p:
            continue
        key = _normalize_query(q)
        table = priors.setdefault(key, {})
        table[p] = table.get(p, 0.0) + 1.0
    return priors


# --------------------------------------------------------------------------- #
# rank_paths entry point
# --------------------------------------------------------------------------- #


def rank_paths(
    query: str,
    candidates: Sequence[str],
    *,
    repo_root: Path,
    now_epoch: int,
    click_through_priors: dict[str, dict[str, float]] | None = None,
    return_scores: bool = False,
) -> list[str] | list[PathScore]:
    tokens = tokenize_query(query)
    priors = click_through_priors or {}
    scored: list[PathScore] = []
    for path in candidates:
        rec = git_recency_score(path, repo_root=Path(repo_root), now_epoch=now_epoch)
        sym = symbol_match_score(path, tokens, repo_root=Path(repo_root))
        dem = path_demotion_score(path, tokens)
        clk = click_through_score(path, query, priors)
        total = (
            RECENCY_WEIGHT * rec
            + SYMBOL_WEIGHT * sym
            + dem
            + CLICK_WEIGHT * clk
        )
        scored.append(
            PathScore(
                path=path,
                total=total,
                recency=rec,
                symbol=sym,
                demotion=dem,
                click_through=clk,
            )
        )
    scored.sort(key=lambda x: x.total, reverse=True)
    if return_scores:
        return scored
    return [s.path for s in scored]
