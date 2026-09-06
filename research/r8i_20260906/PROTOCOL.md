# R8i implementation handoff

The implemented first block contains 99 tasks: one contextual no-extra baseline and eight shortlisted statistics, each real or under three registered within-cohort permutations (9317, 18739, 28657), crossed with model seeds 0, 101, 202. It does not repeat all 50 statistics and does not execute pair jobs.

The backbone is standalone TabICL32, top60, M400, uniform WAR, window2007, using the same source exclusions as R8g. The CPU selector receives only base features and runs once per fold per worker process; a deterministic ordered-column hash verifies consistency between processes. Every actual feature and its controls enter the identical `slot_0` position. Missingness, observed-value count, marginal distribution and unique-value count are preserved in shuffles. Base priors, coverage and engineered features are fixed before adding slots.

The scheduler can call `run_variant(id, seed)` and use `summarize_matched(candidates)` after arrivals. The summary requires complete real/control runs and identical base-data/selector hashes, then verifies matched slot masks and dimensions before applying the registered exploratory gate. It never uses the no-extra baseline gain to select a feature. There are at most three provisional candidates. The later disabled pair plan contains four matched two-slot arms and allows no more than three pairs.

This remains a development transfer screen on 2012–2014. It does not claim new test performance, confirm the unrerun 42 features, or establish independent historical-decision validity. Raw input dimensions are recorded (60 base, 61 with one slot), together with the number of nonconstant training columns; the legacy prediction wrapper does not expose the library's final post-preprocessing feature count.

Local verification: Python compilation, deterministic permutation invariance to row order and future-cohort removal, distribution/mask preservation, and empty-summary handling passed. No GPU fit was performed by the independent reviewer. Parent owns sandbox integration, remote launch and result publication.
