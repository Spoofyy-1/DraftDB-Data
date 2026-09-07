# R9K: broader data and out-of-fold stacking

This registered development study compares XGBoost, TabICL and Ridge stacks on the same historical players using either 44 or 174 source-backed inputs. The research target is 55%+ full-pool Spearman order correlation, expressed as Spearman × 100. Registration does not establish an improvement or a benchmark result.

The original 50.6% model motivates two mechanisms restored here: a 25% TabICL / 75% Ridge blend for players with richer input coverage, and XGBoost corrections to TabICL predictions for players with thinner coverage. This is an architectural comparison, not an exact reproduction of the old data, labels or score.

Four prespecified architectures are compared:

- Equal weights across direct XGBoost, TabICL and Ridge predictions.
- The original coverage-dependent family weights with direct XGBoost.
- Those coverage weights with XGBoost trained on residual errors from out-of-fold TabICL predictions.
- Nonnegative weights learned from out-of-fold predictions of the three direct members. The residual member is excluded from this meta-model because it would require another level of nested cross-fitting.

All model outputs are ranked before blending. Three deterministic PID-hash inner splits ensure each training row's out-of-fold prediction comes from a model and feature selector that did not use its label. Each inner fit recomputes cohort Gaussian targets from its own training rows. Selectors and deterministic Ridge fits are shared across seeds, saving computation without sharing held-row labels. The registered models use TabICL32 with outlier threshold2, Ridge alpha300 and q25 XGBoost. The actual constructor and source/checkpoint hashes are recorded.

The two label policies are the exact prior H control (drafted cohorts2000+, two observed NBA seasons) and a2007+ observed-prefix target. The prefix target discounts observed WAR by0.85 per ordinal season, stopping at the first unknown ordinal and never using more than five seasons. It mixes available career lengths; it does not pretend that unobserved future seasons are zero. For each outer class2012,2013 or2014, every training cohort is earlier and every used NBA season ends no later thanY−1. All H control arrays and dated facts were independently reverified. The prefix policy has236/315/389 training rows; H has423/470/514.

There are12 jobs: two panels × two label policies × three outer development classes. Each job covers seeds0/101/202 and makes35 fits (four selectors, four Ridge, twelve TabICL, twelve direct XGBoost and three residual XGBoost), for420 total. Four isolated workers keep the GPU queue supplied. The new batch waits for the existing J study to finish and verify its saved results. J scores do not choose K settings. The waiting controller is bounded at eight hours and K at three hours; no automatic duplicate or unregistered retry is launched.

Each model worker mounts only its code/runtime, one outer task's training inputs/eligible labels, query inputs and its own output directory. Network access is disabled. The scoring coordinator, outside those workers, reads fixed pre2019 development truth. No2019+ inputs or answers enter this study's model namespaces.

Full-query Spearman averaged over all three seeds and all three development classes ranks candidates. The fixed complete-target subset and fixed three-seed rank average remain secondary results. Direct member controls and the residual component control are reported separately. A learned solution that reduces to one family is not reported as a multi-family winner. The wider-versus44 comparison uses identical query players, labels and seeds. No model is promoted automatically.

Historical limitations remain: the original1428-player pool is incomplete; observed-label admission and complete-target scoring subsets can favor surviving careers; reconstructed source vintages are not uniformly certified. The174 inputs include correlated derivatives, with no assumed benefit. The2019–2025 benchmark was repeatedly inspected in prior research and cannot be called pristine. Its latest standalone H result remains separate from this stack study.

Published materials are explicitly allowlisted code, registration, input-only panels and aggregate proofs. Per-cutoff training label arrays, private facts, identities and raw worker training/OOF records remain on the server. Saved development prediction diagnostics can be exported separately after verification. No new test benchmark evaluation is part of this registration.
