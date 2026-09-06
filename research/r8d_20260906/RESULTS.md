# Completed combinations: 72 development runs

24 configurations, each evaluated on2012–2014 with3seeds. These scores are development correlations, not test accuracy. All72runs completed without errors.

| Configuration | Mean correlation | Seed SD (points) |2012|2013|2014|
|---|---:|---:|---:|---:|---:|
| projection_removed_win2007_uniform_icl128 | 46.68% | 0.11 | 58.54% | 34.25% | 47.24% |
| projection_removed_win2007_uniform_icl32 | 46.43% | 0.07 | 57.98% | 34.25% | 47.07% |
| projection_removed_win2007_disc85_icl32 | 45.09% | 0.31 | 54.79% | 31.99% | 48.48% |
| projection_removed_win2007_disc85_icl128 | 44.93% | 0.25 | 53.95% | 31.94% | 48.89% |
| base_win2007_uniform_icl128 | 44.82% | 0.18 | 56.93% | 28.93% | 48.58% |
| base_win2007_uniform_icl32 | 44.70% | 0.15 | 57.15% | 28.83% | 48.13% |
| projection_removed_win2003_disc85_icl32 | 44.43% | 0.22 | 58.91% | 21.14% | 53.25% |
| projection_removed_win2003_disc85_icl128 | 44.31% | 0.16 | 58.50% | 21.26% | 53.16% |
| projection_removed_win2003_uniform_icl128 | 43.66% | 0.18 | 57.46% | 22.99% | 50.53% |
| projection_removed_win2003_uniform_icl32 | 43.53% | 0.21 | 57.04% | 22.99% | 50.57% |
| skill_win2007_uniform_icl128 | 43.24% | 0.06 | 55.81% | 28.74% | 45.16% |
| skill_win2007_uniform_icl32 | 43.19% | 0.37 | 55.51% | 29.09% | 44.97% |
| skill_win2007_disc85_icl128 | 43.03% | 0.03 | 50.40% | 28.39% | 50.32% |
| base_win2007_disc85_icl128 | 43.01% | 0.09 | 50.78% | 29.63% | 48.63% |
| base_win2007_disc85_icl32 | 42.98% | 0.36 | 50.81% | 29.64% | 48.49% |
| skill_win2007_disc85_icl32 | 42.92% | 0.25 | 50.94% | 28.53% | 49.30% |
| skill_win2003_uniform_icl128 | 42.17% | 0.39 | 54.86% | 24.34% | 47.32% |
| skill_win2003_uniform_icl32 | 42.01% | 0.38 | 54.65% | 23.95% | 47.43% |
| skill_win2003_disc85_icl128 | 41.92% | 0.45 | 55.36% | 22.34% | 48.06% |
| skill_win2003_disc85_icl32 | 41.65% | 0.36 | 55.31% | 21.55% | 48.08% |
| base_win2003_disc85_icl32 | 41.48% | 0.33 | 56.08% | 20.71% | 47.64% |
| base_win2003_disc85_icl128 | 41.30% | 0.10 | 55.85% | 20.31% | 47.74% |
| base_win2003_uniform_icl32 | 40.81% | 0.14 | 55.01% | 18.98% | 48.44% |
| base_win2003_uniform_icl128 | 40.51% | 0.27 | 54.96% | 18.93% | 47.64% |

The strongest development configuration removes inherited percentile/projection values, starts training cohorts in2007, uses uniform WAR weighting, and uses128 TabICL estimators. Its mean is46.68%; the corresponding32-estimator version is46.43%. Neither establishes the60%test goal. The ongoing50-feature screen retains its preregistered baseline; after it finishes, qualifying features should be checked with the projection-removal configuration using historical development and confirmation only.
