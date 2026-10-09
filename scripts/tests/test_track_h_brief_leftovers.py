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
)


# --------------------------------------------------------------------------- #
# H1 — QMD warm cache: hit p95 <300ms
# --------------------------------------------------------------------------- #




def test_h1_warm_cache_miss_then_hit(tmp_path: Path) -> None:
    cache = QmdWarmCache(repo_root=tmp_path, session_key="t1")
    assert cache.get("collections") is None
    cache.set("collections", ["c1", "c2"])
    assert cache.get("collections") == ["c1", "c2"]




def test_h1_warm_cache_expires(tmp_path: Path, monkeypatch) -> None:
    cache = QmdWarmCache(repo_root=tmp_path, session_key="t3")
    cache.set("collections", ["c1"])
    monkeypatch.setattr(
        "qmd_warm_cache.time_now",
        lambda: time.time() + CACHE_TTL_SECONDS + 10,
    )
    assert cache.get("collections") is None






# --------------------------------------------------------------------------- #
# H2 — token_savior gating doc
# --------------------------------------------------------------------------- #








# --------------------------------------------------------------------------- #
# H3 — output-hook over-compression workaround
# --------------------------------------------------------------------------- #






