# Frozen stack inputs for 2019–2025

This package extends the exact M/N 127-column view to the original supplied future player universes. It supplies predictors only. The model and calendar broker must select earlier training cohorts and labels separately.

- `package/features_pre2019.csv`: 1,428 original rows, 2000–2018, with pid, draft_year, and 127 predictors.
- `package/features_YEAR.csv`: 2019–2025 supplied cohort rows in their original order.
- `package/metadata_YEAR.csv`: pid, draft_year, was_drafted, kept outside model predictor matrices.
- `package/manifest.json`: exact column order, first 44-column mapping, source/output hashes, coverage, and limitations.
- `verification.json`: output-boundary checks, exact future 44-column preservation, date checks, parser failure fixtures, and pinned source-code/support hashes.

The original 44 inputs and remaining 48 F50 inputs use previously collected and pinned values. The 15 player-game and 20 team-context predictors use 14 newly fetched historical source archives, 2019–2025. Source code extracts only the original parser/arithmetic functions, extending the upper year guard from 2018 to 2025. Invalid source groups remain missing with explicit reasons. No feature coefficients, means, or model weights were fitted here.

Twelve original M training/inference predictor matrices across 2012–2014 replay exactly. A same-source-season 2018 control replay reproduces all 35 game/team values and missing cells for 75 players.

No NBA outcome labels, benchmark answers, model scores, or actual draft-order columns were read. Original raw source files stay outside the package/model-worker boundary. Annual source column 45 is excluded by the explicit parser projection.

Limitations remain: annual and game snapshots were retrieved retrospectively, publication revisions and schedule completeness are unverified, original population construction is unverified, and non-college coverage is sparse. This is a diagnostic input package requiring root review, not a certification of historical source vintages.

All files are stored on the GPU server under /home/ubuntu/nba/handoff/r9stacktest_features. Local disk was full, so no bulk duplicate files were written to the Mac. Source archives and predictor CSVs can be preserved through an explicit public allowlist; never publish model-worker bundles with labels.
