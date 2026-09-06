# Independent bounded review before launch

**Disposition: no new structural blocker for this registered diagnostic study.**
Launch remains conditional on the parent-owned server preflight: apply/verify
the pandas-3 compatibility fix, confirm the actual CPU selector reproduces
R8q's source-only baseline, verify TabICL accepts the registered constructor
configuration, and freeze the resulting code/data hashes. This review did not
run a model, open outcome values, calculate any score, or modify the worker,
plan, data, or runner.

## Calendar, identity and feature boundaries

`worker.py:193–203` builds training classes 2007 through Y−2, then maps only
label records with actual `season_end <= Y−1` onto those training PIDs. The
validation class Y cannot enter fitting. Only the 41 explicitly registered
college source columns enter the base matrices; legacy engineering, priors,
shrinkage, current biography descendants and actual picks do not enter the
predictor. The fixed CPU selector orders those same 41 columns using training
labels and seed 11. It neither selects against validation coverage nor admits
source-family columns into the selector.

An independent metadata-only check read `pid`, `draft_year`, `ordinal`, and
`season_end`, excluding WAR. Across 4,148 label metadata rows, it found zero
PID/cohort mismatches, duplicate PID/season pairs, ordinal gaps, or calendar
ordering violations. There are no train/validation PID overlaps. Fold sizes
are 251/55, 329/50 and 403/53; maximum eligible training season ends are
2011, 2012 and 2013 respectively. This checks calendar integrity against the
frozen metadata; it does not independently re-source every NBA participation
date.

The source columns are eligible only from each fold's training data: at least
five observations and two distinct values. Registration and runtime agree on
15 combine and four consensus columns. Validation values are used only to
form corresponding design/control matrices after column eligibility is fixed.
The other 22 combine columns were ineligible here, not demonstrated to be
predictively harmful.

All data-file hashes in `data/manifest.json` matched at review time. The legacy
kernel is byte-identical to R8q, and the 41 source-baseline column names match
R8q's `source_college` registration. Actual ordered columns, transformed labels
and base-matrix hashes still need the existing server CPU preflight because
the selector was not executed in this review.

## Controls and matched comparisons

`_vector_shuffle` uses whole family vectors within the same draft cohort and
the exact selected-column NaN pattern. PID-sorted strata and seeds derived
from family, permutation seed, role, cohort and mask make the controls
independent between families and identical across solo/joint arms and model
seeds. Each player's mask and the entire vector multiset are checked, retaining
within-family algebra and covariance. Independent synthetic checks confirmed
cohort confinement, a derived-column algebraic relationship and invariance to
input row order. No outcome data was used in those checks.

`_design` fixes the same baseline matrix in every arm and appends slots in
combine-then-consensus order. Matched real/permuted comparisons check identical
column lists, feature counts, nonconstant training-column counts, masks,
cohort/PID strata and family vector multisets. The summary also checks one
matrix hash per family/permutation/fold/role across solo and joint scopes and
across fit seeds. Thus RP's combine values are RR's combine values, PR's
consensus values are RR's consensus values, and the same P stream is reused in
PP and the relevant single-family control.

The 57-task registration is internally consistent: three baseline tasks,
12 for each solo family, and 30 joint tasks. `RR−RP` correctly measures
consensus conditional on real combine; `RR−PR` measures combine conditional on
real consensus. `RR−RP−PR+PP` is the registered factorial interaction contrast.
The summary withholds a family/factorial comparison until its registered
variants and model seeds are all present. It does not use the feature-count
change from baseline to joint as the matched complementarity estimate.

## Required server compatibility checks

The parent identified a pandas-3 difference in the two finite-value checks:
`.stack().to_numpy()` can retain NaNs. The intended correction is
`.stack().dropna().to_numpy()` in `_load_inputs` and `_source_values`, while
preserving the source matrices and masks themselves. This is a validation
compatibility repair, not imputation or a change to the experiment. Re-run
preflight and refresh worker/prototype hashes after the repair; do not mix
results produced by different worker hashes.

The inherited kernel's TabICL constructor has a broad `TypeError` fallback to
`TabICLRegressor(device="cuda")`. If the installed API rejects any supplied
argument, that fallback would silently discard the registered seed,
`n_estimators=32`, and other options. Verify the installed constructor accepts
the effective `cfg_of('tabicl', ...)` parameters and that the effective
`random_state` is 0/101/202 for the three fit seeds. Existing successful R8q
compatibility may provide evidence, but a silent fallback must not count as a
registered run. Fail closed or explicitly reject any such run.

## Interpretation and inherited limits

`legacy_kernel.py:29–39` fills missing eligible season cells with zero before
forming a within-cohort rank. There are 15/14/14 training rows with no eligible
label metadata in the three folds. Every validation row has some horizon label
metadata, so the validation zero-fill fallback is not triggered by a wholly
unmatched PID in this bundle. The zero treatment is inherited from R8q and
does not import future values, but it is an observed-prefix target convention:
missing evidence alone is not a certified zero career outcome. Censoring and
identity completeness must be resolved before a clean predictive claim.

The original 1,428-row universe and its 55/50/53 drafted validation subsets
remain incomplete historical populations. This study does not incorporate the
new 60-player source-first registries or resolve retrospective college/combine
release-vintage uncertainty. Those limitations remain explicit in the plan
and README and are not repaired by a good control contrast.

Only three development classes, three fit seeds, and three permutation seeds
are used. Training cohorts overlap between folds; repeated contrasts share RR
and validation players. The 27 factorial contrast rows are not 27 independent
datasets. Exact-mask strata leave some rows immovable, and the current
two-publisher consensus count is largely fixed by those masks. These controls
test values beyond the preserved coverage structure. They do not establish an
independent source-count effect, a p-value, a clean held-out score, or evidence
that a 60% target has been reached. Spearman correlation is the metric, not
the fraction of correctly ordered player pairs.

One nonblocking hardening opportunity remains: `summarize_matched` requires
all submitted study hashes to agree, but does not independently recompute the
expected current bundle hash before accepting an internally consistent result
set. A fresh isolated results directory plus frozen runner hashes addresses
the planned launch; explicit expected-study-hash binding would make later
resumption/import safer.

No 2019–2026 outcomes or results were inspected. The review used code,
registration/provenance, file hashes, label identity/calendar metadata, and
synthetic non-model control checks only.
