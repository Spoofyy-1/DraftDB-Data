# Paired H44 and broad174 panels

Both panels preserve the same1428original PIDs, draft years, drafted metadata and row order. `pairedpanel44.csv` contains44 predictors; `panel174.csv` contains those unchanged44 followed by130 sorted added source fields. Metadata columns are not predictors. No source population was expanded.

The shared H44 block passes all66registered H training/query input-matrix hashes exactly. It comes from a pinned input-only server export; reconstructing through earlier intermediateCSV files changed floating-point bits, so those were rejected as substitutes. Both saved panels use17-digit numeric strings and must be parsed with `float_precision="round_trip"`.

|Added family|Columns|Rows covered among1428|
|---|---:|---:|
|F50|48|661|
|combine|37|751|
|dated_bio|10|558|
|player_game|15|660|
|team_context|20|614|

The discarded `ctx_base_fta`, `ctx_base_ftm` and `ctx_base_mid_made` columns stay excluded. Existing H consensus cells stay exactly asfrozen; later verified ranks do not fill their missingness. Synergy/text, international, recruiting, medical and unverifiedlineup/impact columns are absent.

Each added block is left-joined one-to-one byPID/year after its source/date/identity gates; duplicate orconflicting identity keys reject. Missing remainsNaN. Six tests check exactHreplay, added source values/masks, source-orderinvariance, duplicate/cohortconflicts, game/bio temporal/quarantineguards, and output hashes/roundtrip/forbidden schema.

Source admission is diagnostic: college event seasons/dates and fixed arithmetic have documented checks, but retrospective publicationvintage, complete schedule/DNP definitions and originalprospect-pool selection remainunproved. Official combine and archivedlisted bios keep their separate measurement conventions. `model_eligible=false` remains the package-wideflag.

`panel_manifest.json` records exactsource/output/matrixhashes, columns and family/cohortcoverage. `panel_contracts.json` records joins and source dependencies. Actual training-column eligibility, imputation/scaling, OOF stacking and labelseasoncutoffs belong to the separately registered runner; no model or labels were used here.
