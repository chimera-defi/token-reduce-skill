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


def find_latest_review_artifact(repo_root: Path) -> Path | None:
    root = repo_root / "artifacts" / "token-reduction"
    candidates = sorted(root.glob("adoption-repo-*-review.json"))
    if not candidates:
        return None
    return candidates[-1]


def runtime_reliability_check(
    payload: dict[str, Any],
    *,
    max_helper_error_rate_pct: float,
    max_failure_overhead_pct: float,
    max_retry_overhead_pct: float,
) -> tuple[bool, dict[str, Any]]:
    def metric(name: str) -> float:
        raw = efficiency.get(name)
        if raw is None:
            return 100.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 100.0

    report = payload.get("report", {})
    if not isinstance(report, dict):
        return False, {"reason": "missing report block"}
    telemetry = report.get("telemetry", {})
    if not isinstance(telemetry, dict):
        return False, {"reason": "missing telemetry block"}
    efficiency = telemetry.get("efficiency", {})
    if not isinstance(efficiency, dict):
        return False, {"reason": "missing efficiency block"}

    helper_error_rate = metric("helper_error_rate_pct")
    failure_overhead = metric("failure_overhead_pct")
    retry_overhead = metric("retry_overhead_pct")

    ok = (
        helper_error_rate <= max_helper_error_rate_pct
        and failure_overhead <= max_failure_overhead_pct
        and retry_overhead <= max_retry_overhead_pct
    )
    return ok, {
        "helper_error_rate_pct": helper_error_rate,
        "failure_overhead_pct": failure_overhead,
        "retry_overhead_pct": retry_overhead,
        "max_helper_error_rate_pct": max_helper_error_rate_pct,
        "max_failure_overhead_pct": max_failure_overhead_pct,
        "max_retry_overhead_pct": max_retry_overhead_pct,
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
        "--repo-root",
        default=".",
        help="repo root used to auto-discover latest review artifact",
    )
    parser.add_argument(
        "--review-artifact",
        default="",
        help="optional explicit review artifact path; defaults to latest artifacts/token-reduction/adoption-repo-*-review.json",
    )
    parser.add_argument(
        "--skip-review-gate",
        action="store_true",
        help="skip runtime reliability gate based on measure/review output",
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
    parser.add_argument("--max-helper-error-rate", type=float, default=2.0)
    parser.add_argument("--max-failure-overhead", type=float, default=1.0)
    parser.add_argument("--max-retry-overhead", type=float, default=5.0)
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
    review_ok = True
    review_summary: dict[str, Any] = {"skipped": True}
    if not args.skip_review_gate:
        repo_root = Path(args.repo_root).resolve()
        review_path = (
            Path(args.review_artifact).resolve()
            if args.review_artifact.strip()
            else find_latest_review_artifact(repo_root)
        )
        if review_path is None:
            review_ok = False
            review_summary = {"skipped": False, "reason": "no review artifact found"}
        else:
            review_payload = load_json(review_path)
            review_ok, review_summary = runtime_reliability_check(
                review_payload,
                max_helper_error_rate_pct=args.max_helper_error_rate,
                max_failure_overhead_pct=args.max_failure_overhead,
                max_retry_overhead_pct=args.max_retry_overhead,
            )
            review_summary["artifact"] = str(review_path)
            review_summary["skipped"] = False

    verdict = {
        "composite_gate": {"pass": composite_ok, **composite_summary},
        "adaptive_gate": {"pass": adaptive_ok, **adaptive_summary},
        "profiles_gate": {"pass": profiles_ok, **profiles_summary},
        "runtime_reliability_gate": {"pass": review_ok, **review_summary},
    }
    verdict["release_gate_pass"] = composite_ok and adaptive_ok and profiles_ok and review_ok
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["release_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
