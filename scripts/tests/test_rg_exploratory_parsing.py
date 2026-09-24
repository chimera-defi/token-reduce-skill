from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from measure_token_reduction import is_exploratory_rg as measure_is_exploratory_rg
from measure_token_reduction import rg_paths as measure_rg_paths


def _load_enforce_module():
    path = SCRIPT_DIR / "enforce-token-reduce-first.py"
    spec = importlib.util.spec_from_file_location("enforce_token_reduce_first", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rg_e_option_treated_as_pattern_not_path() -> None:
    command = "rg -e prompt_requires_helper scripts/token_reduce_state.py"
    assert measure_rg_paths(command) == ["scripts/token_reduce_state.py"]
    assert measure_is_exploratory_rg(command) is False

    enforce = _load_enforce_module()
    assert enforce.is_exploratory_rg(command, Path(".")) is False


def test_rg_regexp_equals_treated_as_pattern_not_path() -> None:
    command = "rg --regexp=prompt_requires_helper scripts/token_reduce_state.py"
    assert measure_rg_paths(command) == ["scripts/token_reduce_state.py"]
    assert measure_is_exploratory_rg(command) is False

    enforce = _load_enforce_module()
    assert enforce.is_exploratory_rg(command, Path(".")) is False


def test_rg_pattern_file_treated_as_pattern_not_path() -> None:
    command = "rg -f patterns.txt scripts/token_reduce_state.py"
    assert measure_rg_paths(command) == ["scripts/token_reduce_state.py"]
    assert measure_is_exploratory_rg(command) is False

    enforce = _load_enforce_module()
    assert enforce.is_exploratory_rg(command, Path(".")) is False


def test_rg_root_target_still_exploratory() -> None:
    command = "rg -e prompt_requires_helper ."
    assert measure_is_exploratory_rg(command) is True

    enforce = _load_enforce_module()
    assert enforce.is_exploratory_rg(command, Path(".")) is True


def test_rg_quoted_bare_pattern_against_known_file_not_exploratory() -> None:
    """Regression: `rg -n "<quoted pattern>" <file>` is ordinary, targeted work
    (Opus 5.5 guidance: a specific grep against a known file must never be
    treated as exploratory). Before the fix, `classify_bash_command`'s quote
    -stripped surface blanked the quoted pattern to whitespace, so `rg_paths`
    re-tokenized the line and mistook the trailing file argument for the
    pattern -- `rg_paths` came back empty and `is_exploratory_rg` concluded
    "no path argument" -> exploratory, even though this is a single-file grep.
    """
    repo = Path(__file__).resolve().parents[2]
    command = 'rg -n "^#|^##" SKILL.md'

    enforce = _load_enforce_module()
    # Direct call with the raw (quoted) command: shlex already handles this
    # correctly, so this direction already passed before the fix.
    assert enforce.is_exploratory_rg(command, repo) is False

    # The actual hook path: classify_bash_command runs the line through
    # command_scan_surfaces (quote-stripping) before segment-splitting and
    # calling is_exploratory_rg -- this is where the bug lived.
    catastrophic, broad_hit, rg_hit, coverage_hit = enforce.classify_bash_command(
        [command], repo
    )
    assert not catastrophic
    assert not broad_hit
    assert rg_hit is False, "quoted bare rg pattern against a known file must not be exploratory"
    assert not coverage_hit


def test_rg_quoted_bare_pattern_piped_to_head_not_exploratory() -> None:
    """Same bug, exercised as it actually showed up live: a quoted pattern
    whose regex itself contains a literal `|`, piped to `head`."""
    repo = Path(__file__).resolve().parents[2]
    command = 'rg -n "^#|^##" SKILL.md | head -80'

    enforce = _load_enforce_module()
    catastrophic, broad_hit, rg_hit, coverage_hit = enforce.classify_bash_command(
        [command], repo
    )
    assert not catastrophic
    assert not broad_hit
    assert rg_hit is False
    assert not coverage_hit
