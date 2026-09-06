# College impact metric audit

Thirteen omitted raw fields were reviewed. **None of the current Torvik columns is approved for immediate use by this audit.** Three established definitions—individual ORtg, individual DRtg and defensive Stops—are reasonable reconstruction candidates once their historical inputs and exact implementation are verified. The remaining fields stay excluded for the reasons below. No player rows, draft-pick values, outcomes, model results or new feature joins were read or produced.

This distinguishes a season's date from the date and fitting sample of the formula used to summarize it. A historical college box score can be reconstructed under an old fixed definition. Applying coefficients learned from later NBA seasons to that same box score imports later information through the measurement model. The user's permission to retain the current WAR label definition does not itself authorize that change to predictors.

| Index | Field | End-of-2018 freeze | 2012–2014 development folds |
| ---: | --- | --- | --- |
| 5 | ORtg | Conditional reconstruction; current column unverified | Definition predates all three folds; source dependencies must pass |
| 28 | porpag | Exact formula and calibration unresolved; exclude | Exclude |
| 29 | adjoe | Exact player-field adjustment unresolved; exclude | Exclude |
| 46 | drtg | Conditional reconstruction; current column unverified | Definition predates all three folds; source dependencies must pass |
| 47 | adrtg | Exact adjustment and fitting sample unresolved; exclude | Exclude |
| 48 | dporpag | Exact formula, baseline and fitting sample unresolved; exclude | Exclude |
| 49 | stops | Conditional reconstruction; current column unit unverified | Definition predates all three folds; source dependencies must pass |
| 50 | bpm | Original method predates 2018; Torvik version still unresolved | Original release in 2014 is later than 2012/13; exact 2014 cutoff unproved |
| 51 | obpm | Version, calibration and college adaptation unresolved | Exclude |
| 52 | dbpm | Version, calibration and college adaptation unresolved | Exclude |
| 53 | gbpm | Documented BPM2 formula is from 2020; exclude | Exclude; NBA fitting sample extends through 2015–16 |
| 55 | ogbpm | Later formula and unverified raw-variant mapping; exclude | Exclude |
| 56 | dgbpm | Later formula and unverified raw-variant mapping; exclude | Exclude |

The field-by-field machine-readable decisions include dependencies, remaining proof and source IDs in `field_decisions.json` and `field_decisions.csv`. `sources.json` records evidence dates and retrieval limits. All indices above are zero-based; raw index 45 is prohibited and was never inspected.

## What the primary sources establish

Ken Pomeroy's **September 21, 2005** college-statistics primer identifies ORtg with Dean Oliver's method. Basketball Reference's methods page dates Oliver's ORtg, DRtg and Stops definitions to his **2004** book and describes player, team and opponent box-score inputs. These methods precede the development folds. Their constants, possession conventions, historical denominators and exact correspondence to Torvik's raw columns still need verification. ORtg and DRtg are expressed per 100 possessions; the present raw Stops field's aggregation/unit has not been established. [Ken Pomeroy's primer](https://kenpom.com/blog/individual-stats-primer/), [Oliver ratings methods](https://www.basketball-reference.com/about/ratings.html).

Bart Torvik's **May 2, 2022** comment identifies internal `bpm` with original Myers BPM and `gbpm` with BPM2.0, while warning that some old statistics remain in the output. This supports a version distinction; it does not pin the current offensive/defensive subfields or college adjustments. His layout comment also cautions that 2008/09 can omit blank columns, so the later 67-column map must not be assumed for those years. [Torvik's author explanations](https://adamcwisports.blogspot.com/p/data.html).

Daniel Myers dates the original BPM release to **2014** and the revised method to **February 2020**. The revised regression uses four five-year NBA RAPM datasets spanning **1996–97 through 2015–16**; position and offensive-role estimates also use NBA samples. The parent supplied its existing primary-method retrieval for the calibration sections. The publisher's **February 25, 2020** announcement independently establishes the rollout. This audit has no original 2014 release day or raw HTML hash. [Myers's methods](https://www.basketball-reference.com/about/bpm2.html), [publisher announcement](https://www.sports-reference.com/blog/2020/02/introducing-bpm-2-0/).

A **2017** Torvik archive describes historical backfilling through 2008. It establishes that older seasons were reconstructed by then, not that the present formulas or values existed during the 2012–2014 folds. Original publication vintages remain distinct from season cutoffs. [Torvik's October 2017 archive](https://adamcwisports.blogspot.com/2017/10/).

## Next proof required

Start with ORtg, DRtg and Stops: obtain a fixed original definition and a source-specific mapping, then verify every required historical team/opponent/player denominator. If the current Torvik outputs cannot be tied to that implementation, calculate separately named Oliver features from permitted source facts. This is a conditional construction route, not permission to copy three raw columns.

For `porpag`, `adjoe`, `adrtg` and `dporpag`, obtain the author's exact player-level formula, replacement/usage/tempo conventions and calibration sample. Current team adjusted-efficiency descriptions cannot certify player index 29. For original BPM variants, pin the coefficient release, calibration endpoint and college adjustment before considering any later-cutoff use. GBPM remains outside the requested 2018 freeze.

The bounded audit used **12 web operations including three cached-page finds**. Two early searches were unproductive and a direct BPM page open failed; later primary search results supplied the method and announcement. Unrelated player-result snippets were ignored. Existing source lineage confirms identity/replay, but cannot certify rating formulas. The 41-column context and F50 source allowlists omit all 13 fields; that was checked without loading raw player values. Existing datasets and studies were unchanged.
