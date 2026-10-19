#!/usr/bin/env python3
"""Download pinned causal-open-data fixtures and verify SHA256.

This repository is public. Consumers (tetrad-rs, ezcausal, opencausal)
should pin a commit or tag. A GitHub token is optional; it is helpful
for API rate limits or private forks.

Examples:

  python3 scripts/fetch_fixtures.py --ref <commit> --dest ./fixtures
  python3 scripts/fetch_fixtures.py --ref <tag> --all --dest ./fixtures

Environment: GITHUB_TOKEN or GH_TOKEN (optional).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codutil import USER_AGENT, sha256_bytes  # noqa: E402

DEFAULT_REPO = "kelvinlim/causal-open-data"
SUMS_NAME = "SHA256SUMS"
CI_LIST_NAME = "datasets/CI_FIXTURES.txt"


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def api_get(url: str, token: str | None, accept: str) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GET {url} failed: HTTP {exc.code} {exc.reason}") from exc


def contents_url(repo: str, path: str, ref: str) -> str:
    quoted = urllib.parse.quote(path)
    return (
        f"https://api.github.com/repos/{repo}/contents/{quoted}"
        f"?ref={urllib.parse.quote(ref)}"
    )


def fetch_file(repo: str, path: str, ref: str, token: str | None) -> bytes:
    """Fetch a file via the Contents API, falling back to git blobs over 1 MiB."""
    meta = json.loads(
        api_get(contents_url(repo, path, ref), token, "application/vnd.github+json").decode("utf-8")
    )
    if not isinstance(meta, dict) or meta.get("type") != "file":
        raise SystemExit(f"unexpected contents payload for {path}")
    encoding = meta.get("encoding")
    content = meta.get("content")
    if encoding == "base64" and content:
        return base64.b64decode(content)
    git_url = meta.get("git_url")
    if git_url:
        blob = json.loads(api_get(git_url, token, "application/vnd.github+json").decode("utf-8"))
        if blob.get("encoding") == "base64" and blob.get("content"):
            return base64.b64decode(blob["content"])
        if isinstance(blob.get("content"), str):
            return blob["content"].encode("utf-8")
    download_url = meta.get("download_url")
    if download_url:
        return api_get(download_url, token, "*/*")
    raise SystemExit(f"cannot download {path}: no content, git_url, or download_url")


def parse_sums(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        mapping[rel] = digest
    return mapping


def parse_ci_list(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name (public by default)")
    parser.add_argument("--ref", required=True, help="Pinned tag or commit SHA (not main).")
    parser.add_argument("--dest", type=Path, required=True, help="Directory to write files into.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch every path in SHA256SUMS, including the non-CI 630-ROI matrix.",
    )
    args = parser.parse_args()

    token = github_token()
    if token is None:
        print(
            "note: no GITHUB_TOKEN/GH_TOKEN; public downloads work unauthenticated "
            "(token is optional; helpful for rate limits / private forks)",
            file=sys.stderr,
        )

    sums_text = fetch_file(args.repo, SUMS_NAME, args.ref, token).decode("utf-8")
    mapping = parse_sums(sums_text)
    if args.all:
        wanted = sorted(mapping)
    else:
        ci_text = fetch_file(args.repo, CI_LIST_NAME, args.ref, token).decode("utf-8")
        wanted = parse_ci_list(ci_text)
        missing = [p for p in wanted if p not in mapping]
        if missing:
            raise SystemExit(f"CI paths missing from SHA256SUMS: {missing}")

    args.dest.mkdir(parents=True, exist_ok=True)
    (args.dest / SUMS_NAME).write_text(sums_text, encoding="utf-8")
    fetched = []
    for rel in wanted:
        data = fetch_file(args.repo, rel, args.ref, token)
        expected = mapping[rel]
        got = sha256_bytes(data)
        if got != expected:
            raise SystemExit(f"sha256 mismatch for {rel}: {got} != {expected}")
        dest = args.dest / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        fetched.append(rel)
        print(f"ok  {rel}")

    meta = {"repo": args.repo, "ref": args.ref, "files": fetched}
    (args.dest / "FETCH_META.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"fetched {len(fetched)} files from {args.repo}@{args.ref} -> {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
