"""Bloat guard for ``SKILL.md``.

Skills are loaded into every conversation in every consuming repo, so each
line in ``SKILL.md`` is a context tax. Track I (2026-06-21 round 2) brought
the file from 314 to 184 lines by extracting long-form sections into
``references/*.md``. This test locks that win in place: a future PR cannot
silently re-bloat ``SKILL.md`` past the threshold without a deliberate bump
here, which should prompt a reviewer to ask whether the new content belongs
in a reference file instead.

The threshold (230) is the 220-line brief target plus a 10-line buffer.
"""
from __future__ import annotations

from pathlib import Path

SKILL_MD = Path(__file__).resolve().parents[2] / "SKILL.md"
MAX_LINES = 230


def test_skill_md_stays_under_bloat_threshold() -> None:
    line_count = sum(1 for _ in SKILL_MD.open(encoding="utf-8"))
    assert line_count <= MAX_LINES, (
        f"SKILL.md is {line_count} lines, exceeds the {MAX_LINES}-line bloat "
        f"guard. Skills load into every conversation in every consuming repo; "
        f"extract long-form sections into references/*.md and link from "
        f"SKILL.md instead of inlining. If the new content genuinely belongs "
        f"in SKILL.md, raise MAX_LINES in scripts/tests/test_skill_size.py "
        f"deliberately and explain in the commit message."
    )
