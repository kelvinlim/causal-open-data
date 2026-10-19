"""Shared helpers for causal-open-data prep and fetch scripts."""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("COD_CACHE", REPO_ROOT / ".cache"))
DATASETS = REPO_ROOT / "datasets"

USER_AGENT = "causal-open-data/1.0 (https://github.com/kelvinlim/causal-open-data)"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(
    url: str,
    dest: Path,
    *,
    sha256: str | None = None,
    expected_size: int | None = None,
) -> Path:
    """Download `url` to `dest` unless a matching cache file already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if sha256:
            got = sha256_file(dest)
            if got == sha256:
                return dest
            print(f"cached {dest} has sha256 {got}, re-downloading", file=sys.stderr)
            dest.unlink()
        elif expected_size is not None and dest.stat().st_size == expected_size:
            return dest
        elif expected_size is None:
            return dest

    print(f"downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as response, dest.open("wb") as out:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)

    size = dest.stat().st_size
    if expected_size is not None and size != expected_size:
        raise SystemExit(f"size mismatch for {dest}: got {size}, expected {expected_size}")
    if sha256:
        got = sha256_file(dest)
        if got != sha256:
            raise SystemExit(f"sha256 mismatch for {dest}: got {got}, expected {sha256}")
    return dest


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def read_sha256sums(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        mapping[rel] = digest
    return mapping
