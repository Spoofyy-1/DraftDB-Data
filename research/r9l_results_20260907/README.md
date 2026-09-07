# R9L saved development results

Independent verification passed for all 24 saved jobs (216 registered fits), 90 frozen files, 360 member records, 36 reference vector pairs (72 raw/canonical arrays), 4,128 score records, 344 summaries and 301 same-recipe comparisons. Verification performed no fits and ran with only R9L mounted read-only, no network and no GPU devices. Only the 2012–2014 development folds were read.

The archive contains the original saved predictions, score diagnostics, code and registration. It excludes input/scoring NPZ files, individual training/benchmark labels, private identities and all K files. Hash manifests retain references to omitted private inputs for audit; omission is intentional. The original study README is inside the archive.

## Result

The best actual multi-family stack is **add_f50 / stack_013: 75% TabICL + 25% Ridge(alpha=30)**. Its full-query mean Spearman correlation over all three folds and three seeds is **0.40018712462325684**; the complete-outcome subset is secondary at **0.42534494003241236**. These are ranking correlations, not proportions of correctly ordered players.

The separate fixed three-seed family-rank-average mode scores **0.3983522054131563 full / 0.42080494237071814 subset**. It averages each stochastic family’s ranks across seeds, reranks those averages, then applies the fixed stack weights. It is not the mean of the nine fold/seed correlations.

The same recipe on base44 scores **0.36623714351711567**, giving a gain of **0.03394998110614117**. Fold gains are **+0.0011530838760341888 (2012), −0.038469980369786716 (2013), +0.13916683981217598 (2014)**. All three seed means improve, but the benefit is concentrated in 2014.

The strongest standalone control is add_f50 TabICL: **0.3898322360155134 full / 0.39611749143199027 subset**. The strongest base44 stack across all registered recipes scores **0.381036872272636** (stack_010); that is a different recipe and must not replace the paired baseline above.

## Same fixed recipe across feature panels

Every row below uses stack_013. Scores are mean correlations over three folds and three seeds.

| Panel | Full | Subset | Full gain vs base44 |
|---|---:|---:|---:|
| base44 | 0.366237144 | 0.388072375 | +0.000000000 |
| add_bio | 0.286137344 | 0.351312506 | -0.080099800 |
| add_combine | 0.375676096 | 0.381136330 | +0.009438953 |
| add_combine_bio | 0.307394002 | 0.368525726 | -0.058843142 |
| add_f50 | 0.400187125 | 0.425344940 | +0.033949981 |
| add_game | 0.357632196 | 0.378538927 | -0.008604947 |
| add_team | 0.360753252 | 0.385900017 | -0.005483892 |
| all174 | 0.305806678 | 0.334441060 | -0.060430466 |

## Bounded follow-up suggestions

The F50 addition is the clearest lead. First test **F50 + team context** against the F50 anchor with a fixed recipe and all three seeds/folds: team context slightly improved 2013 under stack_013, and team-only stack_012 was the only registered addition/recipe improving every fold and seed mean (+0.012441751386507105 full). This suggests a complementarity question; it does not establish synergy.

A second small candidate is **F50 + verified combine**, because each addition independently helped the same stack_013 mean. Both regressed in 2013, so this should not be sold as a solution to that weak fold. Preserve base44 and F50 anchors, use fixed architecture weights, and report every fold. Do not automatically carry the entire biography block or all174: both were substantially worse here. No new experiment was implemented by this verification task.

## Scope and limitations

Features retain the existing retrospective-vintage, incomplete-population and source-coverage limitations. This is a development diagnostic, not an unbiased holdout result or evidence that the 55% goal was reached. Repeated tuning on the same three folds creates selection optimism. No feature family is causally certified as helpful/harmful by this width-changing comparison; matched shuffle or ablation controls would answer a different question.

TabICL requested and used 32 estimators. Its pinned training-only numerical preprocessing removed 22 constant/unavailable combine fields: add_combine was 81 requested / 59 effective columns, add_combine_bio 91 / 69, and all174 174 / 152. No validation-based schema choice was made.

The before-new-panel gate is supported by the pinned scheduler ordering and the first three durable completion-log entries being the base44 jobs. Independent historical process tracing was not available. Saved audit checks establish consistency with the pinned run, not forensic proof against every possible external access.

## Verification and files

`verify_saved.py` independently implements tied ranks, canonical duplicate averaging, seed averaging, integer-weight blends and correlation arithmetic. Member/blend vectors match exactly; scores and aggregates agree within 2e-14 (the exact observed maximum is in verification.json). It also checks train-only Ridge preprocessing and recorded constructor settings. It imports no model estimators and does not call the coordinator scorer.

`ARCHIVE_ALLOWLIST.json` enumerates all 46 archive members. `archive_manifest.json` pins the compressed bytes, allowlist and verification proof. `transport_verification.json` records the downloaded archive’s independent local member/hash and JSON field-boundary checks. `PUBLIC_ALLOWLIST.json` lists the only files approved for the parent’s publication review. The verification process did not publish files; publication follows the root agent’s explicit allowlist review.
