"""Standalone brain-hint helper.

Prints a one-line semantic-memory hint when ``qmd`` or ``gbrain`` is on
PATH. Kept deliberately small to avoid the 50-150ms import tax of pulling
in ``token_reduce_adaptive`` from shell helpers; the router still owns
the canonical implementation in ``brain_hint_line``.
"""
from __future__ import annotations

import shutil
import sys


def hint_line(query: str) -> str | None:
    have_qmd = shutil.which("qmd") is not None
    have_gbrain = shutil.which("gbrain") is not None
    if not (have_qmd or have_gbrain):
        return None
    safe = query.replace('"', '\\"').strip() or "<query>"
    if have_qmd and have_gbrain:
        return f'qmd search "{safe}" -n 5 --files  # or: gbrain search "{safe}"'
    if have_qmd:
        return f'qmd search "{safe}" -n 5 --files'
    return f'gbrain search "{safe}"'


def main(argv: list[str]) -> int:
    query = " ".join(argv).strip()
    line = hint_line(query)
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
