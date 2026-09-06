# R8w: 50 statistics conditional on dated consensus

This registered diagnostic rescreens all 50 F50 statistics on the fixed 41-column raw-college backbone plus the four original verified pre-draft consensus fields. R8r screened them without consensus. This study introduces no combinations, automatic promotion, confirmation scoring, or 2019–2026 inputs/outcomes.

## Design

Development folds remain 2012, 2013, 2014. For fold Y, training draft cohorts are 2007 through Y−2; outcome seasons end by Y−1. The original calendar-cutoff WAR/rank target, full drafted-class denominator, CPU feature selector, and TabICL32 constructor are unchanged. There are 251/329/403 training rows and 55/50/53 query rows. The selector receives only the 41 source fields, retains all 41 in its frozen training-only ordering, and the four real consensus columns are appended unchanged. No legacy bio, medical, scouting, consensus, engineering, coverage weighting or shrinkage enters the predictors. IDs, actual picks and row positions are never predictors.

The queue has 603 tasks: three baseline fits plus 50 fields × (real + three controls) × three model seeds. Seeds are 0, 101, 202; controls use prespecified 9317, 18739, 28657. All 50 fields pass the training-only threshold of at least five observed values and two distinct values in every fold, so none is omitted. Every single/control appends the same `slot_041`, with exactly identical baseline columns and width. A control shuffles one field within draft cohort and observed/missing pattern, separately in training and query rows; the SHA256-derived stream also keys on the field. Player masks and observed-value multisets remain exact. Constant and singleton strata cannot move; `preflight.json` reports effective changes and coverage.

Training and query presentation is canonical SHA256(pid) order. Identity is excluded from model inputs. Predictions for exact identical full input vectors receive their common arithmetic mean; NaNs and signed zero are handled consistently. Distinct vectors are never quantized. Raw and canonical predictions, row-vector hashes and duplicate groups remain auditable.

## Source and replay safeguards

All 16 R8u data files are copied byte-for-byte. The additional 50-column table, dictionary, metadata and provenance are copied from R8r with verified hashes. The physically mounted lineage is restricted to 661 pre-2019 traced player histories; it records source file/row, source player ID, season and team. The independent `work/fifty_audit` replay found zero duplicated (season, team, source-player-ID) rows and reproduced all original focal/history selections without changing features. Retrospective Torvik source vintage and original prospect-universe construction remain limitations; source-season checks alone do not certify historical publication dates.

The sandbox contains only this pre-2019 bundle, read-only code/runtime/checkpoint, and writable results. Network and outside paths, including the answer vault, are inaccessible. CPU preparation must match completed R8u input, column, identity, label and consensus hashes exactly. The unchanged copied R8u worker is rerun on the server for full 45-column matrix equality; only its CPU preparation runs. Before any feature result is interpreted, all three TabICL32 baseline seeds must exactly replay completed R8u raw/canonical predictions and fold/mean scores, also previously replayed by R8v. Constructor mismatch fails closed; no fallback or weight reuse.

## Reading the result

The primary diagnostic is real-minus-mean-shuffle paired by field, model seed and fold. Separately report the real score minus the 45-column baseline: the 46-column real/control arms differ in width from baseline, so a positive matched advantage alone is not a baseline improvement. The metric is mean fold Spearman multiplied by 100 for display, not classification accuracy. Fifty hypotheses, three shuffle seeds and three model seeds are exploratory dependent comparisons, not significance tests. This screen cannot establish complementarity between two added statistics or justify promotion by itself.

## Validation and bounded execution

Local preflight exercises 900 deterministic shuffle/order cases, all 603 fold/design combinations, baseline replay gating, exact ties, and eight deliberate audit corruptions. `prototype_manifest.json` freezes plan, runtime, preparation, tests, data manifest and original reference code before the first model. Server `--prepare-only` saves its exact replay checks before launch. The queue uses four workers, a 140 GiB memory cap, 22 CPU-equivalents, and a two-hour runtime cap. Results are diagnostic and are not published by this worker.
