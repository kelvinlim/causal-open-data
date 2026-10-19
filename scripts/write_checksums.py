#!/usr/bin/env python3
"""Write SHA256SUMS for committed dataset files (not raw caches)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codutil import DATASETS, REPO_ROOT, sha256_file  # noqa: E402

INCLUDE_SUFFIXES = {".csv", ".txt", ".md"}
SKIP_DIR_NAMES = {"__pycache__"}


def iter_dataset_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.is_file() and path.suffix in INCLUDE_SUFFIXES:
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "SHA256SUMS",
        help="Output path (sha256sum format).",
    )
    args = parser.parse_args()

    lines = []
    for path in iter_dataset_files(DATASETS):
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines.append(f"{sha256_file(path)}  {rel}")
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} checksums to {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
