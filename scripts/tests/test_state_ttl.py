"""STATE_TTL_SECONDS hardening: shrink from 20min to 5min (matching
BLOCK_TTL_SECONDS) so a poisoned "pending" marker left behind by a crashed
or wedged session has a smaller blast radius on the next session that reuses
the same session key.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import token_reduce_state as trs


def test_state_ttl_is_five_minutes() -> None:
    assert trs.STATE_TTL_SECONDS == 5 * 60


def test_pending_marker_older_than_five_minutes_is_pruned(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    key = "sess-old"
    trs.mark_pending(repo, key, "explore the repo for hooks")
    stale_mtime = time.time() - (6 * 60)
    path = trs.state_path(repo, key)
    default_path = trs.state_path(repo, "default")
    os.utime(path, (stale_mtime, stale_mtime))
    os.utime(default_path, (stale_mtime, stale_mtime))

    assert trs.is_pending(repo, key) is False
    assert not path.exists()
    assert not default_path.exists()


def test_pending_marker_within_five_minutes_is_kept(tmp_path: Path) -> None:
    repo = tmp_path
    key = "sess-fresh"
    trs.mark_pending(repo, key, "explore the repo for hooks")

    assert trs.is_pending(repo, key) is True
