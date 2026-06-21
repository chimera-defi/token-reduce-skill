"""Track H — Brief leftovers.

H1. Warm/persist QMD index across helper invocations. Cache the qmd
    collection list + first-page results per session. Target p95 <300ms.
H2. Explicit ``token_savior`` gating decision documented in SKILL.md +
    references/: optional, install via ``uv tool install token-savior``;
    only needed for exact-symbol change-impact queries. Don't auto-install.
H3. Output-hook over-compression workaround documented (no repo-local
    PostToolUse hook found; redirect pytest output to file + Read it).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qmd_warm_cache import (  # noqa: E402
    CACHE_TTL_SECONDS,
    QmdWarmCache,
    cache_path,
)


# --------------------------------------------------------------------------- #
# H1 — QMD warm cache: hit p95 <300ms
# --------------------------------------------------------------------------- #


def test_h1_cache_path_uses_session_namespace(tmp_path: Path) -> None:
    path = cache_path(repo_root=tmp_path, session_key="abc123")
    assert "abc123" in str(path)
    assert str(tmp_path) in str(path)


def test_h1_warm_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = QmdWarmCache(repo_root=tmp_path, session_key="t1")
    assert cache.get("collections") is None
    cache.set("collections", ["c1", "c2"])
    assert cache.get("collections") == ["c1", "c2"]


def test_h1_warm_cache_persists_across_instances(tmp_path: Path) -> None:
    cache1 = QmdWarmCache(repo_root=tmp_path, session_key="t2")
    cache1.set("first_page:foo", [{"path": "a.py"}])
    cache2 = QmdWarmCache(repo_root=tmp_path, session_key="t2")
    assert cache2.get("first_page:foo") == [{"path": "a.py"}]


def test_h1_warm_cache_expires(tmp_path: Path, monkeypatch) -> None:
    cache = QmdWarmCache(repo_root=tmp_path, session_key="t3")
    cache.set("collections", ["c1"])
    monkeypatch.setattr(
        "qmd_warm_cache.time_now",
        lambda: time.time() + CACHE_TTL_SECONDS + 10,
    )
    assert cache.get("collections") is None


def test_h1_warm_cache_hit_under_300ms(tmp_path: Path) -> None:
    cache = QmdWarmCache(repo_root=tmp_path, session_key="t4")
    cache.set("first_page:bar", [{"path": "b.py"}])
    # Read 50 times, take p95.
    latencies = []
    for _ in range(50):
        start = time.perf_counter()
        cache.get("first_page:bar")
        latencies.append((time.perf_counter() - start) * 1000)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    assert p95 < 300.0, f"p95={p95:.2f}ms"


def test_h1_cache_ttl_is_session_scoped() -> None:
    # 5 minutes is short enough to avoid stale state across long sessions
    # but long enough to amortize repeated reads.
    assert 60 <= CACHE_TTL_SECONDS <= 3600


# --------------------------------------------------------------------------- #
# H2 — token_savior gating doc
# --------------------------------------------------------------------------- #


def test_h2_skill_md_mentions_token_savior_is_optional() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    lowered = skill.lower()
    assert "token-savior" in lowered or "token_savior" in lowered
    assert "optional" in lowered
    assert "uv tool install token-savior" in lowered


def test_h2_skill_md_says_only_exact_symbol_queries() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    lowered = skill.lower()
    # Must clarify when it's actually useful.
    assert "exact-symbol" in lowered or "exact symbol" in lowered


def test_h2_skill_md_says_do_not_auto_install() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    lowered = skill.lower()
    assert "do not auto-install" in lowered or "no auto-install" in lowered or "don't auto-install" in lowered


# --------------------------------------------------------------------------- #
# H3 — output-hook over-compression workaround
# --------------------------------------------------------------------------- #


def test_h3_repo_has_no_post_tool_use_hook() -> None:
    # If we ever add one, it must explicitly preserve test output.
    settings = REPO_ROOT / ".claude" / "settings.json"
    if settings.exists():
        text = settings.read_text()
        # The brief forbids modifying the global hook. If a PostToolUse
        # hook lands here, it must be reviewed.
        assert "PostToolUse" not in text, (
            "If a PostToolUse hook is added, it MUST NOT mangle pytest output. "
            "See SKILL.md 'output-hook workaround'."
        )


def test_h3_skill_md_documents_workaround() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    lowered = skill.lower()
    # Workaround: redirect to file, Read it.
    assert "redirect" in lowered and "read" in lowered
    assert "pytest" in lowered


def test_h3_workaround_mentions_global_hook_caveat() -> None:
    skill = (REPO_ROOT / "SKILL.md").read_text()
    lowered = skill.lower()
    # The workaround section should acknowledge this is a cross-repo issue.
    assert "global" in lowered or "cross-repo" in lowered or "~/.claude" in lowered
