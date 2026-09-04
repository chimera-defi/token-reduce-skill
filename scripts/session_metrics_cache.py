#!/usr/bin/env python3
"""On-disk cache of parsed per-session token-reduce adoption metrics.

``measure_token_reduction.py``'s ``measure()`` at ``--scope global`` reads
and fully parses every Claude/Codex session transcript it can find on every
single invocation, with no memoization. Session transcripts are immutable
once a session has ended (only the *currently active* session's file still
grows), so re-parsing an unchanged multi-megabyte JSONL file on every run is
almost entirely wasted work -- and at scale (hundreds of files, several GB)
it is the dominant cost of a ``--scope global`` measurement (observed: a
single 803MB/95k-line Codex transcript alone took ~109s to parse; the full
~4.5GB/1000+ file corpus extrapolates to several minutes, matching the
"never completes even under a 590s timeout" symptom this cache fixes).

This module gives ``measure()`` a small, dependency-free, session-file-level
cache: each entry is keyed by the session file's path and validated by a
fingerprint of every file its metrics were computed from (the main session
file, plus subagent transcripts for Claude sessions). If the fingerprint
still matches what's on disk, the cached metrics are reused verbatim and the
file(s) are not read again. If the fingerprint differs (or there is no
entry), the file is parsed fresh and the result is cached for next time.

Follows this repo's existing on-disk JSON cache conventions:
- ``qmd_warm_cache.py`` for the load/get/set/flush shape.
- ``token-reduce-search.sh``'s ``QMD_STAMP_DIR=$REPO_ROOT/artifacts`` /
  ``stamp_is_fresh()`` for storing cache/stamp state under the repo's
  gitignored ``artifacts/`` directory.

Unlike the QMD cache (which is TTL-based, because it fronts a live query),
this cache has no TTL -- validity is purely content-based (mtime_ns + size),
which is the correct model for immutable-once-written session transcripts:
an unchanged file is unchanged no matter how much wall-clock time passed.

Saves are incremental (every ``cache_flush_every`` files, see
``measure_token_reduction.measure()``) rather than a single end-of-run
write, so a run that gets killed partway through still leaves the files it
did finish processing cached for the next attempt, instead of losing all
progress and starting cold again.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR_NAME = "token-reduction"
CACHE_FILE_NAME = "session-metrics-cache.json"
CACHE_VERSION = 1

Fingerprint = list[list[Any]]


def cache_path(repo_root: Path) -> Path:
    """Where the on-disk cache lives for a given repo_root.

    Matches this repo's ``artifacts/token-reduction/`` convention (see
    ``composite_token_telemetry.py`` output and ``token-reduce-manage.sh``'s
    ``composite``/``review`` commands); ``artifacts/`` is gitignored, so the
    cache is local-machine state and is never committed.
    """
    return Path(repo_root).resolve() / "artifacts" / CACHE_DIR_NAME / CACHE_FILE_NAME


def fingerprint_files(paths: list[Path]) -> Fingerprint | None:
    """Return a sorted (path, mtime_ns, size) fingerprint for ``paths``.

    Returns ``None`` if any path can't be stat'd (e.g. deleted mid-run), so
    the caller treats that as an unconditional cache miss instead of caching
    a fingerprint that can never be reproduced.
    """
    fp: Fingerprint = []
    for p in paths:
        try:
            st = p.stat()
        except OSError:
            return None
        fp.append([str(p), st.st_mtime_ns, st.st_size])
    fp.sort(key=lambda row: row[0])
    return fp


class SessionMetricsCache:
    """Read-through, content-fingerprinted cache of per-session metrics."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return
        if isinstance(raw, dict) and raw.get("version") == CACHE_VERSION:
            entries = raw.get("entries")
            if isinstance(entries, dict):
                self._entries = entries

    def get(self, key: str, fingerprint: Fingerprint | None) -> Any | None:
        if fingerprint is None:
            return None
        entry = self._entries.get(key)
        if not isinstance(entry, dict):
            return None
        if entry.get("fingerprint") != fingerprint:
            return None
        return entry.get("metrics")

    def set(self, key: str, fingerprint: Fingerprint, metrics: Any) -> None:
        self._entries[key] = {"fingerprint": fingerprint, "metrics": metrics}
        self._dirty = True

    def prune_stale(self) -> int:
        """Drop entries whose primary session file no longer exists on disk.

        Keys are ``"<source>:<path>"``; only the primary session file's
        existence gates eviction here. A session whose *subagent* transcript
        was removed still invalidates correctly on the next read via the
        normal fingerprint mismatch path -- it just isn't proactively
        pruned by this method.
        """
        stale = []
        for key in self._entries:
            _, _, raw_path = key.partition(":")
            if raw_path and not Path(raw_path).exists():
                stale.append(key)
        for key in stale:
            del self._entries[key]
        if stale:
            self._dirty = True
        return len(stale)

    def save(self, *, force: bool = False) -> None:
        if not self._dirty and not force:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp{os.getpid()}")
        payload = {"version": CACHE_VERSION, "entries": self._entries}
        try:
            tmp_path.write_text(json.dumps(payload))
            os.replace(tmp_path, self.path)
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        self._dirty = False

    def __len__(self) -> int:
        return len(self._entries)
