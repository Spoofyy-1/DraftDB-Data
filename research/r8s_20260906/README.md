# R8s combine and consensus factorial diagnostics

This independent, frozen prototype tests whether verified mock ranks and verified combine measurements add complementary information to the R8n/R8q 41-column college source baseline. It has **57 registered tasks** and performs no model work on import. No R8q results were read to design the study. No 2019–2026 outcomes or inference pilot rows are included.

The data bundle retains the original 1,428 model identities. Baseline features are physically projected to the 41 allowed columns plus four scoring/membership fields, preserving their original numeric text. Labels, incumbent configuration and kernel are byte-identical to R8q. Original and projected hashes are recorded in `data/manifest.json`. The worker explicitly selects only the 41 `ctx_base_`/`ctx_skill_` baseline columns; it never calls the legacy feature engineering, priors, coverage transforms or shrinkage. `actual_pick` is used only for the comparison score after prediction. The original `was_drafted` validation membership is retained; prospect-universe completeness remains an unresolved limitation.

For validation class Y = 2012, 2013, 2014, training classes run from 2007 through Y−2 and labels include only NBA seasons ending by Y−1. Development evaluation uses the existing WAR definition with outcomes through 2018 and the inherited horizon. The CPU selector orders the same 41 baseline columns once per fold/process, using fixed seed 11. All baseline inputs, labels, membership and source selection are hashed and must match across arms and fit seeds.

Source column eligibility uses only training coverage: at least five observed values and two distinct values. Exactly **15 combine columns and four consensus columns** qualify in each fold. Source columns receive fixed ordered slots after the baseline. The other 22 registered combine fields are retained in provenance but are never appended in these folds; they are not failed predictive tests.

The consensus fields are mean mock rank, best mock rank, rank range and number of publishers. The range is missing with only one publisher. These facts come from 16 verified pre-draft archived primary mocks across 2007–2014, with 715 observations for 402 exact same-cohort identities. Of these, 381 identities join the fixed model dataset; 21 source-only identities are excluded. Some early snapshots are stale, including February 2009; this is a dated mock-rank pilot, not guaranteed final consensus. Each source capture is before midnight Eastern on the first draft date, and its mock update date is before the draft.

## Registered comparisons

Three fit seeds are fixed at 0, 101 and 202. Permutation seeds are 9317, 18739 and 28657.

| Scope | Configurations | Tasks |
| --- | --- | ---: |
| Baseline | College source baseline | 3 |
| Combine alone | Real plus three shuffled controls | 12 |
| Consensus alone | Real plus three shuffled controls | 12 |
| Joint | RR once, plus three replicates each of RP, PR, PP | 30 |

For each factor, R means real feature values and P means shuffled values. Whole family row vectors are permuted only within the same draft cohort **and exact selected-column missingness pattern**. Stable PID order and independent family seed streams give repeatable controls. The identical family stream is reused between the single-family and joint arms, across all fit seeds. This preserves every player's per-column missingness and all within-family row relationships, algebra and covariance. It avoids the incoherent derived combinations produced by independent column permutations.

Every matched comparison checks fixed input shapes, slot identity, base matrices, source masks and the complete multiset of family row vectors in every stratum. The audit reports how many observed rows can move and how many actually changed in each permutation. Singleton or constant-vector strata are immovable. With consensus, source count is already determined by the missingness stratum; the rank permutation therefore tests information beyond coverage/source count, not a separately randomized source-count effect.

| Validation year | Factor | Training observed / swappable | Validation observed / swappable |
| --- | --- | ---: | ---: |
| 2012 | Combine | 138 / 134 | 48 / 45 |
| 2012 | Consensus | 173 / 173 | 50 / 50 |
| 2013 | Combine | 180 / 175 | 42 / 41 |
| 2013 | Consensus | 227 / 227 | 43 / 43 |
| 2014 | Combine | 231 / 223 | 40 / 39 |
| 2014 | Consensus | 280 / 280 | 50 / 50 |

The summary reports paired real-minus-mean-control gains for each single family. Within the identical joint design, RR−RP measures consensus given real combine, RR−PR measures combine given real consensus, and RR−RP−PR+PP measures interaction. Three shuffle contrasts sharing RR are not independent datasets. Raw baseline-to-joint gains change feature count and are contextual, not the matched complementarity test. These exploratory development contrasts do not constitute significance tests, a clean held-out score, or automatic promotion.

## Validation and handoff

`python3 work/r8s/preflight.py` passes without preparing a model. It checks the source hashes and eligibility, 36 stable row-order permutations, 57 real-data design combinations, artificial paired/factorial aggregation fixtures, incomplete-study withholding, runner task-ID normalization and eight adversarial audit/config cases. Fixture scores are never saved in `results/`. All 54 public consensus package hashes remained unchanged.

The local environment has no XGBoost, so the actual fixed CPU selector and TabICL predictor were not executed. Before GPU launch, run `worker._prepared()` on the server and compare baseline column order, matrices, label hashes and membership against R8q's `source_college` baseline. Parent owns the runner and deployment. `run_variant(variant_id, fit_seed, variant_override=None)` and `summarize_matched(candidates)` expose the expected runner interface. Registration, data and controls must stay frozen after scoring begins.

Historical release vintages of the retrospective college/combine files are not yet fully certified, and the fixed prospect universe is incomplete. Every result remains explicitly diagnostic. The verified source package contains factual data and provenance; full source article bodies remain private and are not copied into this experiment.

Parent hardening before scoring: explicit NaN removal in finite-value checks for pandas 3; baseline physical projection; all six baseline hash fields replayed; direct registered TabICL construction and parameter equality checks with no silent fallback. Walter2007/2008 rank facts have dated sources but humorous editorial commentary; publisher quality remains a limitation.
