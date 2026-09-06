# R8r: all 50 F50 statistics on the college source-only backbone

This is a new **603-task** development screen: 50 features × (one real arm +
three shuffled controls) × three model seeds, plus three no-extra baseline runs.
Every feature is included because it passes registered training-value eligibility;
none was chosen using prior R8i/R8j scores. The earlier screens used an inherited
baseline with unresolved source provenance.

The baseline is exactly R8n `dated_raw_college_source_control`: 41 allowlisted
`ctx_base_`/`ctx_skill_` values excluding age and height. The local data bundle
physically omits every legacy biometric, medical, consensus and derived legacy
feature. The four metadata columns only define the fixed historical cohorts and
scoring benchmark; they never enter model inputs. Source-only preparation bypasses
all legacy engineering, shrinkage, prior fitting and coverage calculations.

Per fold, a CPU XGBoost selector fits only those 41 baseline columns and dated
training labels, then retains all 41 in its fixed importance order. That ordered
baseline and both matrices stay identical across every feature, control and model
seed. No F50 value enters baseline preprocessing or selection. The predictor is
unchanged TabICL32/Top60/M400; no weight-reuse helper is imported or adopted.

Each F50 statistic is appended using **the same `slot_0` name**, for both its real
and shuffled values. Controls independently permute observed values within each
draft cohort and train/validation role, using stable pid order and prespecified
permutation seeds 9317, 18739 and 28657. They preserve every missingness position
and within-cohort value distribution. Distribution hashes canonically sort float
hex values so shuffled signed zeros cannot cause false mismatch alarms; model
values are never changed. Model seeds remain 0, 101 and 202. Both
baseline matrices, slot masks, marginal distributions, source eligibility and
actual control value hashes are audited. No-extra baseline differences are
context only because adding a slot changes model shape.

Eligibility requires at least five observed and two unique training values, with
no validation-coverage or label criterion. A wholly untestable feature is excluded
before scoring if no fold passes those thresholds with any within-cohort training
variation. All 50 currently pass, so no task was omitted. In any individual fold
where a feature fails the coverage/uniqueness rule, every arm omits that slot.
Immovable columns and actual changed values are recorded to expose weak controls.

Development folds stay 2012, 2013 and 2014. Class Y uses NBA label seasons ending
at most Y−1 and training draft classes at most Y−2, preserving the existing
conservative cohort exclusion. The original ranking target and development
scoring horizons are unchanged. No 2019–2026 input/answer file is opened or copied
by preparation, and no confirmation or test score can drive this study.

The summary reports each feature's paired real-minus-mean-control difference
across the same model seed/fold, plus fold, seed and individual-shuffle differences.
Fifty comparisons remain exploratory; model seeds are not independent datasets.
No p-values, automatic promotion or combinations are registered. All completed
single-feature results must be reviewed before a separate combination protocol is
written. A better model score does not independently certify provenance.

## Source lineage and remaining limits

The original F50 builder uses explicit raw college statistical indices, excluding
NBA pick column 45. History and teammates are restricted to the focal pre-draft
season; shooting priors are explicit constants rather than fitted future values.
The stored source values are checked against the pre-2019 F50 package and remain
unchanged from R8i/R8j. The sandbox retains pre-2019 source/hash/history provenance.

The parent's separate audit in `work/fifty_audit/lineage_audit.json` and
`source_row_lineage.json` traces focal, history and roster rows with exact source
player IDs, teams, filenames, row indices and permitted-value hashes. It reproduced
all 1,565 existing source selections and found no duplicate (season, team, player
ID) rows among 90,739 raw records or in traced team groups. These are source
lineage checks, not a new proof of identity correctness or historical publication
vintage. Normalized-name identity links still deserve collision review. Historical
Torvik files were retrieved retrospectively, and the inherited prospect universe
retains its known construction limitations. Component consistency/domain checks
for nonlinear ratios are not newly added in this rescreen.

## Reproduction and launch handoff

`prepare_data.py` writes the trimmed data bundle, eligibility report in `plan.json`
and registration. `worker.py` exposes `run_variant(id, seed, variant_override=None)`
and `summarize_matched(candidates)` for the parent-owned runner. Importing it does
not prepare models or use the GPU.

`preflight.py` validates source/calendar joins, training-only thresholds, exact
cohort shuffles, paired aggregation, incomplete-result handling and tamper
rejection. It also compares both baseline matrices and training labels to R8n
using a deliberately artificial fixed-order selector and traps all legacy
transformation calls. Fixture scores are never written as experiment results.
`preflight.json` and `prototype_manifest.json` retain validation/file hashes.

Local XGBoost is unavailable, so the real CPU selector must be replayed on the
server against R8n source-only audits before launch; the local selector fixture
is a code-path check, not a substitute. Explicit `.stack().dropna()` handles pandas
version differences. The summary accepts unchanged `config.id` or the runner's
exact `_seedN` suffix while checking every other registered field. No GPU job,
remote launch, newer-fold substitution or held-out scoring is performed here.
