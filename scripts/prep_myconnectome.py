#!/usr/bin/env python3
"""Regenerate MyConnectome parcellated rsfMRI derivatives from Poldrack lab files.

Downloads session timeseries and parcel labels from
https://web.stanford.edu/group/poldracklab/myconnectome-data/ (CC0 / ODC-PDDL)
into `.cache/myconnectome/` (gitignored) and writes:

  datasets/myconnectome/myconnectome_sub066_518x50.csv   CI, 50-ROI
  datasets/myconnectome/myconnectome_sub066_518x379.csv  CI, full-rank large
  datasets/myconnectome/large/myconnectome_sub066_518x630.csv
      NOT in the CI fixture set: T=518 < p=630, covariance is rank-deficient.

No HCP or other restricted participant data is downloaded or written.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codutil import CACHE, DATASETS, REPO_ROOT, download, write_text  # noqa: E402

STANFORD_BASE = "https://web.stanford.edu/group/poldracklab/myconnectome-data/base"
DEFAULT_SESSION = "sub066"
ROUND = 6
TARGET_379 = 379
ROI50_FIVE = ("DMN", "Somatomotor")
EXCLUDED_NETWORKS = {"Zero", "subcort"}

LARGE_README = """\
# MyConnectome 630-ROI matrix (not a CI fixture)

`myconnectome_sub066_518x630.csv` is the full parcellated scrubbed timeseries
for session 066: **518 timepoints x 630 parcels** (616 cortical + 14
subcortical). TR = 1.16 s. Mean FD = 0.0885 (lowest of the 84 sessions);
the temporal mask keeps all 518 frames.

**Do not use this file in default CI.** T < p, so the sample covariance has
rank 518 and is singular. Fisher Z with small conditioning sets can still
run; SEM-BIC and large conditioning sets will hit singular matrices.

Use the CI-friendly full-rank stand-in instead:

    datasets/myconnectome/myconnectome_sub066_518x379.csv

Source: Poldrack lab `combined_data_scrubbed/sub066.txt` (CC0 / ODC-PDDL).
Raw NIfTI live on OpenNeuro ds000031; they are not mirrored here.
"""


def network_norm(network, lobe) -> str:
    name = str(network)
    if name in {"na", "nan"} or str(lobe) == "subcortical":
        return "subcort"
    return name.replace("-", "_").replace(" ", "_")


def colname(parcel: int, network: str, hemi: str) -> str:
    return f"P{int(parcel):03d}_{network}_{hemi}"


def load_labels(cache_dir: Path) -> pd.DataFrame:
    path = download(
        f"{STANFORD_BASE}/parcellation/parcel_data.txt",
        cache_dir / "parcel_data.txt",
    )
    labels = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["parcel", "hemi", "x", "y", "z", "lobe", "region", "network", "yeo7", "yeo17"],
    )
    labels["network_norm"] = [
        network_norm(n, lobe) for n, lobe in zip(labels["network"], labels["lobe"])
    ]
    labels["colname"] = [
        colname(p, n, h)
        for p, n, h in zip(labels["parcel"], labels["network_norm"], labels["hemi"])
    ]
    return labels


def load_session(cache_dir: Path, session: str) -> np.ndarray:
    path = download(
        f"{STANFORD_BASE}/combined_data_scrubbed/{session}.txt",
        cache_dir / f"{session}.txt",
    )
    data = np.loadtxt(path)
    if data.shape != (518, 630):
        raise SystemExit(f"{session} expected shape (518, 630), got {data.shape}")
    return data


def largest_remainder(counts: pd.Series, target: int) -> pd.Series:
    """Hamilton / largest-remainder allocation. Ties break by network name."""
    quotas = counts * target / int(counts.sum())
    floors = np.floor(quotas).astype(int)
    remain = target - int(floors.sum())
    frac = quotas - floors
    order = sorted(counts.index, key=lambda name: (-float(frac[name]), name))
    alloc = floors.copy()
    for name in order[:remain]:
        alloc[name] += 1
    if int(alloc.sum()) != target:
        raise SystemExit(f"allocation sum {int(alloc.sum())} != {target}")
    return alloc


def spaced_indices(n: int, k: int) -> list[int]:
    """Inclusive-endpoint even spacing; unique when k <= n."""
    if k < 1 or k > n:
        raise SystemExit(f"cannot take {k} of {n}")
    if k == 1:
        return [0]
    idx = [int(round(i * (n - 1) / (k - 1))) for i in range(k)]
    if len(set(idx)) != k:
        raise SystemExit(f"spacing collision for n={n} k={k}: {idx}")
    return idx


def select_roi50(labels: pd.DataFrame) -> list[str]:
    """Left-hemisphere, exclude Zero/subcortical; 5 DMN + 5 Somatomotor, else 4.

    Columns are emitted in increasing parcel-ID order. This reproduces the
    curated 50-ROI list used as an open replacement for a 520 x 50 HCP-style
    series (HCP data themselves are not redistributable and are not included).
    """
    eligible = labels[
        (labels["hemi"] == "L") & (~labels["network_norm"].isin(EXCLUDED_NETWORKS))
    ]
    chosen: list[int] = []
    for net, group in eligible.groupby("network_norm", sort=True):
        take = 5 if net in ROI50_FIVE else 4
        chosen.extend(group.sort_values("parcel")["parcel"].head(take).tolist())
    chosen.sort()
    names = labels.set_index("parcel").loc[chosen, "colname"].tolist()
    if len(names) != 50:
        raise SystemExit(f"roi50 expected 50 names, got {len(names)}")
    return names


def select_roi379(labels: pd.DataFrame) -> list[str]:
    """Both hemispheres, exclude Zero/subcortical, largest-remainder to 379.

    Within each network, take evenly spaced parcel IDs (inclusive endpoints)
    so left and right hemispheres both appear. Columns are emitted in
    increasing parcel-ID order. T=518 > p=379, so the covariance is full rank.
    """
    eligible = labels[~labels["network_norm"].isin(EXCLUDED_NETWORKS)].copy()
    counts = eligible.groupby("network_norm").size().sort_index()
    alloc = largest_remainder(counts, TARGET_379)
    chosen: list[int] = []
    for net, k in alloc.items():
        ids = eligible.loc[eligible["network_norm"] == net, "parcel"].sort_values().to_numpy()
        chosen.extend(ids[i] for i in spaced_indices(len(ids), int(k)))
    chosen.sort()
    names = labels.set_index("parcel").loc[chosen, "colname"].tolist()
    if len(names) != TARGET_379:
        raise SystemExit(f"roi379 expected {TARGET_379} names, got {len(names)}")
    return names


def write_matrix(data: np.ndarray, columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(data, columns=columns).round(ROUND)
    frame.to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE / "myconnectome",
        help="Directory for Stanford timeseries / labels (gitignored).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DATASETS / "myconnectome",
        help="Directory for committed derivatives.",
    )
    parser.add_argument("--session", default=DEFAULT_SESSION, help="Session code, e.g. sub066.")
    parser.add_argument(
        "--skip-large",
        action="store_true",
        help="Do not write the rank-deficient 630-ROI matrix.",
    )
    args = parser.parse_args()

    labels = load_labels(args.cache_dir)
    data = load_session(args.cache_dir, args.session)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    label_out = labels[
        ["parcel", "hemi", "x", "y", "z", "lobe", "region", "network", "yeo7", "yeo17", "colname"]
    ]
    label_out.to_csv(out / "myconnectome_parcel_labels.csv", index=False)

    roi50 = select_roi50(labels)
    roi379 = select_roi379(labels)
    write_text(out / "myconnectome_roi50.txt", "\n".join(roi50))
    write_text(out / "myconnectome_roi379.txt", "\n".join(roi379))

    col_index = {name: i for i, name in enumerate(labels["colname"])}
    idx50 = [col_index[c] for c in roi50]
    idx379 = [col_index[c] for c in roi379]
    write_matrix(data[:, idx50], roi50, out / f"myconnectome_{args.session}_518x50.csv")
    write_matrix(data[:, idx379], roi379, out / f"myconnectome_{args.session}_518x379.csv")

    rank = int(np.linalg.matrix_rank(data[:, idx379]))
    if rank != TARGET_379:
        raise SystemExit(f"379-ROI subset is rank {rank}, expected {TARGET_379}")

    if not args.skip_large:
        large = out / "large"
        write_matrix(data, labels["colname"].tolist(), large / f"myconnectome_{args.session}_518x630.csv")
        write_text(large / "README.md", LARGE_README)

    print(f"wrote MyConnectome derivatives under {out.relative_to(REPO_ROOT)}")
    print(f"  {args.session} 518x50 columns={len(roi50)}")
    print(f"  {args.session} 518x379 rank={rank}")
    if not args.skip_large:
        print(f"  {args.session} 518x630 NON-CI (T<p)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
