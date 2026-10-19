#!/usr/bin/env python3
"""Download the Boston College COVID-19 daily survey (OSF gpxwa) and
regenerate boston/ fixtures for causal-open-data.

License: CC-BY 4.0
Citation: Cunningham, Fields & Kensinger (2021) Sci Data 8:110
  https://doi.org/10.1038/s41597-021-00886-y
OSF: https://osf.io/gpxwa  doi:10.17605/OSF.IO/GPXWA

The existing boston/boston_data_raw.csv (641 × 7) is an exact subset of
the OSF cleaned daily file. This script reconstructs it with the documented
rule and will not overwrite that file unless --write-raw is passed.

Selection rule for boston_data_raw.csv
--------------------------------------
Source file (Most Recent Data, 2022-05-10 recommended release):
  2c_COVID19_daily_survey_ALL_cleaned_deid_2022-02-06_17_39.csv
Columns: alcohol_bev, TIB, TST, PANAS_PA, PANAS_NA, worry_scale, PHQ9
Keep subjects who have >= 31 complete rows on those 7 columns whose
effective date is before 2020-07-01. The effective date is `ref_date`
when present, otherwise the date of `redcap_timestamp` (one Full-survey
row, unique_id 3839L / subject 130, has a blank `ref_date` but a
2020-04-12 timestamp). The four sum scores exist only on the Full
instrument, so this is a Full-survey subset. Rows stay in OSF file
order (already subject, then date). That rule yields exactly the 20
subjects and 641 rows in the checked-in fixture.

Also writes:
  boston_fixture_row_provenance.csv     one OSF key per fixture row
  boston_data_lagged_within_subject.csv 621 × 14; lag inside each subject
  boston_sub132_allsurveys_10v.csv      142 × 10 contemporaneous Set A
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DATA = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "boston"
FIXTURES = ROOT / "boston"

OSF_NODE = "gpxwa"
OSF_STORAGE_ROOT = f"https://api.osf.io/v2/nodes/{OSF_NODE}/files/osfstorage/"
SOURCE_NAME = "2c_COVID19_daily_survey_ALL_cleaned_deid_2022-02-06_17_39.csv"
SOURCE_SIZE = 21_463_343
SOURCE_SHA256 = "536e8d78753351aa9dcb4c8777225f6a99970957ea255616b6386952f7769eea"
# WaterButler / files.osf.io path for the 2022-05-10 recommended release.
SOURCE_STORAGE_ID = "627a9cf952d172076d80b07e"
SOURCE_GUID = "duwv4"
SOURCE_DOWNLOAD_CANDIDATES = (
    f"https://files.osf.io/v1/resources/{OSF_NODE}/providers/osfstorage/{SOURCE_STORAGE_ID}",
    f"https://osf.io/download/{SOURCE_GUID}/",
    f"https://api.osf.io/v2/files/{SOURCE_STORAGE_ID}/download",
)

POOLED_COLS = [
    "alcohol_bev",
    "TIB",
    "TST",
    "PANAS_PA",
    "PANAS_NA",
    "worry_scale",
    "PHQ9",
]
SET_A_COLS = [
    "TIB",
    "TST",
    "sleepdiary_sleeplatency",
    "sleepdiary_wakes",
    "night_awakening_time",
    "sleepdiary_naptime",
    "socialize_min",
    "people_contact",
    "alcohol_bev",
    "stress",
]
CUTOFF = pd.Timestamp("2020-07-01")
MIN_COMPLETE = 31
SUB132 = 132
PROVENANCE_COLS = [
    "fixture_row",
    "sub_id",
    "ref_date",
    "unique_id",
    "record_id",
    "redcap_repeat_instrument",
    "days_elapsed",
    "source_row",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "tetrad-rs-prep/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def osf_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "tetrad-rs-prep/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def iter_osf_children(folder_url: str):
    url = folder_url
    if "page[size]" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}page[size]=50"
    while url:
        payload = osf_get(url)
        yield from payload.get("data", [])
        url = payload.get("links", {}).get("next")


def find_osf_source() -> dict | None:
    """Walk osfstorage and return the cleaned daily-survey file record."""
    stack = [OSF_STORAGE_ROOT]
    seen: set[str] = set()
    while stack:
        url = stack.pop()
        if url in seen:
            continue
        seen.add(url)
        try:
            children = list(iter_osf_children(url))
        except urllib.error.URLError as exc:
            print(f"OSF list failed for {url}: {exc}", file=sys.stderr)
            continue
        for item in children:
            attrs = item.get("attributes", {})
            kind = attrs.get("kind")
            name = attrs.get("name")
            item_id = item.get("id")
            if kind == "folder" and item_id:
                stack.append(f"{OSF_STORAGE_ROOT}{item_id}/")
            elif kind == "file" and name == SOURCE_NAME:
                return item
    return None


def ensure_source(cache_dir: Path) -> Path:
    dest = cache_dir / SOURCE_NAME
    if dest.is_file() and dest.stat().st_size == SOURCE_SIZE and sha256_file(dest) == SOURCE_SHA256:
        return dest

    urls = list(SOURCE_DOWNLOAD_CANDIDATES)
    try:
        rec = find_osf_source()
    except Exception as exc:  # noqa: BLE001 — walk is best-effort
        print(f"OSF walk failed ({exc}); using pinned download URLs", file=sys.stderr)
        rec = None
    if rec:
        link = rec.get("links", {}).get("download")
        if link:
            urls.insert(0, link)

    last_err: Exception | None = None
    for url in urls:
        print(f"Downloading {SOURCE_NAME} from {url}", file=sys.stderr)
        try:
            download(url, dest)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  failed: {exc}", file=sys.stderr)
            continue
        digest = sha256_file(dest)
        size = dest.stat().st_size
        if size != SOURCE_SIZE or digest != SOURCE_SHA256:
            print(
                f"  checksum/size mismatch size={size} sha256={digest}",
                file=sys.stderr,
            )
            dest.unlink(missing_ok=True)
            continue
        return dest
    raise RuntimeError(f"could not download {SOURCE_NAME}: {last_err}")


def effective_date(df: pd.DataFrame) -> pd.Series:
    """ref_date, falling back to redcap_timestamp for the rare blank ref_date."""
    ref = pd.to_datetime(df["ref_date"], errors="coerce")
    ts = pd.to_datetime(df["redcap_timestamp"], errors="coerce")
    return ref.where(ref.notna(), ts)


def select_pooled20(df: pd.DataFrame) -> pd.DataFrame:
    # Preserve OSF file order: the checked-in fixture is not re-sorted.
    complete = df.dropna(subset=POOLED_COLS).copy()
    complete["_eff_date"] = effective_date(complete)
    early = complete.loc[complete["_eff_date"] < CUTOFF]
    counts = early.groupby("sub_id").size()
    keep = counts[counts >= MIN_COMPLETE].index
    return early.loc[early["sub_id"].isin(keep)].copy()


def lag_within_subject(df: pd.DataFrame, cols: list[str], subject: str = "sub_id") -> pd.DataFrame:
    parts = []
    for _, grp in df.groupby(subject, sort=False):
        if len(grp) < 2:
            continue
        cur = grp[cols].iloc[1:].reset_index(drop=True)
        lag = grp[cols].iloc[:-1].reset_index(drop=True)
        lag.columns = [f"{c}_lag" for c in cols]
        parts.append(pd.concat([cur, lag], axis=1))
    if not parts:
        raise RuntimeError("no within-subject consecutive pairs")
    return pd.concat(parts, ignore_index=True)


def select_sub132(df: pd.DataFrame) -> pd.DataFrame:
    sub = df.loc[df["sub_id"] == SUB132].dropna(subset=SET_A_COLS)
    return sub.sort_values(["ref_date", "record_id"], kind="mergesort").reset_index(drop=True)


def arrays_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if list(a.columns) != list(b.columns) or a.shape != b.shape:
        return False
    return np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float), rtol=0.0, atol=0.0, equal_nan=True)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def provenance_frame(selected: pd.DataFrame) -> pd.DataFrame:
    ref = pd.to_datetime(selected["ref_date"], errors="coerce")
    out = pd.DataFrame(
        {
            "fixture_row": np.arange(len(selected), dtype=int),
            "sub_id": selected["sub_id"].astype(int),
            "ref_date": ref.dt.strftime("%Y-%m-%d"),
            "unique_id": selected["unique_id"],
            "record_id": selected["record_id"],
            "redcap_repeat_instrument": selected["redcap_repeat_instrument"],
            "days_elapsed": selected["days_elapsed"],
            "source_row": selected.index if "source_row" in selected.columns else selected.index,
        }
    )
    # source_row: 0-based index in the sorted full daily table is not the OSF
    # file row. Prefer the original CSV row number when available.
    if "_source_row" in selected.columns:
        out["source_row"] = selected["_source_row"].astype(int)
    return out[PROVENANCE_COLS]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--out-dir", type=Path, default=FIXTURES)
    p.add_argument(
        "--write-raw",
        action="store_true",
        help="overwrite boston/boston_data_raw.csv (off by default; the checked-in file is already the open subset)",
    )
    p.add_argument("--source", type=Path, default=None, help="pre-downloaded cleaned daily CSV")
    args = p.parse_args()

    source = Path(args.source) if args.source else ensure_source(args.cache)
    if sha256_file(source) != SOURCE_SHA256:
        raise SystemExit(f"{source} does not match pinned sha256 {SOURCE_SHA256}")

    raw = pd.read_csv(source, low_memory=False)
    raw["_source_row"] = np.arange(len(raw), dtype=int)  # 0-based row in the OSF file (after header)

    selected = select_pooled20(raw)
    pooled = selected[POOLED_COLS].reset_index(drop=True)
    print(
        f"pooled fixture: {pooled.shape[0]} × {pooled.shape[1]} "
        f"subjects={selected['sub_id'].nunique()} "
        f"instrument={selected['redcap_repeat_instrument'].unique().tolist()} "
        f"dates={selected['_eff_date'].min().date()}..{selected['_eff_date'].max().date()} "
        f"blank_ref_date={int(pd.to_datetime(selected['ref_date'], errors='coerce').isna().sum())}"
    )

    existing_raw = args.out_dir / "boston_data_raw.csv"
    if existing_raw.is_file():
        existing = pd.read_csv(existing_raw)
        if arrays_equal(existing, pooled):
            print(f"OK  reconstructed pooled table matches {existing_raw}")
        else:
            print(f"ERROR reconstructed table does not match {existing_raw}", file=sys.stderr)
            print(f"  existing {existing.shape} reconstructed {pooled.shape}", file=sys.stderr)
            return 2
    else:
        print(f"note: {existing_raw} is missing; pass --write-raw to create it")

    if args.write_raw:
        write_csv(pooled, existing_raw)
        print(f"wrote {existing_raw}")

    lagged = lag_within_subject(selected, POOLED_COLS)
    n_boundary = selected["sub_id"].nunique()
    print(
        f"within-subject lag: {lagged.shape[0]} × {lagged.shape[1]} "
        f"(dropped {n_boundary} subject-boundary rows from {len(selected)})"
    )
    if lagged.shape != (len(selected) - n_boundary, 2 * len(POOLED_COLS)):
        raise SystemExit(f"unexpected lagged shape {lagged.shape}")

    sub132 = select_sub132(raw)
    print(f"sub132 Set A: {sub132.shape[0]} × {len(SET_A_COLS)}")
    if sub132.shape[0] != 142:
        raise SystemExit(f"expected 142 complete Set A rows for subject 132, got {len(sub132)}")

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prov = provenance_frame(selected.reset_index(drop=True))
    # restore source_row from the unsorted-file index stored before sort
    prov["source_row"] = selected["_source_row"].to_numpy()
    write_csv(prov, out_dir / "boston_fixture_row_provenance.csv")
    write_csv(lagged, out_dir / "boston_data_lagged_within_subject.csv")
    write_csv(sub132[SET_A_COLS], out_dir / "boston_sub132_allsurveys_10v.csv")
    print(f"wrote provenance, within-subject lag, and sub132 fixtures under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
