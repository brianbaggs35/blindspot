"""`python -m app.terms [path]` writes the terms of use as Markdown (default: ../DISCLAIMER.md)."""

import sys
from pathlib import Path

from app.terms.text import render_markdown

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "DISCLAIMER.md"


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else DEFAULT_PATH
    target.write_text(render_markdown(), encoding="utf-8")
    sys.stdout.write(f"Wrote {target}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
