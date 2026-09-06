# R8u completed individual biography screen

All123 registered tasks completed with zero errors in 109.4 seconds (67.46 trials/minute). All frozen code/data-reference hashes are unchanged. The three baseline seeds exactly reproduce the completed R8t baseline raw predictions, canonical predictions and scores.

Numbers below are the existing mean Spearman metric multiplied by100; gains are points on that scale. They are development diagnostics, not classification accuracy or held-out test performance.

The fixed source-college plus real-consensus baseline is 33.5152. Every single/control arm adds the same one-column slot.

| Field | Actual | Shuffled mean | Matched gain | 2012 gain | 2013 gain | 2014 gain |
|---|---:|---:|---:|---:|---:|---:|
| vmb_position_sg | 33.6424 | 32.5929 | +1.0495 | +1.8286 | +0.8656 | +0.4542 |
| vmb_listed_bmi | 34.5139 | 33.7026 | +0.8113 | +0.6077 | +5.8373 | -4.0110 |
| vmb_position_pf | 31.5397 | 31.0090 | +0.5307 | +0.2253 | +1.0076 | +0.3593 |
| vmb_position_sf | 32.1087 | 32.7667 | -0.6580 | -1.5521 | +1.9522 | -2.3742 |
| vmb_age_reported_years | 30.9511 | 32.0402 | -1.0890 | -1.0221 | -2.6705 | +0.4256 |
| vmb_position_pg | 31.4040 | 32.5827 | -1.1787 | -4.6746 | +0.9745 | +0.1640 |
| vmb_position_c | 29.7687 | 31.8476 | -2.0789 | -0.3367 | -4.2801 | -1.6198 |
| vmb_college_class_year | 31.4931 | 33.7328 | -2.2397 | -3.6132 | -2.2190 | -0.8870 |
| vmb_listed_height_in | 30.9407 | 33.6305 | -2.6898 | -3.9146 | -3.1263 | -1.0285 |
| vmb_listed_weight_lb | 29.6048 | 32.6839 | -3.0790 | +0.9211 | -4.0186 | -6.1397 |

Shooting-guard position is the strongest consistent matched signal: positive in every fold and every model-seed mean. Its actual mean exceeds the no-extra baseline by only0.1273points, so the practical improvement is small. Power-forward position beats its controls consistently but remains below the no-extra baseline; this is not a deployable improvement. BMI has a positive average contrast dominated by2013 and a strongly negative2014 contrast, so it is unstable. Seven fields have negative average matched effects. Listed height, college class and center position hurt in every fold.

These results explain part of the harmful all-biography-family result but do not identify causal effects or certify individual features for deployment. Missingness and source vintage can limit transport; position indicators overlap and ten exploratory comparisons introduce selection uncertainty. No feature was promoted, no combination or confirmation was run, and no2019–2026 outcomes were accessed. The next protocol is the parent’s decision.

Full paired fold/seed/control contrasts are retained in `results/state.json`; `results/run_verification.json` records the final execution and immutable-registration checks.
