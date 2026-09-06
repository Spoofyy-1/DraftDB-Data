# Verified official combine reconstruction

This dataset rebuilds measurements and drills from cached official NBA combine
responses only. It contains **37 `vcmb_` features**: 14 measurements/athletic tests,
BMI, wingspan minus height, and seven shooting-drill groups with made shots,
attempts, and success fraction. No legacy bio columns were modified.

All 26 cached `combine_YYYY.json` files for 2000–2025 passed both checks:
`parameters.SeasonYear == YYYY-(YY+1)` and **every** row's `SEASON == YYYY`.
Each source filename, URL, row count, and SHA-256 is recorded in the manifest.
A bad parameter or a single wrong-year row rejects the whole source file.

Only a player's same draft-year combine file is eligible. This is stricter than
the allowed source-year ≤ draft-year rule and prevents accidental carry-forward
when a cohort's source is absent. The 2026 cache is absent, so every 2026 feature
remains NaN.

Identity joins prefer a unique official NBA player ID. Otherwise, a normalized
exact name must be unique within the same cohort, and any conflicting known IDs
cause rejection. Nine conflicting-ID name matches were excluded. Future identity
rows do not alter earlier-cohort match decisions.

| Input cohort | Original rows retained | Rows with combine data | BMI observed |
| --- | --- | --- | --- |
| Train 2000–2018 | 1,458 | 763 | 760 |
| 2019 | 137 | 61 | 60 |
| 2020 | 112 | 43 | 43 |
| 2021 | 233 | 54 | 54 |
| 2022 | 97 | 49 | 49 |
| 2023 | 101 | 51 | 51 |
| 2024 | 114 | 66 | 66 |
| 2025 | 106 | 57 | 57 |
| 2026 | 61 | 0 | 0 |

Height without shoes, height with shoes, weight, wingspan, and standing reach are
separate observed measurements. BMI requires actual same-row combine weight and
height **without shoes**; it never substitutes shoe height, a current NBA bio,
another year's record, a cohort average, or a medical/research fill. Raw missing
values stay missing. No age is derived or imported.

Shooting drills are parsed from official `made-attempted` strings. A grouped drill
is populated only when every expected station is present and valid. Zero attempts
produce a missing success fraction, not 0% shooting. Rates use fractions from
zero to one; the dictionary specifies units and constituent source fields.

## Files

- `build.py`: offline builder; it does not import the old collector or call any
  network endpoint.
- `data/train_inputs.csv` and `data/2019_inputs.csv` through
  `data/2026_inputs.csv`: PID/draft-year sidecars preserving original input order.
- `data/feature_dictionary.json`: all columns, units, transforms, and source fields.
- `data/row_provenance.csv`: PID, cohort, source file/row, and match method.
- `data/manifest.json`: source hashes, input pool hashes, coverage and policy.
- `data/leakage_checks.json`: completed boundary checks.
- `PUBLIC_ALLOWLIST.json`: explicit files suitable for the research data repo.

The training CSV is **byte-identical after removing all post-2018 source files**,
SHA-256 `27f777fcec6c9eb66fa51c22248f3412d83c15010809bd76e550f5849b1cbc4b`.
Checks also passed for wrong request years, individual wrong-year rows, missing
height/BMI, partial shooting stations, zero attempts, future identity additions,
conflicting IDs, missing 2026 data, and retained inference pools.

The input pools were read using only PID and draft year. No WAR values, NBA career
statistics, or source biographies were used. There was no training or scoring.

Join these sidecars by `(pid, draft_year)` into the corrected baseline. Keep them
under their own `vcmb_` names, and do not restore unsafe inherited bio descendants
through a blanket rename or fill operation. Model selection and imputation, if
used by a model later, must occur within its permitted training fold.
