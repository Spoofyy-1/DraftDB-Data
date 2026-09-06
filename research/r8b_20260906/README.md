# Incumbent reproduction under actual calendar cutoffs

This is a development-only diagnostic, registered after the R8 context sweep. It was a next step listed before R8 confirmation. It does not read or score 2019–2026 tests, and does not rerun confirmation.

Six variants compare the current incumbent, removal of scouting grades, drafted-only training, and targeted teammate/skill/all-context additions. The model-only functions were extracted from the existing engine without executing its training/vault/test loaders. Fixed saved incumbent weights: rich rows 0 XGBoost / 0.75 TabICL / 0.25 ridge; thin rows 0.5 / 0 / 0.5. Saved hyperparameters and legacy feature columns remain in the data manifest. No model is declared certified: legacy features have unresolved source provenance and the incumbent was tuned on these historical folds.

Labels are actual-calendar-filtered to season ending ≤ fold Y−1. The scoring folds are 2012–2014 and use only pre-2019 labels. Source sample includes matched undrafted NBA entrants for incumbent reproduction, with a separate drafted-only variant. Scores are not directly comparable to the old dashboard.

The network-disabled worker receives only this folder, the existing Python runtime, GPU devices, and the cached TabICL checkpoint. Its first step checks that original test and vault paths are inaccessible.
