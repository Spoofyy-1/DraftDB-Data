# Fifty-feature results and the control problem

The initial screen completed 270/270 runs: all 50 individual statistics plus a baseline across three seeds (153 runs), followed by 39 combinations across the same seeds (117). No run failed. These are retrospective development scores on the 2012–2014 classes, not the goal benchmark.

An added constant column reproduced much of the improvement. Adding zero or all-missing values raised the mean from 42.5677% to 44.8594%; the best real statistic, usage rank within the team, reached 45.5030%. The empty-column improvement is about 78% of the apparent real-feature improvement, a diagnostic comparison rather than a causal decomposition. The old selector changed its sampling and selected feature count when columns were added. Availability alone also reached 45.1292%. These controls invalidate treating the original gates as confirmed feature discoveries.

| Diagnostic arm | Three-seed development mean |
|---|---:|
| f50_peer_rank_usage | 45.5030% |
| f50_control_availability | 45.1292% |
| f50_control_zero | 44.8594% |
| f50_control_nan | 44.8594% |
| f50_control_duplicate_ts | 44.0588% |
| f50_control_permuted_usage | 43.9848% |
| baseline | 42.5677% |

The next study selects an ordered base feature set once per historical fold using eligible training data only. Every real candidate is compared with shuffled versions in identical reserved column positions, preserving its missingness, distribution, and cardinality. Coverage, shrinkage and base selection stay fixed. Pair comparisons will use four arms with identical two-column layouts.

The separate TabICL-only study completed 54/54 runs. The simplest best three-seed configuration—32 requested ensemble members, 60 selected features, shrinkage 400—reached 50.0067% development mean. Larger requested ensembles sometimes produced identical predictions; requested and effective ensemble sizes must be distinguished. This is an avenue for further validation, not a 50% test result.

Only one new frozen 2019–2025 benchmark has been measured: 42.5358% mean Spearman using a strict 2018 label cutoff. It remains unchanged. All subsequent choices above use earlier development data. The inherited benchmark has already been repeatedly inspected in prior research, and inherited feature publication dates remain incompletely certified.

The 50 real statistics, definitions and train/test input sidecars are saved separately. Diagnostic zero/shuffle controls are never promoted as new collected statistics. Each model fit uses earlier cohorts and labels mapped to actual NBA seasons ending by its cutoff; the model worker cannot open held-out files.
