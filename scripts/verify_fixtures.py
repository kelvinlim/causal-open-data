#!/usr/bin/env python3
"""Shape, license-scope, checksum, and rank checks for committed fixtures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codutil import DATASETS, REPO_ROOT, read_sha256sums, sha256_file  # noqa: E402

EXPECTED_SHAPES = {
    "datasets/boston/boston_data_raw.csv": (641, 7),
    "datasets/boston/boston_data_lagged_within_subject.csv": (621, 14),
    "datasets/boston/boston_fixture_row_provenance.csv": (641, 5),
    "datasets/boston/boston_sub132_allsurveys_10v.csv": (142, 10),
    "datasets/boston/boston_sub79_allsurveys_10v.csv": (142, 10),
    "datasets/boston/boston_sub132_fullsurvey_15v.csv": (61, 15),
    "datasets/boston/boston_pooled20_itemlevel_20v.csv": (641, 20),
    "datasets/myconnectome/myconnectome_sub066_518x50.csv": (518, 50),
    "datasets/myconnectome/myconnectome_sub066_518x379.csv": (518, 379),
    "datasets/myconnectome/large/myconnectome_sub066_518x630.csv": (518, 630),
}

CLASSIC_COLS = [
    "alcohol_bev",
    "TIB",
    "TST",
    "PANAS_PA",
    "PANAS_NA",
    "worry_scale",
    "PHQ9",
]
EXPECTED_SUBJECTS = {
    24, 41, 46, 53, 60, 79, 86, 113, 128, 130,
    132, 141, 146, 152, 162, 199, 251, 286, 290, 350,
}
FORBIDDEN_NAME_PARTS = ("hcp", "jang", "restricted")
CI_LIST = REPO_ROOT / "datasets" / "CI_FIXTURES.txt"
LARGE_630 = "datasets/myconnectome/large/myconnectome_sub066_518x630.csv"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sums",
        type=Path,
        default=REPO_ROOT / "SHA256SUMS",
    )
    args = parser.parse_args()

    if not args.sums.exists():
        fail(f"missing {args.sums}")

    mapping = read_sha256sums(args.sums)
    for rel, expected in mapping.items():
        path = REPO_ROOT / rel
        if not path.exists():
            fail(f"checksum path missing: {rel}")
        got = sha256_file(path)
        if got != expected:
            fail(f"sha256 mismatch {rel}: {got} != {expected}")

    for rel, (n_rows, n_cols) in EXPECTED_SHAPES.items():
        path = REPO_ROOT / rel
        if not path.exists():
            fail(f"missing {rel}")
        frame = pd.read_csv(path)
        if frame.shape != (n_rows, n_cols):
            fail(f"{rel} shape {frame.shape} != {(n_rows, n_cols)}")

    classic = pd.read_csv(DATASETS / "boston" / "boston_data_raw.csv")
    if list(classic.columns) != CLASSIC_COLS:
        fail(f"classic columns {list(classic.columns)}")
    prov = pd.read_csv(DATASETS / "boston" / "boston_fixture_row_provenance.csv")
    subjects = set(int(s) for s in prov["sub_id"].unique())
    if subjects != EXPECTED_SUBJECTS:
        fail(f"classic subjects {sorted(subjects)}")
    if not (prov["redcap_repeat_instrument"] == "covid19").all():
        fail("classic fixture is not all Full-survey (covid19) rows")

    lagged = pd.read_csv(DATASETS / "boston" / "boston_data_lagged_within_subject.csv")
    expected_lag_cols = CLASSIC_COLS + [f"{c}_lag" for c in CLASSIC_COLS]
    if list(lagged.columns) != expected_lag_cols:
        fail(f"lagged columns {list(lagged.columns)}")

    roi50 = (DATASETS / "myconnectome" / "myconnectome_roi50.txt").read_text().splitlines()
    roi379 = (DATASETS / "myconnectome" / "myconnectome_roi379.txt").read_text().splitlines()
    m50 = pd.read_csv(DATASETS / "myconnectome" / "myconnectome_sub066_518x50.csv")
    m379 = pd.read_csv(DATASETS / "myconnectome" / "myconnectome_sub066_518x379.csv")
    if list(m50.columns) != roi50:
        fail("518x50 columns != myconnectome_roi50.txt")
    if list(m379.columns) != roi379:
        fail("518x379 columns != myconnectome_roi379.txt")
    rank = int(np.linalg.matrix_rank(m379.to_numpy()))
    if rank != 379:
        fail(f"518x379 rank {rank} != 379")
    rank630 = int(np.linalg.matrix_rank(
        pd.read_csv(DATASETS / "myconnectome" / "large" / "myconnectome_sub066_518x630.csv").to_numpy()
    ))
    if rank630 != 518:
        fail(f"518x630 rank {rank630} != 518 (expected T-limited)")

    if not CI_LIST.exists():
        fail("missing datasets/CI_FIXTURES.txt")
    ci_paths = [
        line.strip()
        for line in CI_LIST.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if LARGE_630 in ci_paths:
        fail("630-ROI matrix must stay outside the CI fixture set")
    for rel in ci_paths:
        if not (REPO_ROOT / rel).exists():
            fail(f"CI fixture missing: {rel}")

    for path in DATASETS.rglob("*"):
        lowered = path.name.lower()
        if any(part in lowered for part in FORBIDDEN_NAME_PARTS):
            fail(f"forbidden filename {path.relative_to(REPO_ROOT)}")

    print("verify_fixtures: ok")
    print(f"  checksums: {len(mapping)}")
    print(f"  CI fixtures: {len(ci_paths)}")
    print(f"  classic Boston: 641 x 7, {len(EXPECTED_SUBJECTS)} subjects")
    print(f"  MyConnectome 379 rank: {rank}; 630 rank: {rank630} (non-CI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
