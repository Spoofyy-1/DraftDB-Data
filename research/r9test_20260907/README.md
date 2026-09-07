# Frozen H model evaluation, 2019–2025

See [REPORT.md](REPORT.md) for the measured results and limitations. The model connected to the 57.9% development subset score transferred at 30.9% on the full available benchmark and 29.3% on the complete-outcome subset. These are mean cohort Spearman correlations ×100.

## Reproducibility

`recipe.json`, `scoring_policy.json`, `frozen.json` and `approval.json` fix the model, metric, code/runtime and seven input manifests. `reference_gate.json` records nine exact development replays. Each year has raw and canonical seed predictions, the fixed rank ensemble and a completion record under `results/YYYY/`. `results/prediction_freeze.json` binds all seven completed predictions before answers were opened. `results/test_result.json` contains the aggregate and per-year scores; the scorer maintains its hash-chained evaluation ledger privately.

Prediction uses one year's training/input bundle in a fresh network-isolated process. No query-class labels, actual draft-order predictors, vault access, other-year bundles or reused prediction cache are mounted. Training admits only earlier drafted cohorts with two observed NBA-season labels satisfying the historical cutoff; missing training WAR is never filled with zero. All nine original H reference predictions and tie/model audits matched exactly. The 2024/2025 training calendar remains limited to verified seasons through 2022.

The numeric test feature exports are saved separately in `../r9test_inputs_20260907/`. Historical development material lives in `../r9h_20260907/`. Bundle manifests are public; training-label bundles, raw answer files, source identities and model checkpoint blobs remain outside this export. Hashes identify those private runtime files without publishing them. This directory is an audit package, not a fully self-contained environment.

The complete-target subset is selected by the scorer after predictions and favors players with sufficient observed career length. The full benchmark retains the inherited missing-outcome scoring rule and original incomplete player pool. Previously inspected benchmark data and retrospectively collected college features prevent pristine holdout certification. No test score was used to tune or promote a model. The separately registered development GPU queue continues unchanged.
