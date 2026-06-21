"""Track H1 — warm QMD cache.

Cache QMD collection list and first-page query results for the
duration of a session. Hits should be sub-millisecond; misses fall
through to the live QMD CLI and seed the cache.

Stored on disk under ``.claude/token-reduce-state/qmd-cache/<session>.json``
so successive helper invocations within the same session benefit
without needing a long-lived daemon.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


CACHE_TTL_SECONDS = 600  # 10 minutes — matches typical helper-session lifetime
CACHE_DIR_NAME = "qmd-cache"


def time_now() -> float:
    """Indirection so tests can monkeypatch the clock."""
    return time.time()


def cache_path(*, repo_root: Path, session_key: str) -> Path:
    base = repo_root / ".claude" / "token-reduce-state" / CACHE_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_key) or "default"
    return base / f"{safe}.json"


class QmdWarmCache:
    """Session-scoped read-through cache for QMD discovery."""

    def __init__(self, *, repo_root: Path, session_key: str) -> None:
        self.path = cache_path(repo_root=repo_root, session_key=session_key)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict):
            self._data = raw

    def _flush(self) -> None:
        try:
            self.path.write_text(json.dumps(self._data))
        except OSError:
            pass

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if not isinstance(entry, dict):
            return None
        ts = entry.get("ts")
        value = entry.get("value")
        if not isinstance(ts, (int, float)):
            return None
        if time_now() - float(ts) > CACHE_TTL_SECONDS:
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = {"ts": time_now(), "value": value}
        self._flush()
