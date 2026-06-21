"""Track A — ranking quality tests.

Drives the design of `scripts/rank_paths.py`. Each section corresponds to one
sub-track from references/improvement-brief-2026-06-21.md:

- A1 git-recency log-decay
- A2 symbol-match boost
- A3 path-relevance demotion
- A4 query expansion / stopwords
- A5 click-through learning
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from rank_paths import (  # noqa: E402  (path setup before import)
    PathScore,
    click_through_score,
    expand_query,
    git_recency_score,
    path_demotion_score,
    rank_paths,
    symbol_match_score,
    tokenize_query,
)


# ---------------------------------------------------------------------------
# A4 query expansion / stopwords (no fixture needed)
# ---------------------------------------------------------------------------


def test_tokenize_query_drops_short_and_stopwords() -> None:
    assert tokenize_query("how do I find the measure script") == [
        "measure",
        "script",
    ]


def test_tokenize_query_preserves_symbols_with_punctuation() -> None:
    tokens = tokenize_query("measure_token_reduction.py call site")
    assert "measure_token_reduction" in tokens
    assert "call" in tokens and "site" in tokens
    # tokens that look like file extensions alone are dropped
    assert ".py" not in tokens
    assert "py" not in tokens


def test_expand_query_adds_bigrams_for_multi_token() -> None:
    expanded = expand_query("ranking quality helper")
    # singles
    assert "ranking" in expanded
    assert "quality" in expanded
    assert "helper" in expanded
    # bigrams
    assert "ranking quality" in expanded
    assert "quality helper" in expanded
    # no triple bigram leakage
    assert "ranking quality helper" not in expanded


def test_expand_query_single_token_is_idempotent() -> None:
    assert expand_query("ranker") == ["ranker"]


# ---------------------------------------------------------------------------
# A1 git-recency log-decay
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    cmd_env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    if env:
        cmd_env.update(env)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        env={**cmd_env, "PATH": "/usr/bin:/bin"},
        capture_output=True,
    )


@pytest.fixture
def recency_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main", "-q")
    (repo / "old.py").write_text("# old\n")
    (repo / "fresh.py").write_text("# fresh\n")
    _git(
        repo,
        "add",
        "old.py",
    )
    _git(
        repo,
        "commit",
        "-m",
        "old",
        "--date=2025-01-01T00:00:00Z",
        env={"GIT_COMMITTER_DATE": "2025-01-01T00:00:00Z"},
    )
    _git(repo, "add", "fresh.py")
    _git(
        repo,
        "commit",
        "-m",
        "fresh",
        "--date=2026-06-20T00:00:00Z",
        env={"GIT_COMMITTER_DATE": "2026-06-20T00:00:00Z"},
    )
    return repo


def test_git_recency_score_fresh_outranks_old(recency_repo: Path) -> None:
    # now=2026-06-21
    now = 1750464000  # 2026-06-21T00:00:00Z
    fresh = git_recency_score("fresh.py", repo_root=recency_repo, now_epoch=now)
    old = git_recency_score("old.py", repo_root=recency_repo, now_epoch=now)
    assert fresh > old
    assert 0.0 <= old <= fresh <= 1.0


def test_git_recency_score_clamps_after_max_age(recency_repo: Path) -> None:
    # Same repo but evaluate as if far future — older than 90d window.
    future = 1750464000 + 86_400 * 365  # +1y
    old = git_recency_score("old.py", repo_root=recency_repo, now_epoch=future)
    # log-decay clamps the floor near zero (not negative)
    assert old <= 0.05
    assert old >= 0.0


def test_git_recency_score_unknown_file_returns_zero(recency_repo: Path) -> None:
    assert git_recency_score(
        "does_not_exist.py",
        repo_root=recency_repo,
        now_epoch=1750464000,
    ) == 0.0


# ---------------------------------------------------------------------------
# A2 symbol-match boost
# ---------------------------------------------------------------------------


@pytest.fixture
def symbol_corpus(tmp_path: Path) -> Path:
    repo = tmp_path / "syms"
    repo.mkdir()
    (repo / "definer.py").write_text(
        "def measure_token_reduction(events):\n    return len(events)\n"
    )
    (repo / "mentioner.py").write_text(
        "# this file just mentions measure_token_reduction in a comment\n"
        "x = 1\n"
    )
    (repo / "shell_def.sh").write_text(
        "#!/usr/bin/env bash\nmeasure_token_reduction() { echo hi; }\n"
    )
    (repo / "ts_def.ts").write_text(
        "export function measureTokenReduction(events: number[]): number {\n"
        "  return events.length;\n"
        "}\n"
    )
    return repo


def test_symbol_match_boost_finds_python_def(symbol_corpus: Path) -> None:
    tokens = ["measure_token_reduction"]
    define = symbol_match_score(
        "definer.py", tokens, repo_root=symbol_corpus
    )
    mention = symbol_match_score(
        "mentioner.py", tokens, repo_root=symbol_corpus
    )
    assert define > 0
    assert mention == 0


def test_symbol_match_boost_finds_shell_function(symbol_corpus: Path) -> None:
    tokens = ["measure_token_reduction"]
    score = symbol_match_score(
        "shell_def.sh", tokens, repo_root=symbol_corpus
    )
    assert score > 0


def test_symbol_match_boost_finds_typescript_camel_to_snake(
    symbol_corpus: Path,
) -> None:
    tokens = ["measure_token_reduction"]
    score = symbol_match_score(
        "ts_def.ts", tokens, repo_root=symbol_corpus
    )
    assert score > 0


# ---------------------------------------------------------------------------
# A3 path-relevance demotion
# ---------------------------------------------------------------------------


def test_path_demotion_tests_demoted_without_cue() -> None:
    demoted = path_demotion_score(
        "scripts/tests/test_thing.py",
        tokenize_query("find the thing helper"),
    )
    kept = path_demotion_score(
        "scripts/thing.py",
        tokenize_query("find the thing helper"),
    )
    assert demoted < 0
    assert kept == 0


def test_path_demotion_tests_kept_when_query_cues() -> None:
    score = path_demotion_score(
        "scripts/tests/test_thing.py",
        tokenize_query("test thing"),
    )
    assert score == 0


def test_path_demotion_vendor_and_dist_demoted() -> None:
    tokens = tokenize_query("rank paths")
    assert path_demotion_score("vendor/foo/bar.py", tokens) < 0
    assert path_demotion_score("dist/rank.min.js", tokens) < 0
    assert path_demotion_score("node_modules/foo/index.js", tokens) < 0
    assert path_demotion_score("__pycache__/cached.pyc", tokens) < 0


def test_path_demotion_fixtures_demoted_unless_cued() -> None:
    base_tokens = tokenize_query("rank paths")
    assert path_demotion_score("tests/fixtures/foo.txt", base_tokens) < 0
    cued = tokenize_query("ranking fixtures corpus")
    assert path_demotion_score("tests/fixtures/foo.txt", cued) == 0


# ---------------------------------------------------------------------------
# A5 click-through learning
# ---------------------------------------------------------------------------


def test_click_through_prior_boosts_previously_read_file() -> None:
    priors = {
        "measure script": {"scripts/measure_token_reduction.py": 0.8},
    }
    boost = click_through_score(
        "scripts/measure_token_reduction.py",
        "measure script",
        priors,
    )
    other = click_through_score(
        "scripts/other.py",
        "measure script",
        priors,
    )
    assert boost > 0
    assert other == 0


def test_click_through_prior_normalizes_query_for_lookup() -> None:
    priors = {
        "ranking helper": {"scripts/rank_paths.py": 0.5},
    }
    # case/whitespace normalization should still hit
    assert click_through_score(
        "scripts/rank_paths.py",
        "  RANKING   helper  ",
        priors,
    ) > 0


def test_click_through_prior_missing_query_returns_zero() -> None:
    priors = {"unrelated": {"foo.py": 0.9}}
    assert click_through_score("foo.py", "different query", priors) == 0


# ---------------------------------------------------------------------------
# End-to-end ranking
# ---------------------------------------------------------------------------


@pytest.fixture
def integration_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "int_repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main", "-q")

    # Definition site, recent
    (repo / "scripts").mkdir()
    (repo / "scripts" / "measure_token_reduction.py").write_text(
        "def measure_token_reduction(events):\n    return len(events)\n"
    )
    # Old, just mentions
    (repo / "docs").mkdir()
    (repo / "docs" / "notes.md").write_text(
        "Talks about measure_token_reduction conceptually.\n"
    )
    # Tests file with the symbol — should be demoted absent test cue
    (repo / "scripts" / "tests").mkdir()
    (repo / "scripts" / "tests" / "test_measure.py").write_text(
        "def test_measure_token_reduction(): pass\n"
    )
    # Vendored noise containing the symbol
    (repo / "vendor").mkdir()
    (repo / "vendor" / "old_lib.py").write_text(
        "# measure_token_reduction was the old name\n"
    )

    _git(repo, "add", ".")
    _git(
        repo,
        "commit",
        "-m",
        "older noise",
        "--date=2025-09-01T00:00:00Z",
        env={"GIT_COMMITTER_DATE": "2025-09-01T00:00:00Z"},
    )
    # Touch the definition to make it newer
    (repo / "scripts" / "measure_token_reduction.py").write_text(
        "def measure_token_reduction(events):\n    return len(events) + 1\n"
    )
    _git(repo, "add", "scripts/measure_token_reduction.py")
    _git(
        repo,
        "commit",
        "-m",
        "fresh tweak",
        "--date=2026-06-15T00:00:00Z",
        env={"GIT_COMMITTER_DATE": "2026-06-15T00:00:00Z"},
    )
    return repo


def test_rank_paths_definition_beats_mention_and_tests(
    integration_repo: Path,
) -> None:
    candidates = [
        "docs/notes.md",
        "scripts/tests/test_measure.py",
        "vendor/old_lib.py",
        "scripts/measure_token_reduction.py",
    ]
    ranked = rank_paths(
        "measure_token_reduction helper",
        candidates,
        repo_root=integration_repo,
        now_epoch=1750464000,  # 2026-06-21
    )
    assert isinstance(ranked, list)
    assert ranked[0] == "scripts/measure_token_reduction.py"
    # vendor + tests demoted below docs
    assert ranked.index("vendor/old_lib.py") > ranked.index("docs/notes.md")
    assert (
        ranked.index("scripts/tests/test_measure.py")
        > ranked.index("docs/notes.md")
    )


def test_rank_paths_click_through_overrides_close_call(
    integration_repo: Path,
) -> None:
    candidates = [
        "scripts/measure_token_reduction.py",
        "docs/notes.md",
    ]
    priors = {
        "measure_token_reduction helper": {"docs/notes.md": 5.0},  # huge prior
    }
    ranked = rank_paths(
        "measure_token_reduction helper",
        candidates,
        repo_root=integration_repo,
        now_epoch=1750464000,
        click_through_priors=priors,
    )
    assert ranked[0] == "docs/notes.md"


def test_rank_paths_returns_path_score_for_debug(
    integration_repo: Path,
) -> None:
    candidates = ["scripts/measure_token_reduction.py", "vendor/old_lib.py"]
    detailed = rank_paths(
        "measure_token_reduction",
        candidates,
        repo_root=integration_repo,
        now_epoch=1750464000,
        return_scores=True,
    )
    assert all(isinstance(item, PathScore) for item in detailed)
    assert detailed[0].path == "scripts/measure_token_reduction.py"
    assert detailed[0].total > detailed[-1].total
