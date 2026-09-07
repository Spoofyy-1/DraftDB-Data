The frozen TabICL + Ridge + CatBoost stack scored **36.74% order correlation on the 2019–2025 draft classes**. The earlier standalone H candidate scored 30.87%; the new result is 5.87 percentage points higher. Model inputs, settings and training targets also changed, so the difference cannot be attributed to stacking alone.

On 2020–2025, matching the years of the historical 50.6% result, the new stack scored **36.90%**. The old performance has not been recovered. **The 55% goal remains unmet.**

| Draft class | Stack correlation | Actual draft-order baseline | Players | Latest training-label season |
|---|---:|---:|---:|---:|
| 2019 | 35.79% | 40.21% | 58 | 2018 |
| 2020 | 34.73% | 35.02% | 58 | 2019 |
| 2021 | 42.29% | 40.84% | 56 | 2020 |
| 2022 | 30.09% | 26.24% | 52 | 2021 |
| 2023 | 43.93% | 11.06% | 56 | 2022 |
| 2024 | 23.22% | 13.40% | 55 | 2022 |
| 2025 | 47.12% | 17.64% | 57 | 2022 |
| Seven-class mean | **36.74%** | **26.35%** | **392** | — |

These percentages are Spearman correlation × 100, not the percentage of players placed in exactly the right order. Development performance on 2012–2014 was 42.69%; that was used to select the stack and is separate from this test result.

The stack gives equal weight to TabICL (16 estimators, no normalization, outlier threshold 2), Ridge (alpha 30), and CatBoost (600 trees). TabICL and Ridge use 127 college, shooting, game and team inputs. CatBoost uses 44 inputs. Three fixed seeds are combined by averaging ranks within each model family, then blending family ranks.

All 21 reference member predictions and 12 stacked reference predictions reproduced exactly. The 49 new test fits completed in 114 seconds. All seven prediction files were frozen before the scorer opened any test answers; 50 registered files, model settings, preprocessing fingerprints, identity alignment and training-season cutoffs were verified. No current-class draft order or outcome entered model fitting.

Training expands into earlier cohorts and uses observed first-season WAR with actual NBA season ending no later than test year minus one. Verified label coverage currently ends at 2022, so the 2024 and 2025 models omit some newer training seasons your rules would allow. Two unresolved inherited first-season facts remain excluded; missing training outcomes are not fabricated as zeros.

The complete-target subset scored 31.80% and is secondary. The main score preserves the original full-pool scoring convention in which missing outcome components contribute zero. The benchmark has been inspected in prior work, its player population is incomplete, and original feature publication dates are not fully certified. This is a diagnostic evaluation, not a pristine holdout.

[Frozen model, predictions and verification](https://github.com/Spoofyy-1/DraftDB-Data/tree/main/research/r9stacktest_20260907) · [127-column inputs and source records](https://github.com/Spoofyy-1/DraftDB-Data/tree/main/research/r9stacktest_inputs_20260907)
