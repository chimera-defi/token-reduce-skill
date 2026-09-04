from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from session_metrics_cache import (  # noqa: E402
    SessionMetricsCache,
    cache_path,
    fingerprint_files,
)


def test_cache_path_lives_under_artifacts_token_reduction(tmp_path: Path) -> None:
    p = cache_path(tmp_path)
    assert p == (tmp_path / "artifacts" / "token-reduction" / "session-metrics-cache.json")


def test_fingerprint_files_returns_none_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jsonl"
    assert fingerprint_files([missing]) is None


def test_fingerprint_files_is_order_independent(tmp_path: Path) -> None:
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text("a")
    b.write_text("bb")

    fp1 = fingerprint_files([a, b])
    fp2 = fingerprint_files([b, a])

    assert fp1 == fp2
    assert fp1 is not None


def test_set_then_get_round_trips(tmp_path: Path) -> None:
    cache = SessionMetricsCache(tmp_path / "cache.json")
    f = tmp_path / "s.jsonl"
    f.write_text("x")
    fp = fingerprint_files([f])

    cache.set(f"codex:{f}", fp, {"qmd_search": True})

    assert cache.get(f"codex:{f}", fp) == {"qmd_search": True}


def test_get_misses_when_fingerprint_changed(tmp_path: Path) -> None:
    cache = SessionMetricsCache(tmp_path / "cache.json")
    f = tmp_path / "s.jsonl"
    f.write_text("x")
    fp = fingerprint_files([f])
    cache.set(f"codex:{f}", fp, {"qmd_search": True})

    f.write_text("xx")  # changes size + mtime
    new_fp = fingerprint_files([f])

    assert cache.get(f"codex:{f}", new_fp) is None


def test_get_misses_when_fingerprint_is_none(tmp_path: Path) -> None:
    cache = SessionMetricsCache(tmp_path / "cache.json")
    f = tmp_path / "s.jsonl"
    f.write_text("x")
    fp = fingerprint_files([f])
    cache.set(f"codex:{f}", fp, {"qmd_search": True})

    assert cache.get(f"codex:{f}", None) is None


def test_save_persists_and_reload_recovers_entries(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = SessionMetricsCache(path)
    f = tmp_path / "s.jsonl"
    f.write_text("x")
    fp = fingerprint_files([f])
    cache.set(f"codex:{f}", fp, {"qmd_search": True})

    cache.save()

    assert path.exists()
    reloaded = SessionMetricsCache(path)
    assert reloaded.get(f"codex:{f}", fp) == {"qmd_search": True}


def test_save_is_noop_when_not_dirty(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = SessionMetricsCache(path)

    cache.save()

    assert not path.exists()


def test_prune_stale_drops_entries_for_deleted_files_only(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = SessionMetricsCache(path)
    kept = tmp_path / "kept.jsonl"
    kept.write_text("k")
    gone = tmp_path / "gone.jsonl"
    gone.write_text("g")

    cache.set(f"codex:{kept}", fingerprint_files([kept]), {"a": 1})
    cache.set(f"codex:{gone}", fingerprint_files([gone]), {"a": 2})
    gone.unlink()

    removed = cache.prune_stale()

    assert removed == 1
    assert len(cache) == 1
    assert cache.get(f"codex:{kept}", fingerprint_files([kept])) == {"a": 1}


def test_corrupted_cache_file_is_ignored_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json")

    cache = SessionMetricsCache(path)

    assert len(cache) == 0


def test_cache_file_from_wrong_version_is_ignored(tmp_path: Path) -> None:
    import json

    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"version": 999, "entries": {"x": {"fingerprint": [], "metrics": {}}}}))

    cache = SessionMetricsCache(path)

    assert len(cache) == 0
