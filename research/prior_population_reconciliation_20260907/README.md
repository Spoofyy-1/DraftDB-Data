# Historical population reconciliation — offline review

The complete 2007–2011 selected-member registry contains **300 people**, while only **260** match the historical selection slots in the original 1,458-row training pool and **251** match in the current 1,428-row pool. The existing studies retain an incomplete historical population. This audit proposes repairs; it does not certify their scores, modify a study, or claim model improvement.

| Historical class | Source registry | Original matching selected rows | Current matching selected rows | Missing or misclassified upstream | Removed by calendar gate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2007 | 60 | 50 | 47 | 10 | 3 |
| 2008 | 60 | 51 | 50 | 9 | 1 |
| 2009 | 60 | 51 | 49 | 9 | 2 |
| 2010 | 60 | 54 | 51 | 6 | 3 |
| 2011 | 60 | 54 | 54 | 6 | 0 |
| Total | 300 | 260 | 251 | 40 | 9 |

Of the 40 upstream omissions, **four have recoverable legacy identities** in the original prospect table but are incorrectly marked `was_drafted=0`, `declared_only=1`, and `split=train_declared`. Independent contemporary selection sources establish that they belong in the historical selected population. Their inherited never-played/zero assumptions are not adopted. The other **36 have no recovered exact source-name or source-ID identity** in that table; unresolved spelling aliases remain possible. The missing upstream players/timeline builder prevents a stronger individual causal claim for those 36.

This corrects the initial slot-only finding: checking historical selection slots alone missed the four misclassified identities. Exact same-cohort name checks recovered them. Every original row and source file remains unchanged.

The additional nine selected rows are among the 30 original training rows rejected by the inherited calendar resolver. The resolver rejects globally ambiguous/missing normalized RAPTOR names or source-label mismatches before the later date cutoff. All 30 removed PIDs match its recorded rejection ledger exactly. Two father/son name collisions and an unrelated same-name collision affect the missing historical subset; unreviewed Wikipedia caches must not substitute for explicit identity evidence.

## Existing material available for repair

All **49 missing members** remain in the private proposal independently of features and labels. Existing verified-source packages contain an exact candidate college row for 22, an official same-year combine row for 20, and dated mock facts for 24; **38 have at least one such family**. Ten already have compatible source-only 41-field college context rows under recovered legacy IDs. These are availability inventories, not new numeric feature matrices or approvals to use every field.

College joins use only source seasons at or before the draft and a maximum one-year gap. Mock parsers replay the frozen table/fact hashes and verify publication/capture dates before the draft. Combine request years and every row's season agree. Historical college/combine release vintages remain unverified; some combine prospect IDs differ from later NBA IDs and must remain separate namespaces. Source-only membership IDs allow rows to survive even when a global identity bridge is absent.

Four missing members have candidate historical RAPTOR calendars. One unambiguous source-name/Basketball-Reference UID, corroborated by the historical selection-slot and official combine identity, yields **one observed 2009 WAR cell**, usable no earlier than prediction year 2010. Its original ordinal cell was blank; no claim of agreement with an existing numeric label is made. This is a proposed dated observation, not a complete five-season target. The other three identities remain quarantined pending explicit cross-system bridges; one has two overlapping same-name NBA calendars, which cannot be resolved by choosing whichever WAR matches.

The other 45 lack an exact eligible source calendar in this bounded lookup. Missing matches do not establish nonparticipation or zero contribution. None of the 49 has a newly verified complete first-five-observed-season target.

## Exact horizon eligibility

For predicted draft Y and horizon h, a usable target requires **every ordinal 1…h** with actual `season_end <= Y−1`. Missing records, delayed debuts, incomplete follow-up, and unknown identities never become zero. Membership is fixed separately, using only an earlier class and a membership-source date no later than the cutoff.

The current inherited development pool has these counts of complete observed targets:

| Predicted draft | Current training rows | h=1 | h=2 | h=3 | h=4 | h=5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2012 | 251 | 236 | 143 | 80 | 31 | 0 |
| 2013 | 329 | 315 | 200 | 125 | 70 | 25 |
| 2014 | 403 | 389 | 255 | 170 | 109 | 61 |

These reproduce the inherited training window starting in 2007 and ending at Y−2; they do not endorse its population construction. The separate 300-member inventory retains every source member and checks earlier-class/date eligibility at each prediction year 2008–2019, followed independently by h=1…5 observability. It uses existing dated labels and the one proposed source observation; no target values are parsed by the horizon inventory.

The inherited kernel fills missing seasonal targets with zero before horizon weighting/ranking. There are already **15, 14, and 14 training rows with no observed NBA season by the respective development cutoffs**. Merely appending all missing memberships would amplify that unsupported imputation. The inherited scoring path also fills absent mapped truth with zero and must not be reused unchanged for a newly complete population.

A five-played-season experiment cannot run on the 2007-start window at the end-2011 cutoff: there are no complete targets. A next diagnostic must declare a feasible observed horizon, or independently reconstruct an earlier training population. Keeping only complete observed targets describes a censored/observed subset; it does not make all 300 memberships fully labelled or remove selection bias automatically.

## Proposed next dataset boundary

Use the complete historical membership registry as the left side of every join. Preserve the four corrected legacy identities and all unresolved source-only identities; keep original benchmark pools unchanged. Attach dated source features without inventing values. Store seasonal labels, identity approval, and horizon observability separately. Pass only eligible observed targets to a specifically registered diagnostic; retain all unavailable memberships in its censoring report. Any zero outcome needs affirmative dated evidence under an explicitly defined target, never a missing source lookup.

No existing model or source package was changed. No network requests, 2019+ test/vault access, model fits, or scoring occurred. Eight integrity tests passed, including future-season exclusion, missing-ordinal rejection, population preservation, and original-source hash checks.

The public allowlist contains only aggregate reports and verification. Exact identities, historical selection positions, source-ID crosswalks, source evidence, label observations, and row-level horizon eligibility are private.
