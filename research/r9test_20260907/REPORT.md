# Frozen model test: 2019–2025

The model associated with the 57.9% development result scored **29.3% on the complete-outcome test subset** and **30.9% on the full available benchmark**. These are Spearman rank correlations multiplied by 100, not the percentage of draft positions predicted correctly.

| Draft | Full benchmark | Draft-order baseline | Complete-outcome subset | Players: full / complete | Labels through |
|---|---:|---:|---:|---:|---:|
| 2019 | 30.2% | 40.2% | 35.8% | 58 / 33 | 2018 |
| 2020 | 26.3% | 35.0% | 9.2% | 58 / 32 | 2019 |
| 2021 | 37.8% | 40.8% | 36.2% | 56 / 33 | 2020 |
| 2022 | 18.8% | 26.2% | 22.6% | 52 / 39 | 2021 |
| 2023 | 37.2% | 11.1% | 33.6% | 56 / 46 | 2022 |
| 2024 | 23.1% | 13.4% | 24.0% | 55 / 51 | 2022 |
| 2025 | 42.7% | 17.6% | 43.3% | 57 / 55 | 2022 |
| Seven-class mean | **30.9%** | **26.3%** | **29.3%** | 392 / 289 | — |

The complete-outcome subset's draft-order baseline was 21.3%. Class scores receive equal weight. The frozen model combines seeds 0, 101 and 202 by equal rank averaging. For comparison with the development headline's mean-of-seed convention, the test mean of individual seed correlations was 29.3% on the complete-outcome subset and 31.0% on the full available benchmark.

The recipe was selected before this evaluation: s2000_gap1_drafted_h2_E_tabicl16_o0p5. It uses 44 fixed predictors and trains on historically drafted players with two observed NBA-season WAR labels. Nine development fits reproduced the original raw predictions, canonical predictions and model settings exactly. Each test year ran in its own process and isolated filesystem/network namespace, with only that year's input bundle. All seven prediction files were hashed and frozen before the scorer opened any test outcomes. Actual draft position was used only by the scorer for the comparison baseline.

Training labels obey the prediction-year cutoff; missing training outcomes were not zero-filled. The verified calendar currently stops at 2022, so the 2024 and 2025 fits omit otherwise allowable newer training seasons. The original benchmark's outcome horizons are five seasons for 2019–2021, four for 2022, three for 2023, two for 2024 and one for 2025.

The full benchmark retains the inherited scoring treatment in which missing outcome components contribute zero. The complete-outcome subset requires every outcome component for that horizon to be observed, which favors players with sufficient observed career length; it is not full-class accuracy. All predictions were made before this scoring-only mask was applied.

This remains a diagnostic result: the benchmark was repeatedly inspected in earlier work, the original player pool omits some historical draftees, and retrospective college inputs are not fully certified to their original publication dates. It should not be described as a pristine holdout or proof of a leakage-free production model. No test result was used to tune this model or promote a new recipe.

Prediction freeze: `443cf9dab191de42a09ca393346969f42e6229a1137b002dd9a99a29eb35076f`
Scored at: 2026-09-07T08:42:14.530940+00:00
