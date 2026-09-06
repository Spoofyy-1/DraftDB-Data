# Quarantined college candidate join

The35-column candidate projection preserves all1,458 canonical input PIDs and their exact order. The private augmented copy also preserves all539 original string columns unchanged.670 rows have15 consistent player-game candidates;624 have20 team-context candidates;623 have both. The119 existing college lineages outside this pool are not appended or name-matched. There are no new network requests, model fits, label reads or benchmark-result reads.

## Coverage

| Draft cohort | Full pool | Exact focal lineage | Player-game family | Team-context family | Both |
|---|---:|---:|---:|---:|---:|
|2000|70|0|0|0|0|
|2001|64|0|0|0|0|
|2002|65|0|0|0|0|
|2003|65|0|0|0|0|
|2004|66|0|0|0|0|
|2005|89|0|0|0|0|
|2006|78|0|0|0|0|
|2007|64|0|0|0|0|
|2008|64|44|44|41|41|
|2009|63|51|50|49|48|
|2010|71|56|56|54|54|
|2011|80|56|56|55|55|
|2012|77|56|56|52|52|
|2013|82|59|59|54|54|
|2014|84|62|62|56|56|
|2015|66|51|51|40|40|
|2016|89|69|69|64|64|
|2017|117|83|83|81|81|
|2018|104|84|84|78|78|

787 rows lack a verified focal college lineage; they remain entirely missing in both new families. One of671 intersecting player-game groups is quarantined by its source audit.47 team-context joins remain missing or quarantined. Missing values are never replaced with zeros. The separate1,428-row study pool has660 player-game joins and614 team-context joins; it does not replace the full pool.

## Temporal and identity conditions

Player-game joins use only the existing focal source season, exact Torvik source player id/team, anonymized source-subject key, annual row index and both frozen source hashes. The preexisting college context manifest agrees with the annual-file hashes used by the game package. A group must pass its original GP and six shooting-total checks; no parsed game can bypass that group quarantine. Candidate means are checked against the source group's direct totals and observedGP.

Team joins match the original PID/cohort, exact focal team/season, original college row and allowed-values hash. Their prior whole-season validation and minimum20 cached-game condition remain in force. Each family's minimum and maximum game dates must fit its source season, source season must not exceed draft year, and its last game date must be strictly before the registered draft date. These dates come from existing frozen mock/profile source manifests; no new calendar assertion is invented.

The player-game gate permits any historically earlier focal season; the frozen team package permits at most a one-year gap. In these actual joined player rows, source-year gaps are {0: 614, 1: 56}; there are no gaps greater than one year. The cohorts without college sources remain missing rather than receiving a season-convention substitute.

All candidates retain **model_eligible=False**. Historical event dates and deterministic arithmetic are established to the documented source checks; original publication/revision timestamps and complete schedules are not newly proved. The original source's credited-event discrepancies and DNP/minutes limitations remain. Parent review may separately authorize a bounded diagnostic; this join does not grant admission or certify inherited predictors.

## What differs from the existing41 source fields

All660 paired study rows have exact agreement for GP and the six shooting rates as GP-normalized existing shooting totals. Scoring rate also exactly equals(2×two-point makes+3×three-point makes+free throws)/GP. These eight fields are alternative representations, not new independent observations.

The new ORB, DRB, AST and STL averages differ beyond four-decimal rounding on58/660 paired rows; BLK differs on56. These are consistent source-subset recomputations. Direct TOV and PF use observed events where the current41 fields contain rounded rates or ratios; this is a measurement distinction, not a promise of predictive improvement. The20 team/opponent context fields describe events not present as team statistics in the current41 player-only columns. No outcome-guided feature ranking or selection was performed.

## Files and verification

- `candidate_inputs.csv`: public pseudonymous PID/draft_year plus35 numeric candidates, with every canonical row preserved.
- `private/full_pool_with_candidates.csv`: all539 original columns plus35 candidates; private and not allowlisted.
- `join_provenance.json`: local audit of exact hashed source lineage, dates and group validity; excluded from public delivery. `coverage.json` and `excluded_reasons.json` provide public aggregate reports.
- `overlap_with_source41.json`: fixed arithmetic/direct comparisons; actual_pick and was_drafted columns are excluded from its input projection.
- `input_pins.json`, `consumed_game_files.json`: source hashes. No original files were changed.

Seven essential tests pass: complete original-cell/order preservation, family missingness, actual and adverse cutoff dates, future-source removal, source-group/provenance/arithmetic tampering, hash and duplicate-key rejection, and explicit output schema. Removing all2015–2018 game source candidates leaves every candidate value for draft cohorts through2014 unchanged. The public allowlist excludes raw identities, source bodies, inherited input copies and private test logs.
