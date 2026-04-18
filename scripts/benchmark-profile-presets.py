#!/usr/bin/env python3
"""Benchmark routing profile presets for load vs savings tradeoffs."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "references" / "benchmarks" / "profile-presets-benchmark.json"
PROFILES = ["minimal-load", "balanced", "max-savings"]


def run(cmd: list[str], *, env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def main() -> int:
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="token-reduce-profiles-") as tmp_dir:
        tmp = Path(tmp_dir)
        for profile in PROFILES:
            config_path = tmp / f"{profile}.config.json"
            bench_path = tmp / f"{profile}.benchmark.json"
            env = dict(os.environ)
            env["TOKEN_REDUCE_CONFIG_PATH"] = str(config_path)

            code, out, err = run(
                ["uv", "run", "scripts/token-reduce-settings.py", "profile", "apply", profile],
                env=env,
            )
            if code != 0:
                raise SystemExit(f"profile apply failed for {profile}: {(out + err).strip()}")

            code, out, err = run(
                [
                    "uv",
                    "run",
                    "--with",
                    "tiktoken",
                    "scripts/benchmark-adaptive-tiering.py",
                    "--output",
                    str(bench_path),
                ],
                env=env,
            )
            if code != 0:
                raise SystemExit(f"profile benchmark failed for {profile}: {(out + err).strip()}")

            bench = json.loads(bench_path.read_text(encoding="utf-8"))
            summary = bench.get("summary", {})
            verdict = bench.get("verdict", {})
            rows.append(
                {
                    "profile": profile,
                    "baseline_tokens": int(summary.get("baseline_tokens", 0) or 0),
                    "adaptive_tokens": int(summary.get("adaptive_tokens", 0) or 0),
                    "adaptive_savings_vs_baseline_pct": float(
                        summary.get("adaptive_savings_vs_baseline_pct", 0.0) or 0.0
                    ),
                    "adaptive_quality_pass": bool(summary.get("adaptive_quality_pass", False)),
                    "promote_adaptive_default": bool(verdict.get("promote_adaptive_default", False)),
                }
            )

    best = sorted(
        rows,
        key=lambda row: (
            int(bool(row["adaptive_quality_pass"])),
            float(row["adaptive_savings_vs_baseline_pct"]),
        ),
        reverse=True,
    )[0]

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profiles": rows,
        "recommended_profile": best["profile"],
        "recommendation_reason": (
            "highest adaptive savings among profiles that preserve benchmark quality"
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
