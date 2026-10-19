#!/usr/bin/env python3
"""Download MyConnectome parcellated scrubbed timeseries and build fixtures.

Sources (Poldrack lab public derivatives):
  https://web.stanford.edu/group/poldracklab/myconnectome-data/base/combined_data_scrubbed/subNNN.txt
  https://web.stanford.edu/group/poldracklab/myconnectome-data/base/parcellation/parcel_data.txt

Raw BOLD is OpenNeuro ds000031 (CC0). The project site also dedicates the
data under ODC-PDDL 1.0. Both are public-domain dedications.

Session sub066 is used because it has the lowest mean FD (0.0885) and
zero censored frames (tmask keeps all 518 TRs).

Outputs
-------
(a) myconnectome_sub066_518x50.csv
    50-ROI network-balanced left-hemisphere subset listed in
    scripts/myconnectome_roi50.txt (copied to myconnectome/) (Zero / subcortical excluded).

(b) myconnectome_sub066_518x379.csv
    Deterministic ~379-ROI full-rank subset. Rule (see select_roi379):
      1. Eligible = cortical parcels whose network is not Zero and whose
         lobe is not subcortical (network != na).
      2. Target n = 379 so T=518 > p (the full 630-ROI matrix is rank 518).
      3. Allocate slots to networks with the largest-remainder method,
         proportional to each network's eligible count. Ties break by
         network name (ASCII).
      4. Inside a network, take the lowest parcel IDs.
    The script verifies np.linalg.matrix_rank == 379 and prints the
    covariance condition number.

The 50-ROI CSV is a checked-in test fixture. The 379-ROI CSV is written
when it is under --max-commit-bytes (default 3 MiB); otherwise only the
ROI list and a sha256 sidecar are committed and the CSV is produced in
the cache for the speed profile.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DATA = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "myconnectome"
FIXTURES = ROOT / "myconnectome"

MC_BASE = "https://web.stanford.edu/group/poldracklab/myconnectome-data/base"
SESSION = "sub066"
TIMESERIES_URL = f"{MC_BASE}/combined_data_scrubbed/{SESSION}.txt"
PARCEL_URL = f"{MC_BASE}/parcellation/parcel_data.txt"
TARGET_379 = 379
EXCLUDE_NETWORKS = {"zero", "na", "nan", "none", ""}
EXCLUDE_LOBES = {"subcortical"}
ROI50_LIST = SCRIPTS_DATA / "myconnectome_roi50.txt"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    print(f"Downloading {url} -> {dest}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "tetrad-rs-prep/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return dest


def normalize_network(name: object) -> str:
    return str(name).strip().replace(" ", "_").replace("-", "_")


def colname(parcel: int, hemi: str, network: str, lobe: str) -> str:
    net = normalize_network(network)
    lobe_s = str(lobe).strip().lower()
    if lobe_s in EXCLUDE_LOBES or net.lower() in EXCLUDE_NETWORKS:
        if lobe_s in EXCLUDE_LOBES:
            return f"P{int(parcel):03d}_subcort_{hemi}"
        if net.lower() == "zero":
            return f"P{int(parcel):03d}_Zero_{hemi}"
        return f"P{int(parcel):03d}_{net}_{hemi}"
    return f"P{int(parcel):03d}_{net}_{hemi}"


def load_parcels(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["parcel", "hemi", "x", "y", "z", "lobe", "region", "network", "yeo7", "yeo17"],
    )
    df["parcel"] = df["parcel"].astype(int)
    df["network_norm"] = df["network"].map(normalize_network)
    df["colname"] = [
        colname(int(r.parcel), str(r.hemi), str(r.network), str(r.lobe))
        for r in df.itertuples(index=False)
    ]
    return df


def eligible_mask(df: pd.DataFrame) -> pd.Series:
    net = df["network_norm"].str.lower()
    lobe = df["lobe"].astype(str).str.strip().str.lower()
    return ~net.isin(EXCLUDE_NETWORKS) & ~lobe.isin(EXCLUDE_LOBES)


def largest_remainder(sizes: dict[str, int], target: int) -> dict[str, int]:
    total = sum(sizes.values())
    if total == 0:
        raise ValueError("no eligible parcels")
    raw = {k: target * v / total for k, v in sizes.items()}
    floors = {k: int(math.floor(x)) for k, x in raw.items()}
    leftover = target - sum(floors.values())
    # Largest fractional part first; ties by network name.
    order = sorted(sizes, key=lambda k: (-(raw[k] - floors[k]), k))
    out = dict(floors)
    for k in order[:leftover]:
        out[k] += 1
    return out


def select_roi379(parcels: pd.DataFrame, target: int = TARGET_379) -> list[str]:
    elig = parcels.loc[eligible_mask(parcels)].copy()
    sizes = elig.groupby("network_norm").size().to_dict()
    quota = largest_remainder(sizes, target)
    chosen: list[str] = []
    for net in sorted(quota):
        n = quota[net]
        block = elig.loc[elig["network_norm"] == net].sort_values("parcel")
        chosen.extend(block["colname"].tolist()[:n])
    if len(chosen) != target:
        raise RuntimeError(f"379-ROI selector produced {len(chosen)} names")
    # Stable order: parcel id (encoded in the P### prefix).
    chosen.sort(key=lambda name: int(name[1:4]))
    return chosen


def write_csv(df: pd.DataFrame, path: Path, float_format: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format=float_format)
    return path


def matrix_stats(x: np.ndarray) -> tuple[int, float]:
    # Bias-corrected covariance, matching tetrad-rs / Tetrad.
    cov = np.cov(x, rowvar=False, ddof=1)
    rank = int(np.linalg.matrix_rank(cov, tol=1e-8))
    cond = float(np.linalg.cond(cov))
    return rank, cond


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--out-dir", type=Path, default=FIXTURES)
    p.add_argument("--session", default=SESSION)
    p.add_argument("--target-379", type=int, default=TARGET_379)
    p.add_argument("--max-commit-bytes", type=int, default=3 * 1024 * 1024)
    p.add_argument("--force-379", action="store_true", help="always write the 379 CSV under --out-dir")
    p.add_argument("--timeseries", type=Path, default=None)
    p.add_argument("--parcels", type=Path, default=None)
    args = p.parse_args()

    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    ts_path = args.timeseries or download(
        TIMESERIES_URL.replace(SESSION, args.session), cache / f"{args.session}.txt"
    )
    parcel_path = args.parcels or download(PARCEL_URL, cache / "parcel_data.txt")

    x = np.loadtxt(ts_path)
    if x.shape != (518, 630):
        raise SystemExit(f"{ts_path} has shape {x.shape}, expected (518, 630)")
    parcels = load_parcels(parcel_path)
    if len(parcels) != 630:
        raise SystemExit(f"{parcel_path} has {len(parcels)} rows, expected 630")

    labels_path = args.out_dir / "myconnectome_parcel_labels.csv"
    write_csv(parcels, labels_path)
    print(f"wrote parcel labels {labels_path} ({len(parcels)} rows)")

    roi50 = [ln.strip() for ln in ROI50_LIST.read_text().splitlines() if ln.strip()]
    if len(roi50) != 50:
        raise SystemExit(f"{ROI50_LIST} has {len(roi50)} names, expected 50")
    name_to_idx = {n: i for i, n in enumerate(parcels["colname"])}
    missing = [n for n in roi50 if n not in name_to_idx]
    if missing:
        raise SystemExit(f"roi50 names missing from parcel table: {missing[:5]}")
    idx50 = [name_to_idx[n] for n in roi50]
    df50 = pd.DataFrame(x[:, idx50], columns=roi50)
    out50 = args.out_dir / f"myconnectome_{args.session}_518x50.csv"
    write_csv(df50, out50)
    r50, c50 = matrix_stats(df50.to_numpy())
    max_abs_r = np.corrcoef(df50.to_numpy(), rowvar=False)
    np.fill_diagonal(max_abs_r, 0.0)
    print(
        f"50-ROI: {df50.shape[0]} × {df50.shape[1]} rank={r50} "
        f"cond={c50:.3e} max|r|={np.nanmax(np.abs(max_abs_r)):.3f} -> {out50}"
    )

    roi379 = select_roi379(parcels, args.target_379)
    idx379 = [name_to_idx[n] for n in roi379]
    df379 = pd.DataFrame(x[:, idx379], columns=roi379)
    r379, c379 = matrix_stats(df379.to_numpy())
    if r379 != args.target_379:
        raise SystemExit(f"379-ROI covariance rank {r379} != {args.target_379}")
    print(
        f"379-ROI: {df379.shape[0]} × {df379.shape[1]} rank={r379} cond={c379:.3e}"
    )
    nets: dict[str, int] = defaultdict(int)
    for name in roi379:
        # P###_NETWORK_H
        parts = name.split("_")
        nets["_".join(parts[1:-1])] += 1
    print("379-ROI per-network counts:", dict(sorted(nets.items())))

    roi379_list = args.out_dir / "myconnectome_roi379.txt"
    roi379_list.write_text("\n".join(roi379) + "\n")

    # Try a compact float format first so a committed CSV can stay under 3 MiB.
    out379_cache = cache / f"myconnectome_{args.session}_518x{args.target_379}.csv"
    write_csv(df379, out379_cache, float_format="%.8g")
    digest = sha256_file(out379_cache)
    size = out379_cache.stat().st_size
    sidecar = args.out_dir / f"myconnectome_{args.session}_518x{args.target_379}.sha256"
    sidecar.write_text(f"{digest}  myconnectome_{args.session}_518x{args.target_379}.csv\n")
    print(f"379-ROI CSV {size} bytes sha256={digest} at {out379_cache}")

    out379 = args.out_dir / f"myconnectome_{args.session}_518x{args.target_379}.csv"
    if args.force_379 or size <= args.max_commit_bytes:
        write_csv(df379, out379, float_format="%.8g")
        print(f"wrote fixture {out379} ({size} bytes)")
    else:
        if out379.exists():
            print(f"left existing {out379} in place (oversize {size} bytes)")
        else:
            print(
                f"379-ROI CSV is {size} bytes (> {args.max_commit_bytes}); "
                f"not copying into {args.out_dir}. Regenerated via this script "
                f"or scripts/speed_profile.py (checksum in {sidecar.name})."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
