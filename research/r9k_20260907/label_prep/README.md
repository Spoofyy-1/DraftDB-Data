# R9K private training-label preparation

Six CPU-only exports are ready at `/home/ubuntu/nba/handoff/r9k_label_exports/`. No source acquisition, model fitting, scoring, query-truth extraction, or production-source changes occurred. SSH was used only to run the approved preparation and transfer code/aggregate verification.

| Outer year | Exact H control rows | Discounted observed-prefix rows |
| --- | ---: | ---: |
| 2012 | 423 | 236 |
| 2013 | 470 | 315 |
| 2014 | 514 | 389 |

The exact control is H's frozen `s2000_gap1_drafted_h2`: its ordered PID, draft-year, raw cumulative WAR, and Gaussian-target arrays are preserved exactly. Every used H fact was independently reverified through the cutoff-first calendar broker. All 846/940/1,028 control facts agree; mismatches would stop preparation without changing H or creating exports.

The second policy uses the exact original H 1,428-member universe, draft cohorts at least 2007 and strictly earlier than the outer year. It requires a verified contiguous observed ordinal prefix `1..m`, with `1<=m<=5`, and stops at a missing ordinal. Raw `label_value` is the sum of `.85**(ordinal-1)*WAR`. Each value is clipped to `[-40,40]`, then converted to an average-tied Gaussian rank within admitted training cohorts only. Unknown labels never become zero; explicitly observed zero is retained. Both policies require at least 40 training rows and at least five rows in each admitted cohort.

Source seasons are filtered to `season_end<=outer_year-1` before source-identity matching. Earlier identities are constrained to the exact H population before project-name uniqueness checks. The pinned broker compares only source-dated eligible ordinal cells from the pre-2019 raw training snapshot. Future values, names, source identities, and future membership additions cannot influence earlier outputs.

## Export contract

For each `{policy}/{outer_year}/`:

- `training.npz`: exactly `pid`, `draft_year`, `label_value`, `y`, `prefix_length`; no `X` and no query truth. Numeric target arrays are float64; prefix length is integer metadata, never a predictor.
- `manifest.json`: cutoff, cohort and prefix counts, maximum actual label season, source pins, fact hash, ordered PID hash, and H-compatible numeric array hashes. It explicitly records finite observed labels, no missing-label zero filling, and query-PID disjointness.
- `eligible_label_facts.csv`: private data-authority evidence. **Do not mount or copy this file, the raw sources, or the entire export root into a model worker.**

Policy directories are `h_s2000_gap1_drafted_h2` and `prefix_s2007_gap1_all_d085`. Years are 2012, 2013, and 2014. The root manifest pins all six NPZs and per-year manifests. Root/scorer authority retains the unchanged H query truth and masks.

A model builder may combine the appropriate training export with its approved predictors. For every inner split, recompute clipping and cohort Gaussian ranking from that inner training subset's `label_value` and `draft_year`; do not reuse full-outer ranks. Recomputing on the complete outer training arrays must match exported `y` exactly. H-compatible hashes use compact JSON shape, NaN-mask bytes, and zero-normalized float64 bytes; ordered PID hashes use compact JSON SHA256.

Eight adversarial tests passed both locally and on the server: future-value and identity/membership perturbations, eligible mismatch rejection, ordinal gaps, known zero, actual season dates, deterministic ordering, duplicate rejection, clipping/ties, and admission guards. A separate reopen verifier reproduced every raw label value from the private facts and every target using SciPy `rankdata`, rechecked hashes and source immutability, and verified private directory/file modes700/600.

The observed-prefix objective has variable follow-up length. The fixed inherited universe remains retrospectively selected and incomplete, and observed-label admission can select survivors. These are disclosed diagnostic policies, not a certified complete-population benchmark or an accuracy claim. No publication or model promotion was performed.
