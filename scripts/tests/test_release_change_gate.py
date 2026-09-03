#!/usr/bin/env python3
"""Tests for release-change-gate.py pure functions — previously zero coverage."""
from __future__ import annotations

import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))

# Module name has a hyphen — import via importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "release_change_gate",
    scripts_dir / "release-change-gate.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

composite_check = _mod.composite_check
adaptive_check = _mod.adaptive_check
profile_check = _mod.profile_check


class TestCompositeCheck:
    def _payload(self, *, quality_pass: bool = True, savings: float = 80.0) -> dict:
        return {
            "benchmarks": [
                {"name": "composite_stack", "quality_pass": quality_pass, "savings_vs_broad_pct": savings}
            ]
        }

    def test_passes_when_quality_pass_and_savings_above_min(self):
        ok, meta = composite_check(self._payload(quality_pass=True, savings=85.0), min_savings=80.0)
        assert ok is True
        assert meta["quality_pass"] is True
        assert meta["savings_vs_broad_pct"] == 85.0

    def test_fails_when_savings_below_min(self):
        ok, meta = composite_check(self._payload(quality_pass=True, savings=50.0), min_savings=80.0)
        assert ok is False

    def test_fails_when_quality_pass_false(self):
        ok, meta = composite_check(self._payload(quality_pass=False, savings=90.0), min_savings=80.0)
        assert ok is False

    def test_fails_when_benchmarks_key_missing(self):
        ok, meta = composite_check({}, min_savings=80.0)
        assert ok is False
        assert "reason" in meta

    def test_fails_when_benchmarks_not_a_list(self):
        ok, meta = composite_check({"benchmarks": "bad"}, min_savings=80.0)
        assert ok is False

    def test_fails_when_composite_stack_row_absent(self):
        payload = {"benchmarks": [{"name": "other_bench", "quality_pass": True, "savings_vs_broad_pct": 90.0}]}
        ok, meta = composite_check(payload, min_savings=80.0)
        assert ok is False
        assert meta.get("reason") == "missing composite_stack row"

    def test_meta_includes_min_required_savings(self):
        ok, meta = composite_check(self._payload(), min_savings=75.0)
        assert meta["min_required_savings_pct"] == 75.0


class TestAdaptiveCheck:
    def _payload(self, *, quality_pass: bool = True, savings: float = 80.0) -> dict:
        return {
            "summary": {
                "adaptive_quality_pass": quality_pass,
                "adaptive_savings_vs_baseline_pct": savings,
            }
        }

    def test_passes_when_quality_pass_and_savings_above_min(self):
        ok, meta = adaptive_check(self._payload(quality_pass=True, savings=90.0), min_savings=80.0)
        assert ok is True

    def test_fails_when_savings_below_min(self):
        ok, meta = adaptive_check(self._payload(quality_pass=True, savings=60.0), min_savings=80.0)
        assert ok is False

    def test_fails_when_quality_pass_false(self):
        ok, meta = adaptive_check(self._payload(quality_pass=False, savings=90.0), min_savings=80.0)
        assert ok is False

    def test_fails_when_summary_missing(self):
        # Missing summary → defaults to {}, quality_pass=False, savings=0.0 → ok=False
        ok, meta = adaptive_check({}, min_savings=80.0)
        assert ok is False
        assert meta["adaptive_quality_pass"] is False
        assert meta["adaptive_savings_vs_baseline_pct"] == 0.0

    def test_fails_when_summary_not_dict(self):
        ok, meta = adaptive_check({"summary": [1, 2]}, min_savings=80.0)
        assert ok is False

    def test_missing_savings_key_treated_as_zero(self):
        ok, meta = adaptive_check({"summary": {"adaptive_quality_pass": True}}, min_savings=80.0)
        assert ok is False
        assert meta["adaptive_savings_vs_baseline_pct"] == 0.0


class TestProfileCheck:
    def test_passes_when_at_least_one_profile_promoted(self):
        payload = {
            "profiles": [
                {"profile": "fast", "promote_adaptive_default": True},
                {"profile": "slow", "promote_adaptive_default": False},
            ],
            "recommended_profile": "fast",
        }
        ok, meta = profile_check(payload)
        assert ok is True
        assert "fast" in meta["promoted_profiles"]
        assert meta["recommended_profile"] == "fast"

    def test_fails_when_no_profile_promoted(self):
        payload = {
            "profiles": [
                {"profile": "slow", "promote_adaptive_default": False},
            ]
        }
        ok, meta = profile_check(payload)
        assert ok is False
        assert meta["promoted_profiles"] == []

    def test_fails_when_profiles_missing(self):
        # Missing profiles → defaults to [], promoted=[] → ok=False
        ok, meta = profile_check({})
        assert ok is False
        assert meta["promoted_profiles"] == []

    def test_fails_when_profiles_not_a_list(self):
        ok, meta = profile_check({"profiles": "bad"})
        assert ok is False

    def test_multiple_promoted_profiles_all_listed(self):
        payload = {
            "profiles": [
                {"profile": "a", "promote_adaptive_default": True},
                {"profile": "b", "promote_adaptive_default": True},
                {"profile": "c", "promote_adaptive_default": False},
            ]
        }
        ok, meta = profile_check(payload)
        assert ok is True
        assert set(meta["promoted_profiles"]) == {"a", "b"}
