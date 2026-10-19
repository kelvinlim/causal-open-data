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
