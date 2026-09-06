# Bounded TabICL inference-order audit

Completed on the H100 with one model fit and ten predictions in3.32seconds. No numerical change exceeded the preregistered1e-5 threshold, and no ordering of distinct input vectors changed. Exact ties and almost-ties among identical all-missing input rows do change at floating-point precision; predictions and displayed rankings must not be described as exactly invariant.

| Change to query | Largest absolute prediction change | Rank correlation with baseline | Strict pair inversions |
|---|---:|---:|---:|
| Identical repeat |0|1|0|
| Reverse rows |1.49e-8|0.998338|2|
| Three fixed random row permutations |5.96e-8|0.998338–0.998339|2 each|
| Replace pandas index only |0|1|0|
| Append/prepend32unlabeled historical rows |1.49e-7|0.997688|4 each|
| Shuffle combined87-row pool |1.49e-7|0.998844|1|

`results/order_audit.json` contains each numerical comparison, timings, constructor settings, ordered columns, hashes and call count. `results/duplicate_analysis.json` records exact duplicate groups and a margin proof that all observed inversions occurred within identical vectors. `inspect_duplicates.py` makes no new predictions: it reuses only the saved2012 R8r baseline prediction vector after requiring its hash to match the audit exactly. The training matrix, query matrix and training-label hashes also match R8r exactly.

There are48 distinct source-input vectors among55players. The sole duplicate group contains8players with all41features missing, at zero-based original query positions3,13,28,44,45,49,51,54. Their pids are `P43f8251240`, `P089ae8ca96`, `Pc0b16a51f2`, `P0dca4f55c4`, `P8e2f7481af`, `Pf3fb310df6`, `Pefaae49c8b`, `P404f9fdfb6`. This group has28pair comparisons. Its baseline scores already span4.66e-10 despite identical inputs. The smallest baseline score gap between distinct input vectors is8.7708234787e-5, whereas twice the largest observed change is2.9802322388e-7. Because two prediction perturbations can close a gap by at most twice their maximum magnitude, all observed inversions are provably inside the duplicate group. This proof does not identify the individual inverted pairs within that group; the benchmark saved aligned-vector hashes and aggregate comparisons rather than individual changed vectors.

The current R8r metric calls SciPy Spearman directly (`work/r8r/worker.py`, function `rho`), so it handles exact ties by average ranks rather than explicit draft-order sorting. Numerical splitting of mathematically identical predictions can nevertheless change ranks and the metric slightly. A future separately registered policy should assign the same prediction to exactly identical input vectors and use average ranks for scoring. Display-only ordering within tied groups should use a preexisting identity key independent of draft order. Do not select a rounding tolerance based on accuracy, retroactively rewrite completed scores, or claim that this single-fold audit proves invariance for every backbone.

The estimator was TabICL2.2.0 with Torch2.12.1+cu130: CUDA,32requested/effective estimators,41effective features, random_state0, batch_size32, norm_methods='none', outlier_threshold2.0, feat_shuffle_method='latin', kv_cache=False, checkpoint `tabicl-regressor-v2-20260212.ckpt`. Remaining installed defaults are recorded in the result. The benchmark calls the constructor directly; any TypeError fails closed. No weight-reuse helper or legacy constructor fallback was invoked.

The sandbox contains only251training input rows from2007–2010, their labels ending by2011,55query input rows from2012 and32unlabeled additional input rows from2011. Query/additional outcome labels, actual picks, draft-order features and2019+files are physically absent. Only the explicit41source feature columns reach selection and TabICL; pid, draft_year and pandas index never become model features. The original CPU selector is fit on training rows only; all41columns are retained in its importance ordering. No legacy engineering, coverage or shrinkage path is called. Label and input provenance caveats inherited from the source-only study remain outside this numerical audit's scope.

`run_sandbox.sh` mounts only this bundle, the Python environment and the cached checkpoint; networking is disabled and the process drops privileges. Unit `draftdb-r8order-20260906` was capped at120seconds,24GiB RAM and two CPU equivalents. This was a bounded diagnostic; no WAR outcome scoring, model selection, new study launch or changes to existing experiments occurred.
