#!/usr/bin/env python3
"""Sync README benchmark token cells with benchmark artifacts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sync_rows(readme_text: str, artifact_path: Path) -> tuple[str, int]:
    payload = load_json(artifact_path)
    rows = payload.get("benchmarks", [])
    if not isinstance(rows, list):
        return readme_text, 0

    updates = 0
    text = readme_text
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        tokens = row.get("tokens")
        savings_pct = row.get("savings_vs_broad_pct")
        if not isinstance(name, str) or not isinstance(tokens, int):
            continue

        # Sync token count column
        token_pattern = re.compile(rf"^\| `{re.escape(name)}` \| `\d+` \|", re.MULTILINE)
        token_replacement = f"| `{name}` | `{tokens}` |"
        text, count = token_pattern.subn(token_replacement, text, count=1)
        updates += count

        # Sync savings percentage column (e.g. "70.8% saved" or "baseline")
        if isinstance(savings_pct, (int, float)) and savings_pct > 0.0:
            savings_str = f"{round(float(savings_pct), 1)}%"
            savings_pattern = re.compile(
                rf"(^\| `{re.escape(name)}` \| `\d+` \| )`[\d.]+%` saved",
                re.MULTILINE,
            )
            savings_replacement = rf"\g<1>`{savings_str}` saved"
            new_text, scount = savings_pattern.subn(savings_replacement, text, count=1)
            if scount:
                text = new_text
                updates += scount

    return text, updates


_LLMS_LOCAL_MAP: dict[str, str] = {
    # benchmark JSON name -> unique fragment in the llms.txt row label
    "broad_inventory": r"rg --files",
    "guidance_scoped_rg": r"scoped",
    "qmd_files": r"qmd search",
    "token_reduce_paths_warm": r"token-reduce-paths\.sh",
    "token_reduce_snippet_warm": r"token-reduce-snippet\.sh",
}


def sync_llms_txt(llms_text: str, local_artifact: Path, composite_artifact: Path) -> tuple[str, int]:
    """Sync llms.txt benchmark table rows from local-benchmark.json and composite-benchmark.json."""
    updates = 0
    text = llms_text

    local_payload = load_json(local_artifact)
    local_rows = {r["name"]: r for r in local_payload.get("benchmarks", []) if isinstance(r, dict)}
    # local-benchmark stores savings in top-level dict, not per-row
    local_savings_map: dict[str, float] = local_payload.get("savings_vs_broad_inventory", {})

    for name, label_fragment in _LLMS_LOCAL_MAP.items():
        row = local_rows.get(name)
        if not isinstance(row, dict):
            continue
        tokens = row.get("tokens")
        savings_pct = local_savings_map.get(name, row.get("savings_vs_broad_pct"))
        if not isinstance(tokens, int):
            continue

        # Sync token count: | <label containing fragment> | `OLD` |
        token_pattern = re.compile(
            rf"(\| [^|]*{label_fragment}[^|]* \| )`\d+`( \|)",
            re.MULTILINE,
        )
        text, n = token_pattern.subn(rf"\g<1>`{tokens}`\g<2>", text)
        updates += n

        # Sync savings pct: `NN.N%` saved
        if isinstance(savings_pct, (int, float)) and savings_pct > 0.0:
            savings_str = f"{round(float(savings_pct), 1)}%"
            pct_pattern = re.compile(
                rf"(\| [^|]*{label_fragment}[^|]* \| `\d+` \| )`[\d.]+%` saved",
                re.MULTILINE,
            )
            text, n = pct_pattern.subn(rf"\g<1>`{savings_str}` saved", text)
            updates += n

    # Sync composite-stack summary line: "Full composite-stack benchmark … `NN.N%` saved, quality-pass."
    composite_payload = load_json(composite_artifact)
    composite_row = next(
        (r for r in composite_payload.get("benchmarks", []) if isinstance(r, dict) and r.get("name") == "composite_stack"),
        None,
    )
    if isinstance(composite_row, dict) and composite_row.get("quality_pass"):
        cs_pct = round(float(composite_row.get("savings_vs_broad_pct", 0.0) or 0.0), 1)
        if cs_pct > 0.0:
            cs_pattern = re.compile(r"`[\d.]+%` saved, quality-pass\.")
            text, n = cs_pattern.subn(f"`{cs_pct}%` saved, quality-pass.", text)
            updates += n

    return text, updates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    readme_path = root / "README.md"
    llms_path = root / "llms.txt"
    if not readme_path.exists():
        raise SystemExit("README.md not found")

    local_artifact = root / "references" / "benchmarks" / "local-benchmark.json"
    composite_artifact = root / "references" / "benchmarks" / "composite-benchmark.json"
    artifact_paths = [local_artifact, composite_artifact]
    missing = [path for path in artifact_paths if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing benchmark artifacts: {missing_text}")

    readme = readme_path.read_text(encoding="utf-8")
    updated = readme
    total_updates = 0
    for artifact_path in artifact_paths:
        updated, count = sync_rows(updated, artifact_path)
        total_updates += count
    if updated != readme:
        readme_path.write_text(updated, encoding="utf-8")

    llms_updates = 0
    if llms_path.exists():
        llms = llms_path.read_text(encoding="utf-8")
        llms_updated, llms_updates = sync_llms_txt(llms, local_artifact, composite_artifact)
        if llms_updated != llms:
            llms_path.write_text(llms_updated, encoding="utf-8")

    print(
        json.dumps(
            {
                "readme": str(readme_path),
                "llms_txt": str(llms_path),
                "readme_updated_rows": total_updates,
                "llms_updated_rows": llms_updates,
                "artifacts": [str(path) for path in artifact_paths],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
