# R8p archived-report family diagnostics

All 39 registered tasks completed on the H100 with zero errors. The server CPU preflight exactly reproduced the R8n baseline column, player, label and matrix hashes before launch. `worker.py` exposes `run_variant(vid, vseed)` and `summarize_matched(candidates)` for the parent runner. `plan.json` registers 39 tasks: three baseline model seeds, plus numerical, text and joint families, each with a real arm and three shuffled arms at the same three model seeds.

The fixed baseline is R8n `quarantine_bio_med_consensus_college_derived`. Its input bytes, incumbent and kernel are copied unchanged. Excluded raw source values are cleared before engineering. The CPU selector chooses the base Top60 once per fold/process; hashes must match across every task. Source columns are appended afterward under globally fixed slot names. The remaining legacy inputs are uncertified, so all outputs and summaries are explicitly diagnostic.

Only numeric Synergy and fixed-lexicon text rows from the verified historical package are joined. Camp/agent fields and the NBA 2019–2026 pilot are excluded. The original 1,428-player model universe remains fixed; seven source-only identities are logged in the manifest and omitted. There are 2,390 joined source observations across 121 players.

Source columns survive only if that fold's training rows contain at least five observed values and two distinct values. Validation coverage is not an input to this rule. Whole-class validation denominators remain unchanged.

| Validation draft | Training cohort cutoff | Numeric columns | Numeric training / validation coverage | Text columns | Text training / validation coverage |
| --- | --- | --- | --- | --- | --- |
| 2012 | ≤2010 | 10 | 28 / 7 | 19 | 27 / 9 |
| 2013 | ≤2011 | 19 | 45 / 15 | 19 | 38 / 20 |
| 2014 | ≤2012 | 20 | 53 / 23 | 19 | 48 / 32 |

Each shuffle independently permutes only nonmissing values within each draft cohort. Exact player/column NaN masks, cohort distributions, unique counts and input dimensions match the real arm. Stable PID ordering makes shuffles invariant to physical row order. Numerical and text slots retain the same identities when used jointly. Source availability never becomes part of baseline coverage engineering.

Training labels are taken only from cohorts ≤Y−2 and NBA seasons ending ≤Y−1. Development scoring uses the inherited labels ending by 2018. Row-level source publication/capture checks, exact pid/year joins and source table/provenance equality run before preparation. The model receives audited feature matrices; draft picks remain scoring metadata.

The summary computes real minus the average of three controls for each model seed and fold, then averages the paired gains equally. A family's summary appears only after all twelve tasks complete. Baseline differences are context only because the dimensionality differs. The joint comparison measures a joint family effect; it is not a factorial interaction test or proof of complementarity. There is no automatic promotion.

`preflight.py` passed the real data/provenance checks, 1,272 permutation/order invariants, paired aggregation fixtures, incomplete-family withholding, and intentional mask-tamper rejection. See `preflight.json`. Python syntax and the R8n kernel hash also passed. The CPU Top60 selector and GPU predictor have not been executed locally; local Python lacks XGBoost. On the target environment, `worker._prepared()` runs CPU preparation only and can verify the base audit hashes before the parent launches the registered GPU tasks.

`prepare_data.py` rebuilds this isolated bundle from the current R8n inputs and verified source package. It does not edit those inputs or the published package. Do not rerun it after registering a live experiment; start a new registration if data or plan hashes change. The parent owns the sandbox mount, runner, deployment and GPU launch.

Runtime compatibility: the provenance comparison explicitly drops missing stacked entries because pandas versions differ in `stack()` defaults. This correction occurred before GPU execution; feature values, plan and model definition were unchanged.

Completed diagnostic means: baseline 38.92%; numerical family 37.43% versus matched controls 39.73%; text family 40.14% versus controls 38.73%; joint 38.40% versus controls 38.38%. Text has a positive mean effect but a negative 2012 fold; neither family is confirmed for promotion. No 2019+ test scoring occurred.
