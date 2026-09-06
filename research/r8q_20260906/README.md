# R8q: verified combine features with matched controls

This registers **78 pre-2019 development trials**: two fixed R8n backbones ×
(one baseline + three active families × four arms) × three model seeds. It does not
score a confirmation set or a 2019–2026 test, promote a model, or certify the
inherited evaluation universe as clean.

The backbones are the exact R8n `dated_raw_college_source_control` (41 raw college
base/skill features, excluding age and height) and
`quarantine_bio_med_consensus_college_derived` (Top60 selected from the conservative
legacy quarantine). The source-only branch bypasses every legacy prior, coverage,
shrinkage and engineered feature operation. The conservative branch clears
quarantined raw values before preprocessing; continuous bio/consensus descendants
must be completely missing if selected. Neither branch receives legacy bio,
medical or consensus values through the added combine block.

The added data comes only from `work/verified_combine/data/train_inputs.csv`:
10 anthropometry variables, six athletic tests, 21 shooting-drill fields, and
the ordered union of all 37. Official event season must equal the prospect's
draft year. The sandbox bundle contains 1,428 historical players, 751 with some
combine data, and 11,597 observed combine values. Source rows/hashes and calendar
checks are retained. No inference input file is opened or copied by preparation.

Training-only preflight found 10 eligible anthropometry columns, five athletic
columns and **zero eligible shooting columns in every development fold**. Before
any model scoring, the 24 shooting-arm tasks were removed from registration and
marked untestable. All 21 drill fields remain stored for a separately registered
later study; the fold calendar was not changed. The active all-family arm contains
the same 15 eligible measurements/tests. The omitted sixth athletic field is
modified lane agility, which also fails these training-only eligibility rules.

For every backbone and 2012/2013/2014 fold, the XGBoost selector sees baseline
features and dated training labels only. Its Top60 (or all 41 source features,
in the selector's fixed order) is reused across every family, arm and model seed.
Added columns are retained only with at least five observed training values and
two unique training values. Validation coverage and outcomes cannot influence this
filter. A filtered-out feature is not resurrected in the union family.

Each family has one real arm and three independent per-column value-shuffled
arms with prespecified seeds 9317, 18739 and 28657. Values shuffle only within the
same draft cohort and train/validation role, in stable pid order. All arms use
the same base columns, slot names/order, exact missingness masks and per-column
cohort distributions. Model seeds are 0, 101 and 202. The model remains
TabICL32/Top60/M400, training window 2007, with the original rank target. Class Y
uses labels with season end at most Y−1 and training draft cohorts at most Y−2,
retaining the existing conservative cohort exclusion for comparability.

The summary pairs each model seed and fold's real score with the mean of three
shuffles, and reports fold, seed and individual-permutation differences. It
verifies both base matrices, cohort/label hashes, masks, source columns, actual
shuffle value hashes across model seeds, and whole-class denominators. Baseline
differences are context only because model dimensions differ. Incomplete family
comparisons are withheld. No significance threshold or automatic gate is applied.

Independent-column shuffles deliberately do **not** preserve BMI/drill algebra or
cross-feature covariance. A real-minus-shuffled gain measures usable family joint
structure as well as association with player outcomes and base features; it does
not identify unique causal information in individual fields. Three model seeds
are not three independent datasets. The six active backbone/family comparisons are
exploratory. The all-family arm does not establish complementarity relative to
single families with different model dimensions. Immovable columns and actual
changed values are recorded to expose ineffective shuffles.

## Files and validation

- `prepare_data.py`: reproduces the local data bundle and registration; no model execution.
- `worker.py`: exposes `run_variant(id, seed, variant_override=None)` and `summarize_matched(candidates)` for the parent-owned runner. Importing it does not train models.
- `plan.json`, `data/manifest.json`: registered variants, constants, source/file hashes and limitations.
- `preflight.py`: source/calendar joins, training-only feature thresholds, shuffle invariants, paired-summary fixtures and tamper rejection. It also replays both R8n preprocessing paths under an explicitly artificial fixed-order selector and traps any legacy transformation call in the source-only path. Fixture scores are never stored as experimental runs.
- `preflight.json`: validation results; `cpu_top60_selector_executed` and `gpu_model_executed` remain false locally.

Before launch, run the actual CPU selector preparation on the server for both
backbones and compare ordered base columns, training labels and both matrices
with the corresponding R8n baseline audits. Local XGBoost is unavailable, so the
fixed-order fixture checks code paths without substituting for that real replay.
The worker handles pandas stack-version differences with explicit `.dropna()`.
Sequential backbone reuse restores the legacy global namespace before prediction;
use one sequential task stream per worker process, as in the existing runner.
The summary accepts either unchanged `config.id` or the runner's exact `_seedN`
suffix, while requiring all remaining configuration fields to match registration.

No GPU job or remote launch is performed by these files. Source publication
vintages and the inherited prospect universe remain broader provenance limits.
