# Prep and fetch scripts

Python 3.11+ with `pandas` and `numpy` (`pip install -r requirements.txt`).
`fetch_fixtures.py` uses only the standard library.

| Script | Purpose |
|--------|---------|
| `prep_boston.py` | Download OSF `duwv4` into `.cache/boston/` and write `datasets/boston/`. |
| `prep_myconnectome.py` | Download Stanford timeseries/labels into `.cache/myconnectome/` and write `datasets/myconnectome/` (630-ROI under `large/`). |
| `write_checksums.py` | Rewrite root `SHA256SUMS` for files under `datasets/`. |
| `verify_fixtures.py` | Shapes, classic subject set, SHA256, 379/630 ranks, no HCP/Jang filenames. |
| `fetch_fixtures.py` | Consumer helper: pin `--ref`, download CI set (or `--all`), check SHA256. |

Raw caches are gitignored. Do not commit OSF or OpenNeuro dumps.

```bash
python3 scripts/prep_boston.py
python3 scripts/prep_myconnectome.py          # add --skip-large to omit 630
python3 scripts/write_checksums.py
python3 scripts/verify_fixtures.py

# GITHUB_TOKEN / GH_TOKEN is optional (rate limits / private forks)
python3 scripts/fetch_fixtures.py --ref <commit> --dest ./fixtures
```
