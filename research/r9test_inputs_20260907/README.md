# Frozen H input candidates, 2019–2025

Seven CSVs contain the exact44 sorted H model columns plus PID and draft year. They preserve all900 original input rows. The original1428 pre-2019 H feature rows are not replaced. No model, label export or test scoring is performed here.

`metadata_YEAR.csv` holds only PID, year and the existing server input-file drafted flag. It is separate from predictors. Model/scorer owners select the registered query population and enforce training eligibility and label cutoffs.

|Year|Full rows|College source|Verified mock|Drafted metadata|All44 missing|
|---|---:|---:|---:|---:|---:|
|2019|137|112|51|58|20|
|2020|112|84|54|58|19|
|2021|233|199|46|56|25|
|2022|97|76|48|52|14|
|2023|101|77|48|56|14|
|2024|114|85|49|55|19|
|2025|106|87|47|57|9|

Each feature is documented in `field_contracts.json`; per-column missingness, source hashes and matrix/order hashes are in `manifest.json`. Blank values remain NaN. Source-unmatched players, unlisted mock players and one-publisher disagreement remain missing. No name guessing, rank imputation, current biographies or actual draft order enters the feature matrix.

The college40-field portion uses the same38 context definitions and2 selected F50 definitions as H. All3020 original selected F50 cache values replay exactly. The old38-context check covers25,118 cells, with max8.9e-16 numeric difference against CSV round-trip values; it does not authorize rewriting old H matrices. New finite exports use exact FP64 round-trip strings; read with `float_precision="round_trip"`. All seven resulting matrix hashes reproduce exactly.

The `work/fifty_audit/fifty_test_*` files are negative cutoff-2018 fixtures and must not be used as future-cohort caches. Reconstruction instead pins the original work/fifty source manifest and existing exact source-row lineage. No future2026 source is loaded. Earlier exported feature values survive complete removal of later sources at three cutoff years.

Same pre-draft cohort inputs can later serve expanding training for2019–2023 without refilling or reconstructing them with later player information. The independent label/recipe builder must prohibit the current query cohort in training and restrict outcomes to completed seasons allowed by that evaluation year.

## Limits and admission

Package-wide `model_eligible=false` means parent review is still required. The main missing contract is a strict original-publication-date guarantee for annual college tables: they were retrieved retrospectively, and their source seasons are known, but game-level calendar evidence and original vintage are absent here. These numeric candidates support only an explicitly admitted retrospective diagnostic. The raw annual count/per-game subset mismatch is preserved to match the frozen recipe, not silently repaired. No later NBA-calibrated impact metrics are imported.

The archived mock ranks have stronger dated availability proof, but only one publisher is available for2021–2025, and2019–2020 include stale and partial serious top15 forecasts. Source count/range reflects this changing coverage. Original pool construction and inherited identity limitations remain documented. Six focused tests cover row/order/metadata/schema, future/stale/identity rejection, future-source removal, mock-date/duplicate rejection, missingness and raw hash tampering.

Only explicitly allowlisted files are public candidates. Raw responses, source-player identities and detailed college row pointers stay private. No source package was modified.
