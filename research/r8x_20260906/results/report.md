All 318 pair-complement trials completed without errors. Independent local validation reproduced the complete summary; all 18 baseline/single-feature replays matched full predictions, scores and audits exactly, and all 37 frozen files were unchanged.

Runtime: 258.9 seconds; 73.69 trials/minute with four workers.

| Pair | Development | vs baseline | A given B | B given A | Consistent candidate |
|---|---:|---:|---:|---:|---|
| career_slope_usage + posterior_rim | 35.651% | +2.136 pt | +0.866 pt | +1.573 pt | True |
| nondunk_rim_pct + posterior_rim | 35.584% | +2.069 pt | +0.041 pt | +1.005 pt | False |
| career_slope_usage + nondunk_rim_pct | 35.454% | +1.939 pt | +0.976 pt | +0.220 pt | False |
| career_slope_ftp + posterior_rim | 35.326% | +1.810 pt | +1.150 pt | +1.657 pt | True |
| career_slope_ftp + nondunk_rim_pct | 35.263% | +1.747 pt | +1.673 pt | +0.585 pt | False |
| peer_rank_orb + posterior_rim | 35.076% | +1.561 pt | +0.653 pt | +1.459 pt | False |
| nondunk_rim_pct + peer_rank_orb | 34.749% | +1.233 pt | +0.033 pt | +0.869 pt | False |
| career_slope_ftp + career_slope_usage | 34.616% | +1.101 pt | +0.910 pt | +0.631 pt | False |
| career_slope_ftp + peer_rank_orb | 34.240% | +0.725 pt | +1.171 pt | +1.394 pt | True |
| career_slope_usage + peer_rank_orb | 33.892% | +0.376 pt | +0.427 pt | +0.350 pt | False |

Baseline: 33.5152%. Best pair: career usage slope + stabilized rim finishing, 35.6508%; +2.1356 points versus baseline and +0.7114 versus the better single. Both conditional gains were positive in every fold mean and every model-seed mean.

Three pairs met the registered descriptive complement screen: FT percentage slope + offensive-rebound peer rank; FT percentage slope + stabilized rim finishing; usage slope + stabilized rim finishing. The first has negative joint-shuffle gain in 2014; the descriptive gate did not require that joint gain, so it should not be described as uniformly robust under all controls.

These are exploratory 2012–2014 development comparisons selected after a previous feature screen. Conditional shuffles break cross-feature associations; this is not a significance test. No confirmation cohorts or 2019+ benchmark were scored; no model was promoted. The 60% benchmark target remains unmet.
