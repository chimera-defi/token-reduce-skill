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
