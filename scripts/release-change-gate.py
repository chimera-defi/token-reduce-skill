#!/usr/bin/env python3
"""Evaluate whether current benchmark artifacts meet release keep/drop criteria."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"failed to read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"invalid artifact shape (expected object): {path}")
    return raw


def composite_check(
    payload: dict[str, Any], *, min_savings: float
) -> tuple[bool, dict[str, Any]]:
    benchmarks = payload.get("benchmarks", [])
    if not isinstance(benchmarks, list):
        return False, {"reason": "missing benchmarks list"}
    composite = next((row for row in benchmarks if isinstance(row, dict) and row.get("name") == "composite_stack"), None)
    if composite is None:
        return False, {"reason": "missing composite_stack row"}
    quality_pass = bool(composite.get("quality_pass"))
    savings = float(composite.get("savings_vs_broad_pct", 0.0) or 0.0)
    ok = quality_pass and savings >= min_savings
    return ok, {
        "quality_pass": quality_pass,
        "savings_vs_broad_pct": savings,
        "min_required_savings_pct": min_savings,
    }


def adaptive_check(
    payload: dict[str, Any], *, min_savings: float
) -> tuple[bool, dict[str, Any]]:
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        return False, {"reason": "missing summary"}
    quality_pass = bool(summary.get("adaptive_quality_pass"))
    savings = float(summary.get("adaptive_savings_vs_baseline_pct", 0.0) or 0.0)
    ok = quality_pass and savings >= min_savings
    return ok, {
        "adaptive_quality_pass": quality_pass,
        "adaptive_savings_vs_baseline_pct": savings,
        "min_required_savings_pct": min_savings,
    }


def profile_check(payload: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list):
        return False, {"reason": "missing profiles list"}
    promoted = [
        row.get("profile")
        for row in profiles
        if isinstance(row, dict) and bool(row.get("promote_adaptive_default"))
    ]
    ok = len(promoted) > 0
    return ok, {
        "promoted_profiles": promoted,
        "recommended_profile": payload.get("recommended_profile"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--composite-artifact",
        default="references/benchmarks/composite-benchmark.json",
    )
    parser.add_argument(
        "--adaptive-artifact",
        default="references/benchmarks/adaptive-tier-benchmark.json",
    )
    parser.add_argument(
        "--profiles-artifact",
        default="references/benchmarks/profile-presets-benchmark.json",
    )
    parser.add_argument(
        "--min-composite-savings",
        type=float,
        default=60.0,
        help="minimum composite_stack savings vs broad required to pass gate",
    )
    parser.add_argument(
        "--min-adaptive-savings",
        type=float,
        default=0.0,
        help="minimum adaptive savings vs baseline required to pass gate",
    )
    args = parser.parse_args()

    composite_payload = load_json(Path(args.composite_artifact))
    adaptive_payload = load_json(Path(args.adaptive_artifact))
    profiles_payload = load_json(Path(args.profiles_artifact))

    composite_ok, composite_summary = composite_check(
        composite_payload, min_savings=args.min_composite_savings
    )
    adaptive_ok, adaptive_summary = adaptive_check(
        adaptive_payload, min_savings=args.min_adaptive_savings
    )
    profiles_ok, profiles_summary = profile_check(profiles_payload)

    verdict = {
        "composite_gate": {"pass": composite_ok, **composite_summary},
        "adaptive_gate": {"pass": adaptive_ok, **adaptive_summary},
        "profiles_gate": {"pass": profiles_ok, **profiles_summary},
    }
    verdict["release_gate_pass"] = composite_ok and adaptive_ok and profiles_ok
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["release_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
