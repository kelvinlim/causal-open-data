#!/usr/bin/env python3
"""Regenerate Boston College COVID sleep/well-being derivatives from OSF gpxwa.

Downloads the recommended 2022-05-10 cleaned daily survey (CC-BY 4.0) into
`.cache/boston/` (gitignored) and writes fixture CSVs under `datasets/boston/`.

Classic 641 x 7 fixture selection rule (reproduces tetrad-rs boston_data_raw.csv
exactly):
  1. Complete cases on alcohol_bev, TIB, TST, PANAS_PA, PANAS_NA, worry_scale, PHQ9.
  2. Effective date = ref_date when present, else the date of redcap_timestamp
     (one Full-survey row, unique_id 3839L / subject 130, has a blank ref_date).
  3. Keep subjects with >= 31 complete rows whose effective date is < 2020-07-01.
  4. Emit those rows in original OSF file order.

The classic file is **not** lagged. tetrad-rs historically lagged the pooled
stack once (640 x 14), which crosses a subject boundary 19 times. This script
also writes a within-subject lag (621 x 14) without changing the classic CSV.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codutil import CACHE, DATASETS, REPO_ROOT, download, write_text  # noqa: E402

OSF_GUID = "duwv4"
OSF_STORAGE_ID = "627a9cf952d172076d80b07e"
OSF_DOWNLOAD = f"https://osf.io/download/{OSF_GUID}/"
OSF_FILENAME = "2c_COVID19_daily_survey_ALL_cleaned_deid_2022-02-06_17_39.csv"
OSF_SHA256 = "536e8d78753351aa9dcb4c8777225f6a99970957ea255616b6386952f7769eea"
OSF_SIZE = 21_463_343

CLASSIC_COLS = [
    "alcohol_bev",
    "TIB",
    "TST",
    "PANAS_PA",
    "PANAS_NA",
    "worry_scale",
    "PHQ9",
]
SET_A = [
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
SET_B = SET_A + [
    "isolation",
    "worry_health",
    "worry_finances",
    "panas_happy3",
    "panas_sad3",
    "panas_angry3",
    "panas_nervous3",
    "panas_active3",
    "depression2",
    "depression4",
]
SET_B15 = [c for c in SET_B if c not in {
    "worry_health",
    "panas_happy3",
    "panas_active3",
    "depression2",
    "depression4",
}]

EXPECTED_SUBJECTS = [
    24, 41, 46, 53, 60, 79, 86, 113, 128, 130,
    132, 141, 146, 152, 162, 199, 251, 286, 290, 350,
]

BOSTON_PRIOR = """\
/knowledge

addtemporal
1 alcohol_bev_lag TIB_lag TST_lag PANAS_PA_lag PANAS_NA_lag worry_scale_lag PHQ9_lag
2 alcohol_bev TIB TST PANAS_PA PANAS_NA worry_scale PHQ9

forbiddirect

requiredirect
"""

CITATION = """\
Cunningham, T.J., Fields, E.C. & Kensinger, E.A. (2021) Boston College daily \
sleep and well-being survey data during early phase of the COVID-19 pandemic. \
Sci Data 8, 110. https://doi.org/10.1038/s41597-021-00886-y

Open Access Link: https://www.nature.com/articles/s41597-021-00886-y
OSF: https://osf.io/gpxwa  doi:10.17605/OSF.IO/GPXWA
License: Creative Commons Attribution 4.0 International (CC-BY 4.0)
"""


def load_osf_daily(cache_dir: Path) -> pd.DataFrame:
    path = download(
        OSF_DOWNLOAD,
        cache_dir / OSF_FILENAME,
        sha256=OSF_SHA256,
        expected_size=OSF_SIZE,
    )
    return pd.read_csv(path, low_memory=False)


def classic_subset(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["ref_date_parsed"] = pd.to_datetime(frame["ref_date"], errors="coerce")
    frame["ts_parsed"] = pd.to_datetime(frame["redcap_timestamp"], errors="coerce")
    frame["eff_date"] = frame["ref_date_parsed"].fillna(frame["ts_parsed"])
    complete = frame.dropna(subset=CLASSIC_COLS)
    early = complete[complete["eff_date"] < "2020-07-01"]
    counts = early.groupby("sub_id").size()
    keep = counts[counts >= 31].index
    got = sorted(int(s) for s in keep)
    if got != EXPECTED_SUBJECTS:
        raise SystemExit(f"subject set mismatch: {got}")
    subset = early[early["sub_id"].isin(keep)].sort_index()
    if len(subset) != 641:
        raise SystemExit(f"expected 641 classic rows, got {len(subset)}")
    return subset


def lag_within_subject(subset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lag the 7 classic variables within each subject (drop the first row)."""
    lagged_frames = []
    prov_rows = []
    for sub_id, group in subset.groupby("sub_id", sort=False):
        group = group.sort_index()
        current = group[CLASSIC_COLS]
        prev = current.shift(1)
        prev.columns = [f"{c}_lag" for c in CLASSIC_COLS]
        paired = pd.concat([current, prev], axis=1).iloc[1:]
        lagged_frames.append(paired)
        cur_ids = group["unique_id"].tolist()
        cur_dates = group["ref_date"].tolist()
        for i in range(1, len(group)):
            prov_rows.append(
                {
                    "sub_id": int(sub_id),
                    "unique_id": cur_ids[i],
                    "unique_id_lag": cur_ids[i - 1],
                    "ref_date": cur_dates[i],
                    "ref_date_lag": cur_dates[i - 1],
                }
            )
    lagged = pd.concat(lagged_frames, ignore_index=True)
    if len(lagged) != 621:
        raise SystemExit(f"expected 621 within-subject lag rows, got {len(lagged)}")
    return lagged, pd.DataFrame(prov_rows)


def write_csv(df: pd.DataFrame, path: Path, *, round6: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.round(6) if round6 else df
    out.to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE / "boston",
        help="Directory for the raw OSF CSV (gitignored).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DATASETS / "boston",
        help="Directory for committed derivatives.",
    )
    args = parser.parse_args()

    daily = load_osf_daily(args.cache_dir)
    subset = classic_subset(daily)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    write_csv(subset[CLASSIC_COLS], out / "boston_data_raw.csv")
    write_text(out / "boston_prior.txt", BOSTON_PRIOR)
    write_text(out / "CITATION.txt", CITATION)

    prov = subset[
        ["sub_id", "ref_date", "unique_id", "redcap_repeat_instrument", "days_elapsed"]
    ].copy()
    write_csv(prov, out / "boston_fixture_row_provenance.csv")
    write_csv(
        subset[["unique_id", "sub_id", "ref_date"]],
        out / "boston_pooled20_fixture_row_ids.csv",
    )

    lagged, lag_prov = lag_within_subject(subset)
    write_csv(lagged, out / "boston_data_lagged_within_subject.csv")
    write_csv(lag_prov, out / "boston_lagged_within_subject_provenance.csv")

    sub132 = daily[daily["sub_id"] == 132].dropna(subset=SET_A)
    write_csv(sub132[SET_A], out / "boston_sub132_allsurveys_10v.csv", round6=True)
    sub79 = daily[daily["sub_id"] == 79].dropna(subset=SET_A)
    write_csv(sub79[SET_A], out / "boston_sub79_allsurveys_10v.csv", round6=True)
    sub132_full = daily[
        (daily["sub_id"] == 132) & (daily["redcap_repeat_instrument"] == "covid19")
    ].dropna(subset=SET_B15)
    write_csv(sub132_full[SET_B15], out / "boston_sub132_fullsurvey_15v.csv", round6=True)
    write_csv(subset[SET_B], out / "boston_pooled20_itemlevel_20v.csv", round6=True)

    print(f"wrote Boston derivatives under {out.relative_to(REPO_ROOT)}")
    print(f"  boston_data_raw.csv: {len(subset)} x {len(CLASSIC_COLS)}")
    print(f"  boston_data_lagged_within_subject.csv: {len(lagged)} x {lagged.shape[1]}")
    print(f"  boston_sub132_allsurveys_10v.csv: {len(sub132)} x {len(SET_A)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
