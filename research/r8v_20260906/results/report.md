# R8v completed model-family comparison

All 48 registered tasks completed with zero errors in 34.1 seconds. The six TabICL32 reference tasks reproduce every saved R8u raw/canonical prediction and score exactly. Frozen code/reference hashes and the recomputed final summary match.

All numbers below are the existing mean Spearman metric multiplied by 100. This is a pre-2019 development comparison, not classification accuracy or a 2019–2026 test result.

| Model/background | Mean | 2012 | 2013 | 2014 | Seeds |
|---|---:|---:|---:|---:|---:|
| college_consensus_tabicl16 | 33.7782 | 32.4946 | 29.1018 | 39.7382 | 3 |
| college_consensus_sg_tabicl16 | 33.7290 | 32.4801 | 28.7240 | 39.9828 | 3 |
| college_consensus_tabicl45 | 33.7053 | 32.0039 | 29.4220 | 39.6898 | 3 |
| college_consensus_sg_tabicl45 | 33.6553 | 32.0785 | 28.7272 | 40.1602 | 3 |
| college_consensus_sg_tabicl32 | 33.6424 | 32.1194 | 28.8681 | 39.9398 | 3 |
| college_consensus_tabicl32 | 33.5152 | 31.2295 | 29.5213 | 39.7947 | 3 |
| college_consensus_extratrees_leaf5 | 30.5541 | 13.2518 | 30.0528 | 48.3578 | 3 |
| college_consensus_sg_extratrees_leaf5 | 28.4759 | 14.5794 | 28.5030 | 42.3453 | 3 |
| college_consensus_extratrees_leaf15 | 28.1113 | 11.2316 | 27.6257 | 45.4765 | 3 |
| college_consensus_sg_extratrees_leaf15 | 27.9178 | 10.7457 | 28.0740 | 44.9336 | 3 |
| college_consensus_ridge30 | 25.6927 | 23.2688 | 28.2085 | 25.6007 | 1 |
| college_consensus_sg_xgb_depth3 | 25.3967 | 0.5820 | 33.4406 | 42.1674 | 3 |
| college_consensus_ridge300 | 25.2937 | 18.0306 | 28.4198 | 29.4307 | 1 |
| college_consensus_sg_ridge30 | 24.9565 | 22.7205 | 28.3141 | 23.8349 | 1 |
| college_consensus_sg_xgb_depth5 | 24.8872 | -0.7504 | 29.5725 | 45.8394 | 3 |
| college_consensus_xgb_depth3 | 24.8157 | -1.0799 | 33.6551 | 41.8718 | 3 |
| college_consensus_sg_ridge300 | 24.7867 | 17.7781 | 28.5543 | 28.0277 | 1 |
| college_consensus_xgb_depth5 | 24.7049 | -4.4421 | 33.0051 | 45.5518 | 3 |
| college_consensus_ridge3000 | 17.2876 | 4.3291 | 24.5293 | 23.0044 | 1 |
| college_consensus_sg_ridge3000 | 17.2476 | 4.0116 | 23.7512 | 23.9800 | 1 |

The best registered configuration is TabICL16 without SG at 33.7782, versus 33.5152 for the TabICL32 reference: only 0.2630 points higher. TabICL16 helps 2012 but is slightly worse in 2013 and2014 than that reference. More estimators did not reliably improve results. The optional SG field does not consistently improve the other settings, so its earlier positive contrast is not a general model-family gain.

ExtraTrees is the strongest alternative overall but remains below TabICL; it is stronger in 2014 and markedly weaker in 2012. Ridge and CPU XGBoost are also lower overall. These differences do not establish that blending helps; no blends were run. There is no substantial overall improvement here and no automatic promotion.

Effective TabICL ensemble counts were exactly 16, 32 and 45 as requested. Effective predictor widths were 45 without SG and 46 with SG. Ridge preprocessing records confirm that fitted sample counts equal training-row counts; imputation, missing indicators and scaling used training rows only. Native NaNs were retained for ExtraTrees/XGBoost, with XGBoost explicitly on CPU. Full constructor, cap, preprocessing, fold and seed records are in `state.json` and `run_verification.json`.

The benchmark remains developmental and retains original source/universe limitations. SG was chosen from earlier development screening, and this grid introduces further selection uncertainty. No held-out outcome, confirmation class, blend, data mutation or publication was used.
