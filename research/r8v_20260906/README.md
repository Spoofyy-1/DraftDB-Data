# R8v fixed model-family comparison

The study registers 48 tasks on the unchanged pre-2019 development folds. Two fixed backgrounds use 41 source-college fields plus four real pre-draft consensus fields, either alone or with the previously screened shooting-guard indicator. No other feature selection, blends, combinations, confirmation or 2019–2026 testing is included.

| Model | Registered settings | Seeds per background |
|---|---|---:|
| TabICL | 16, 32 or 45 requested estimators; prior norm/outlier/batch settings retained | 0, 101, 202 |
| Ridge | alpha 30, 300 or 3000; deterministic SVD solver | 0 only |
| ExtraTrees | 500 trees; minimum leaf 5 or 15; feature fraction0.7; two CPU threads | 0, 101, 202 |
| XGBoost | CPU histogram; depth3 or5; 300 trees; learning rate0.05; child weight5; lambda5; row/column fractions0.8; two threads | 0, 101, 202 |

Ridge uses a training-fitted median imputer, missing indicators and StandardScaler. All-missing training columns remain present with zero fill; indicator membership is learned from training missingness. The server fixtures verify training medians, empty-column behavior and unchanged fitted statistics after extreme validation inputs. ExtraTrees and XGBoost receive native NaNs; unsupported native ExtraTrees behavior fails closed. No validation row enters a fit operation. All estimators use the same canonical identity ordering and exact-input-vector prediction averaging as R8u; identifiers and draft picks never enter model features.

Requested and effective constructor parameters are recorded. TabICL also records the effective ensemble count and feature count, so a library-imposed cap cannot be mistaken for additional models. Constructor errors fail closed. Installed server versions were inspected as scikit-learn1.9.0, XGBoost3.4.1 and TabICL2.2.0; no packages are installed for this study.

Before GPU tasks begin, the CPU preflight reproduces both backgrounds through an unchanged copy of the R8u preparation code and requires exact completed-reference input, player, label, column and full-matrix hashes. Before interpreting any model results, all six TabICL32 tasks must also reproduce the saved R8u raw/canonical predictions and scores exactly. The summary withholds interpretation while those replays remain pending and rejects changed reference results.

Local fixtures passed the 48-task registration, deterministic Ridge deduplication, 20 variant summaries, required reference gating and 12 tamper checks. Constructor TypeError was verified to propagate without fallback. Fixture values are never study/model data or saved research results. The parent-reviewed input sources remain unchanged, with source-vintage and original-universe limitations intact.

Four workers interleave GPU TabICL and CPU model tasks under a two-hour,140G host-memory and22-CPU-equivalent unit cap. Network access is disabled inside the isolated mount. Code, plans and reference hashes are frozen before the first study model. No data, source, R8u or earlier study is mutated; nothing is published by this worker.
