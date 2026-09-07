# Archived gen11 recovery

The archived 50.6% expanding recipe was recovered by its identity, not by searching for the highest benchmark score. No model was fitted and no test outcome or vault data file was opened. The only vault-related read was the plain Python source to inspect its cutoff implementation.

The original rich weights are **0 XGB / .25 TabICL / .75 Ridge**, thin weights **1 / 0 / 0**. R8baseline instead used **0 / .75 / .25** and **.5 / 0 / .5**. Its 42.5358% strict run therefore was not the original stack reproduced. The original XGB member is itself TabICL plus a q25 residual model; restoring a plain XGB component would still be different.

Original hz=0 fits one discounted five-season Gaussian-rank target. R8baseline passed each score horizon directly. Original main training rows were never season-truncated inside the expanding loop, and incoming rows were limited by draft ordinal rather than actual NBA season dates. Unknown WAR was filled with zero. A compliant adaptation must use explicit observed-prefix targets built from verified actual season cutoffs. It cannot claim exact replay of those historical labeling behaviors.

Original scouts were included. R8baseline removed their values but retained their missingness in coverage/routing. Original broader inputs, engineering and shrinkage are recovered as a configuration specification, not admitted as dated source-safe evidence.

The CURRENT_MODEL recipe and remote gen11_export agree. Current remote source and input-column snapshots were pinned; current436 raw input names also equal the baseline manifest. Historical v3.2 data bytes and original runtime have not been recovered, so byte-identical reproduction is not established. There is no paired causal measurement attributing the performance gap to these differences.

See recipe.json for all original knobs, effective transforms, constructor parameters, ordered columns and source hashes.
