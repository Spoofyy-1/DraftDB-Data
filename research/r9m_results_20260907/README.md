# R9M saved development results

Independent saved-result verification passed: 105 frozen files; six unchanged L controls (54 original fits, 90 saved member vectors); 18 new jobs (162 new fits); 4,128 same-panel and 11,400 cross-panel score records; 344 same-panel summaries; 950 cross-panel summaries; all 1,824 design aliases; and 1,900 paired cross-panel comparisons with base44/F50. The verifier performed zero model fits and ran with M read-only, no GPU devices, no network and no other study mounted. Only development years 2012–2014 were read.

## Verified result

The strongest actual multi-family stack is **cross_0771**, equal one-third weights on TabICL and Ridge(alpha=30) using **f50_game_team**, plus CatBoost using **base44**. Its full-query mean Spearman correlation over three seeds and three folds is **0.42446990012264746**. The complete-outcome subset is secondary at **0.5069561499864694**. This is a ranking correlation, not the fraction of correct predictions.

The separate fixed three-seed family-rank-average mode scores **0.42308001483178015 full / 0.5272453657240946 subset**. It averages each stochastic family’s percentile ranks across seeds, reranks those family averages, and applies the fixed weights. It must not be confused with averaging the nine fold/seed correlations.

The winning full score improves on the same equal-third base44 recipe by **0.04532087900637566**. All fold means improve: **+0.04871757574525176 (2012), +0.029965769275679455 (2013), +0.05727929199819587 (2014)**. All three seed means also improve. Relative to the same equal-third F50 recipe, mean gain is **0.05616504980471926**, but the 2014 fold regresses by **0.05804447441691468**.

The strongest same-panel stack is **f50_game_team / stack_013**, 75% TabICL + 25% Ridge30: **0.4180092326475242 full / 0.4796408586931515 subset**. Its fixed three-seed mode is **0.42152221043615007 / 0.4805389449299235**. The strongest standalone is TabICL on f50_game_team: **0.4035601816582227 full / 0.4422241416980532 subset**. Single-model endpoints were checked separately and did not receive the actual-stack headline.

## Scope and suggested next diagnostic

The evidence supports retaining model-specific feature views: the winning CatBoost member uses base44 while TabICL/Ridge use the broader game/team panel. A bounded next profile check could hold those views and equal-third weights fixed, retain the current CatBoost depth-3 MAE/L2=100/600-tree anchor, and compare only depths 2 and 4 at the same other settings across all three seeds/folds. That requires 18 new CatBoost fits while reusing unchanged TabICL/Ridge predictions. This is a suggestion only; no next study was implemented or launched.

All scores are development diagnostics on repeatedly reused folds, with selection optimism from 950 cross-panel recipes plus same-panel candidates. The 50.70% secondary subset and 52.72% fixed-mode subset are not the full-pool headline. No independent later-year generalization or attainment of the 55% goal is established. Existing source-vintage, population and missingness limitations remain. Width-changing feature comparisons are not matched-shuffle causal information tests.

Control provenance is checked against the previously independently verified L archive hashes, original frozen input bytes, model/runtime hashes and current arrays/PID order. The pinned scheduler invokes that gate before new-job submission and its completion log begins with the six reused records. Historical process tracing was not available; saved audit consistency is not forensic proof against every possible external action.

## Files and publication boundary

The 56-member archive retains original saved result bytes, original reused L records, code, registration and aggregate provenance. It excludes all input/scoring NPZ, private label values, identities, credentials, K files and raw source articles. Hash references to omitted private inputs remain intentionally. Raw member and blend vectors match exactly; independent tied-rank/correlation arithmetic differs by at most **2.220446049250313e-16**.

`verify_saved.py` imports no model estimators and never calls the coordinator scorer. `L_ARCHIVE_ALLOWLIST.json` and `L_verification.json` are compact prior proof dependencies. `ARCHIVE_ALLOWLIST.json` lists every allowed archive member. `archive_manifest.json` pins the archive/proof bytes. `transport_verification.json` confirms all downloaded member hashes and the JSON label/identity boundary without extracting or duplicating the archive. `PUBLIC_ALLOWLIST.json` is the parent’s explicit publication allowlist. The verification process did not publish files; publication follows root review of the explicit allowlist.
