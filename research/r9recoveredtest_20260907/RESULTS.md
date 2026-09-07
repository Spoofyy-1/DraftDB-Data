The recovered fixed stack scored **40.00% order correlation on 2019–2025**, compared with 36.74% for the previous stack: a measured increase of **3.26 percentage points**. Training targets, cohorts and model mechanisms also changed, so that increase cannot be attributed to blend weights alone.

On2020–2025, matching the years of the historical 50.6% result, this adaptation scored **38.92%**. The historical result has not been recovered, and the 55% target remains unmet.

| Draft class | Recovered stack | Players | Latest training-label season |
|---|---:|---:|---:|
| 2019 | 46.51% | 58 | 2018 |
| 2020 | 38.60% | 58 | 2019 |
| 2021 | 54.88% | 56 | 2020 |
| 2022 | 33.65% | 52 | 2021 |
| 2023 | 45.59% | 56 | 2022 |
| 2024 | 27.39% | 55 | 2022 |
| 2025 | 33.40% | 57 | 2022 |

The fixed primary blend uses 25% TabICL and75% Ridge for richer inputs and the TabICL plus residual-XGBoost hybrid for thinner inputs. Its primary score uses a fixed average across three seeds. The full-pool draft-order baseline is 26.35%; the separate complete-target subset score is 35.06%. Percentages are Spearman correlation ×100, not the percentage of exact draft positions predicted correctly.

The registered control using the previous blend weights scored 40.84% on identical underlying predictions. Restoring the old weights alone therefore did not fix the gap. This control was diagnostic and was not substituted for the preregistered primary result.

All 182 fits completed in 196.73 seconds. All seven prediction files were frozen before scoring. Inputs exclude current-class actual draft order and outcomes; training uses earlier cohorts and actual label seasons ending by test-year minus one.

This uses 127 reviewed inputs instead of the original 257. Original publication vintage and complete historical player coverage are not certified. Verified training-label coverage ends2022, leaving allowed 2023–2024 seasons absent from later training. The inherited full-pool scorer treats missing outcome components as zero; this is a historically reused diagnostic benchmark, not an untouched holdout.

[Registered model and provenance](https://github.com/Spoofyy-1/DraftDB-Data/tree/main/research/r9recoveredtest_20260907)
