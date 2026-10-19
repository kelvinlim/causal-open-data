# causal-open-data

Openly licensed test and benchmark datasets for causal discovery, shared by
[tetrad-rs](https://github.com/kelvinlim/tetrad-rs),
[ezcausal](https://github.com/kelvinlim/ezcausal), and
[opencausal](https://github.com/kelvinlim/opencausal).

**Keep this repository private.** Sibling packages should pin a commit or tag
and pull fixtures from here instead of vendoring copies.

No Human Connectome Project (HCP) data, no other restricted/participant data,
and no Jang panic-EMA files are stored here.

## Contents

| Path | n × p | License | CI? |
|------|-------|---------|-----|
| [`datasets/boston/boston_data_raw.csv`](datasets/boston/boston_data_raw.csv) | 641 × 7 | CC-BY 4.0 | yes |
| [`datasets/boston/boston_data_lagged_within_subject.csv`](datasets/boston/boston_data_lagged_within_subject.csv) | 621 × 14 | CC-BY 4.0 | yes |
| [`datasets/boston/boston_sub132_allsurveys_10v.csv`](datasets/boston/boston_sub132_allsurveys_10v.csv) | 142 × 10 | CC-BY 4.0 | yes |
| [`datasets/myconnectome/myconnectome_sub066_518x50.csv`](datasets/myconnectome/myconnectome_sub066_518x50.csv) | 518 × 50 | CC0 / PDDL | yes |
| [`datasets/myconnectome/myconnectome_sub066_518x379.csv`](datasets/myconnectome/myconnectome_sub066_518x379.csv) | 518 × 379 | CC0 / PDDL | yes |
| [`datasets/myconnectome/large/myconnectome_sub066_518x630.csv`](datasets/myconnectome/large/myconnectome_sub066_518x630.csv) | 518 × 630 | CC0 / PDDL | **no** (T < p) |

The 630-ROI matrix is rank-deficient and lives outside the default CI set.
Use the 379-ROI subset as the large full-rank case. Shapes, selection rules,
and checksums: [DATASETS.md](DATASETS.md). Attributions: [NOTICE](NOTICE).

The CI path list is [`datasets/CI_FIXTURES.txt`](datasets/CI_FIXTURES.txt).
SHA256 for every committed dataset file is [`SHA256SUMS`](SHA256SUMS).

## How consumers should fetch fixtures

Pin a **commit SHA or tag**, not `main`. After fetching, check hashes:

```bash
sha256sum -c SHA256SUMS
```

or, for the default CI set only, verify the paths in `datasets/CI_FIXTURES.txt`
against `SHA256SUMS`.

### Option A — git submodule (recommended)

```bash
git submodule add git@github.com:kelvinlim/causal-open-data.git third_party/causal-open-data
git -C third_party/causal-open-data checkout <tag-or-commit>
git -C third_party/causal-open-data show -s --format=%H HEAD   # record the pin
```

Read files from `third_party/causal-open-data/datasets/...`. Cite Boston as
CC-BY 4.0 (see NOTICE). MyConnectome is CC0 / PDDL.

### Option B — sparse clone of a pinned commit

```bash
git clone --filter=blob:none --sparse git@github.com:kelvinlim/causal-open-data.git
cd causal-open-data
git sparse-checkout set datasets scripts
git checkout <tag-or-commit>
sha256sum -c SHA256SUMS
```

### Option C — download helper (token required)

```bash
export GITHUB_TOKEN=...   # contents:read on kelvinlim/causal-open-data
python3 scripts/fetch_fixtures.py --ref <tag-or-commit> --dest ./fixtures
# add --all to include the non-CI 630-ROI matrix
```

The helper pulls `SHA256SUMS` from the pinned ref, downloads each path, and
refuses to write a file whose SHA256 does not match.

### Option D — GitHub Contents API

Private raw GitHub URLs need auth. Use the Contents API (or git blobs above
1 MiB) with `Authorization: Bearer $GITHUB_TOKEN` and `ref=<commit>`. Do not
depend on unauthenticated `raw.githubusercontent.com` for this repo.

tetrad-rs, ezcausal, and opencausal should switch to one of the options above
and stop vendoring Boston / MyConnectome copies.

## Regenerate derivatives from upstream

Raw OSF / Stanford downloads stay in `.cache/` (gitignored). Do not vendor
the multi-GB original dumps.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/prep_boston.py
python3 scripts/prep_myconnectome.py
python3 scripts/write_checksums.py
python3 scripts/verify_fixtures.py
```

`prep_boston.py` reconstructs the classic 641 × 7 fixture **byte-for-byte**
from OSF file `duwv4`. `prep_myconnectome.py` rebuilds the 50-ROI and 379-ROI
subsets from session `sub066` timeseries plus parcel labels.

## License

Scripts and packaging: MIT (see [LICENSE](LICENSE)).

Redistributed data keep their upstream licenses:

- Boston College COVID-19 Sleep and Well-Being: **CC-BY 4.0**
- MyConnectome parcellated timeseries: **CC0 / ODC-PDDL 1.0**

See [NOTICE](NOTICE).
