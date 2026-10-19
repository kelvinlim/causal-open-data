# causal-open-data

Openly licensed test and benchmark datasets for causal discovery, shared by
[tetrad-rs](https://github.com/kelvinlim/tetrad-rs),
[ezcausal](https://github.com/kelvinlim/ezcausal), and
[opencausal](https://github.com/kelvinlim/opencausal).

**No HCP or other restricted participant data.** Derivatives here are
regenerated from public sources by the prep scripts.

## Contents

| Path | n × p | License | Notes |
|------|-------|---------|-------|
| `boston/boston_data_raw.csv` | 641 × 7 | CC-BY 4.0 | 20-subject Full-survey subset of OSF gpxwa |
| `boston/boston_data_lagged_within_subject.csv` | 621 × 14 | CC-BY 4.0 | Within-subject lag (20 boundary rows dropped) |
| `boston/boston_sub132_allsurveys_10v.csv` | 142 × 10 | CC-BY 4.0 | Subject 132, sleep / social / drinks / stress |
| `boston/boston_fixture_row_provenance.csv` | 641 × 8 | CC-BY 4.0 | OSF `sub_id` / `ref_date` / `unique_id` per pooled row |
| `myconnectome/myconnectome_sub066_518x50.csv` | 518 × 50 | CC0 / PDDL | Session 066, network-balanced 50-ROI subset |
| `myconnectome/myconnectome_sub066_518x379.csv` | 518 × 379 | CC0 / PDDL | Session 066, full-rank 379-ROI subset |

Checksums: `MANIFEST.json`. Licenses and selection rules: `NOTICE`.

## Regenerate

```bash
python3 -m pip install pandas numpy
python3 scripts/prep_boston.py --write-raw
python3 scripts/prep_myconnectome.py --force-379
```

Downloads are cached under `.cache/` (gitignored). Boston reconstruction
is checked against `boston/boston_data_raw.csv` when that file exists.

## Consumers

tetrad-rs keeps a few small copies under `tests/data/` so CI does not
need this private repo, and fetches the 379-ROI table (and any missing
fixtures) with `scripts/data/fetch_open_data.py`.

## License

Scripts and packaging: MIT. Dataset licenses remain CC-BY 4.0 (Boston)
and CC0 / PDDL (MyConnectome). See `NOTICE`.
