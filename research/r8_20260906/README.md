# DraftDB: run review and next experiments

Audit date: 6 September 2026. Target: mean order correlation (Spearman × 100) of at least 60%, using the existing WAR definition. This report does **not** claim that target has been reached.

## Agreed timing rule

For predicted draft class Y, training can expand into earlier cohorts, but may use only NBA seasons ending no later than Y−1. The predicted cohort and its outcomes cannot enter fitting. Its actual draft order cannot be a model input. The user explicitly permits retrospectively reconstructed WAR measurements of eligible historical seasons.

The 2019–2025 results are a repeatedly inspected benchmark, not an untouched holdout. The historical dashboard displayed thousands of scoring calls. Sealing files prevents modification; it does not reverse information gained from examining test results. A 2026 board must remain unscored until suitable outcomes exist.

## What was reviewed

The inventory covers 33 structured run/lineage files in rounds 5–7, including archived islands, current lineages, the overnight sweep, and all available structured panels. There are 2,919 raw records, including mirrored lineage/run entries and archived copies. Exact record deduplication leaves 1,895 distinct exported records; this is **not** a count of independent experiments. The panel comparison table contains 158 completed comparisons.

Configuration and development metrics were exported. Blind scores and per-player test outcomes were omitted from the research inventory. Scores from different data versions, fold sets, fitness objectives, and target timing rules must not be pooled into one ranking.

## Historical successes worth preserving

These are recorded validation improvements under their original protocols, not newly verified causal effects under the corrected cutoff.

| Change | Recorded development evidence | Decision |
|---|---|---|
| Coverage-dependent ensemble weights | Overnight +1.09 correlation points, 4/5 folds; accepted in several lineages | Recheck with weights selected independently of scored folds |
| Coverage weights with horizon-specific models | Overnight +1.71 points, 4/5 folds | Retain the hypothesis; correct calendar censoring first |
| Regularized ridge member | Overnight +0.80 to +2.47 points across four alphas, although each failed the fold gate; later ridge-300 lineage mutation accepted at +1.17 | Strongest repeated model-family direction; exact alpha remains uncertain |
| Shooting plus production interactions | Main archived lineage accepted at +0.60 points | Preserve a compact, interpretable group |
| Training back to 2007 | Current main lineage gen11 accepted at +1.99 points | Broader data can help; earlier than 2005 has very different coverage |
| TabICL settings / residual quantile blend | Main lineage accepted several setting changes; q25 + residual mutation +1.03 | Keep as comparison candidates, not proof of a universal optimum |

## Which optional data helped or hurt

Values below are changes in validation correlation ×100, within the stated panel's original baseline. A failed gate can mean insufficient evidence rather than harmful data.

| Block / change | Recorded change in points | Interpretation |
|---|---:|---|
| Broad Torvik block | −1.18 | Hurt this stack; many redundant or sparse features |
| Rule-based text counts | −0.78 | Negative; leave disabled initially |
| Birth / prep / hometown misc block | −1.09 | Negative; little reason to prioritize it |
| All optional blocks together | −1.20 | Adding every available feature did not help |
| All optional blocks plus top weighting | −1.33 | Additional weighting did not rescue the broad merge |
| Wikipedia attention | −0.14 | Nearly flat, not a demonstrated edge |
| Google Trends | −0.11 | Nearly flat despite 5/7 fold wins |
| Mock momentum | −0.04 | Nearly flat; the reported historical training coverage is 0% |
| Recruiting RSCI extension | −0.51 | Negative in this panel; overlaps existing pedigree information |
| Trajectory | +0.28 | Small positive, only 2 fold wins; promising enough to isolate, not adopt |
| Team-season context | −0.26 | Broad existing team block did not pass |
| Program pipeline | −0.22 | Weak and has additional target-timing risk |
| 2000 / 2003 window | −2.67 / −2.36 | Early-era coverage hurts; 2003 was −2.96 in another panel |
| Class-relative normalization | −1.59 | Removing absolute statistical levels hurt |
| Position-relative normalization | −1.26 | Did not pass on the later panel |
| Pairwise member | −0.39 | Did not help the existing ensemble |
| Pairwise plus fitted meta weights | −1.27 ridge / −1.15 NNLS | No support from these completed panels |

The combine/spline and later queued experiments have no completed structured results in this inventory. They must be marked **unfinished**, not failed. Several panels ended before testing their complete configured candidate lists.

## Evaluation defects found

1. **Played-season ordinals were mistaken for calendar years.** The source builder creates `y_s1`, `y_s2`, etc. by counting NBA seasons present in the player's timeline. The old expanding and walk-forward functions truncate using `draft_year + ordinal`. Delayed debuts and missing seasons invalidate that arithmetic. Matching the historical RAPTOR source dated 4,984 existing training labels. Of these, 630 labels across 275 players occur later than the arithmetic assumes. This is a count of potentially mistimed labels, not a count of confirmed contaminated model fits.
2. **The vault was imported into the training process.** Importing the old vault eagerly loads all answer files. Its `expanding_rows()` also returns individual outcomes. This does not match the module's claim that only aggregates leave the vault. Path scans and a hash manifest do not create a process security boundary.
3. **Some stack weights were fit on the same folds used to report fitness.** The rank-average branch calls `learn_weights(g,F)` and then scores those same folds using the chosen weights. Other meta branches exclude a fold but can use later fold years. Neither is a fully chronological nested evaluation.
4. **Global target normalization can cross fold boundaries.** The `zseason` label option uses means and standard deviations computed from the full training pool at module load. Any active use must estimate these within each fit.
5. **Some feature provenance is unresolved.** LLM-extracted scouting grades need dated report/source validation. Program and coach features use retrospective outcome totals with the same nominal-season assumption. Current Wikipedia infoboxes and retrospectively collected season tables require careful distinction between a historical fact and a historical source snapshot.
6. **No fresh holdout can be recovered by renaming files.** The proposed confirmation years were used in earlier work. They are a one-time confirmation within the new bounded experiment, not historically untouched data.

## Data prepared for the next experiment

The calendar audit matched 1,428 of 1,458 training players to a unique normalized source identity, then verified available ordinal WAR against the existing labels. Thirty unresolved identities or mismatches are recorded and excluded rather than assigned invented zero outcomes. The exported research dataset contains 963 matched, drafted players and 3,195 season-label rows ending by 2018.

The new college builder generated 71 features for 790 pre-2019 prospects from local Torvik season tables. It rejects stale or ambiguous name/player-ID matches, excludes future college seasons, and never reads Torvik's NBA-pick field. Feature groups include:

- Teammates' minutes-weighted usage, efficiency, passing, rebounding, and defensive activity, excluding the prospect himself.
- Number of competing creators and rotation players, to distinguish constrained opportunity from lack of ability.
- Changes in role, minutes, usage, passing, turnovers, shooting, and team affiliation.
- Skill combinations such as defensive activity relative to fouls, passing relative to turnovers, and free-throw skill with volume.

The first comparison retains a compact legacy baseline with college box scores, combine measurements, pre-draft consensus, recruiting, and international production. It explicitly compares removing market and international features. Broader optional features are tested in small groups. LLM scouting grades, globally learned projections/percentiles, and outcome-derived program/coach fields are excluded.

These choices make the experiment stricter but also mean its scores are not a like-for-like reproduction of the old champion. Legacy baseline feature provenance remains an inherited limitation; “calendar-safe” is not a blanket certification of every collected feature.

## Registered experiment

Sixty-three fixed configurations compare ridge, XGBoost, ExtraTrees, CatBoost, and a small TabICL set. Development uses 2012–2014. The selected single model or fixed equal-rank blend is frozen before a single confirmation on 2015–2017, with a different random seed. No 2019–2026 inputs or outcomes are mounted into the worker; its network is disabled. Preprocessing is fit only on each training frame.

For fold Y, training labels are filtered by actual season ending ≤Y−1. Recent cohorts can have censored observed prefixes; no later outcomes are filled in. The development score uses observed first-k played-season WAR known by 2018, with `k=min(5,2018−Y)`. It is explicitly a **pre-2019 development metric**, not the final 2019–2025 test score.

The next priorities after this comparison are a corrected reproduction of the incumbent, historical consensus coverage before 2005, better dated international production, and source-verified shot-creation/role evidence. The 60% target must be established by a frozen-model evaluation, not by selecting the highest result from repeated test evaluations.

Source for calendar matching: [FiveThirtyEight historical RAPTOR data](https://github.com/fivethirtyeight/data/tree/master/nba-raptor). Existing-method reference: [DraftDB methods](https://github.com/Spoofyy-1/draftdb/blob/main/docs/METHODS.md).

## Reproduce the prepared research run

Use Python 3.12 with NumPy, pandas, SciPy, scikit-learn, XGBoost, CatBoost, and TabICL. The supplied `data/` files are sufficient for `python research.py`; it refuses to overwrite an existing registered run. A local TabICL checkpoint is needed for offline runs. `run_sandbox.sh` documents the deployed server isolation; adapt its installation paths for another machine.

To rebuild the calendar sidecar, download the RAPTOR CSV at the source URL in `calendar_audit.json`, verify its SHA-256, then run `python build_calendar.py --source RAPTOR.csv --identity ../../identity/tabular_names.csv --train train_source.csv --output .` (use the actual identity filename). Run `python build_context.py`, then `python prepare_data.py`. Source snapshots contain later outcomes for old training cohorts; only the filtered `data/` directory is exposed to the worker. `actual_pick` remains metadata for the benchmark and is expressly excluded from fitting.
