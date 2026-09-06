# Historical prospect-universe review and practical reconstruction plan

The original benchmark can be preserved while training candidates are rebuilt
from pre-draft records. That produces a **fixed retrospective ranking benchmark
with a separately reconstructed training universe**. It does not turn the
inherited benchmark into a complete or untouched draft-night population.

This review inspected source code, identity metadata, cached-source inventories,
the existing aggregate PID-pool audit, and official pre-draft eligibility
publications. It did not inspect WAR values, fit a model, or calculate a test
score.

## Confirmed construction risks

References below are to
`/Users/kennakao/Downloads/nba_redraft_handoff/reference_code/tabular.py`.

| Construction | Evidence | Consequence |
| --- | --- | --- |
| Some cohort years depend on later NBA debut | Lines 104–110 use `first_season - 1` for missing draft years of undrafted NBA players. | The year used to define a prospect's class can be learned after the actual eligibility event. Later pre-NBA professional seasons may then be attached to a retrospectively moved cohort. |
| Candidate selection can depend on eventual NBA participation | Lines 107 and 112–114 consult NBA season counts, actual selection status and career classification while building the population. | Selection is not demonstrated to be reproducible from draft-night evidence, even if those fields never become model features. The upstream players/timeline builder remains unavailable. |
| Known unsuccessful entrants are treated differently in training | Lines 48–91 add some non-withdrawing entrants outside the existing population and set eventual never-played outcomes. Lines 302–305 explicitly move declared-only training rows to `train_declared`; line 335 exports only `train`. | The exported training population omits a class of pre-draft candidates that remains in inference pools. NBA participation/selection history influences which training examples survive. |
| Outcome completeness controls train membership | Lines 300–301 move incomplete outcome windows out of `train`, then line 335 exports only `train`. | Later follow-up availability affects the frozen source training population. A later season-cutoff filter cannot recover candidates already omitted upstream. |
| Cohort assignment uses an unbounded last-college-season map in the supplementary entrant path | Lines 58–60 and 82 use each person's last timeline college season. | A later college return can affect whether a historical entrant matches. No explicit as-of filter appears in this path; actual contaminated memberships have not been enumerated. |
| Schema selection consults later inference cohorts | Lines 321–327 drop fields absent from all post-2018 inference classes. | Future input coverage influences the historical schema. This is distinct from reading test labels. |

The code comments expressly describe a training population of drafted players
and undrafted players who reached the NBA. It would therefore be inaccurate to
describe the 1,458-row training file as every historically eligible prospect.
It would also be inaccurate to claim every selection decision is future-derived:
the original code additionally permits college/international records, and its
upstream source-building logic was not recovered. The firm conclusion is that
membership **uses** later information and is not certified as-of.

The calendar broker repairs eligible label dates, not these earlier selection
decisions. Its present verified-NBA-season filter further limits usable labels
to players with documented NBA participation by each cutoff. That is a disclosed
observed-label subset, not a reconstruction of all pre-draft candidates.

## What can stay unchanged

The existing ID-only audit at
`work/calendar_broker/boundary_audit/pool_audit.json` establishes that all eight
original inference PID lists are preserved, including row order. The original
scored 2019–2025 benchmark has 392 drafted rows; 2026 remains prediction-only.
Those numbers describe the supplied benchmark, not every real NBA selection.

Keep its immutable PID/year manifest for comparison. Continue predicting every
original inference row, even when rebuilt features are entirely missing. The
independent scorer can use its already frozen drafted benchmark membership only
after predictions are frozen. It must require full coverage and never drop a row
because source matching, feature availability, or model confidence is poor.

For a complete prospect model, training membership should come from a separate
pre-draft eligibility registry. A simpler, valid alternative is a **historical
drafted-only training registry**: membership in an earlier actual draft is
already observable once that draft has occurred before the prediction cutoff.
That membership is not itself future leakage. Require every member of each
chosen earlier class, exclude pick values from model inputs, and censor label
availability independently. This models outcomes conditional on historical
selection, with a disclosed population shift when predicting a broader pool.

For the pre-draft registry, do not use membership in the fixed benchmark, actual
picks, eventual NBA IDs, future NBA participation, or career completeness to
decide who enters it.
Existing NBA IDs may be used as optional identity crosswalks, never as a
requirement for candidate inclusion or a numeric model feature.

Compatibility rows that cannot be verified in the reconstructed eligibility
registry stay in the original inference manifest with a provenance-gap flag
outside the feature matrix. They do not become evidence that the training
registry is complete. If a legacy non-drafted row has a retrospectively assigned
cohort, keep that compatibility mapping separate from its corrected eligibility
cohort rather than silently rewriting the benchmark.

One additional issue merits an explicit invariant: seed-rank averaging over the
entire legacy input pool depends on that pool's composition. Reference models
should use the same frozen input population. A deployment claim should additionally
test whether appending unrelated candidates changes existing scores/ranks and,
if necessary, use score calibration fitted on historical training data rather
than normalization based on a retrospectively selected inference pool.

## Available starting material and missing evidence

| Material | Current evidence | Appropriate use |
| --- | --- | --- |
| `datarebuild/identity/tabular_names.csv` | 2,560 existing prospects; 321 lack an NBA ID. | Legacy PID compatibility and identity crosswalks. Its membership is inherited, so it cannot seed a complete reconstructed cohort. |
| `~/nba/keys/player_key.parquet` | A broader 83,977-row identity key exists, with unique PIDs/source UIDs; 78,765 lack NBA IDs. It has no eligibility date field. | Recover source-ID aliases without restricting entrants to the 2,560 legacy identities. Its existence does not prove complete historical coverage or pre-draft publication. |
| `combine_raw/combine_YYYY.json` | 26 official cached years, 2000–2025; request year and every source row's season validated by the combine rebuild. | Independent combine-participant discovery and actual event-year features. Invitations/participation alone do not prove final draft eligibility or cover every prospect. |
| `tracking_raw/*.csv.gz` | 19 annual college-statistics files are present. | Candidate identity/statistics joins and a broader college player pool. A roster, class label or absence from a later roster is not by itself proof of draft eligibility. |
| `mock_raw/*.html` | 62 cached HTML snapshots. Several filenames visibly fall after the associated draft year/date. | Only source-verified pre-draft pages can supply discovery evidence. Mock inclusion is not a final eligibility decision; unverified/post-draft pages remain excluded. |
| Original `early_entrants.parquet` | Referenced by the handoff code but not located in the searched local trees. | Must be recovered or reconstructed with dated provenance; the flattened legacy rows are insufficient. |
| Automatic eligibility / final withdrawals | No complete year-by-year local registry was established. | Required before claiming all eligible prospects have been reconstructed. |

Official historical material is available to begin that registry. NBA's June 2018
release identifies remaining entrants and withdrawals before the draft.
[NBA final early-entry release](https://www.nba.com/news/forty-three-international-early-entry-candidates-withdraw-nba-draft-2018).
The 2017 announcement distinguishes NBA and NCAA withdrawal deadlines.
[NBA 2017 early-entry announcement](https://www.nba.com/news/nba-announces-early-entry-candidates-2017-nba-draft).

These examples demonstrate usable source types; they do not establish coverage
for every year. Eligibility rules and deadlines need contemporaneous year-specific
sources. Do not infer automatic eligibility merely from a current biography,
an eventual graduation date, a later NBA debut, or the latest version of a rule.

## Proposed builder: `build_predraft_universe.py`

Use a small explicit registry rather than rebuilding the missing monolithic
handoff pipeline. A practical first scope is the existing 2007–2018 training
window, with each incomplete year clearly marked. Start with well-documented
years to validate parsing; do not silently claim the remaining years are complete.

**Inputs, all versioned independently of NBA outcome files:**

1. `cohort_rules.json`: each year's pre-draft freeze timestamp, declaration and
   withdrawal deadlines, rule source, and permissible eligibility evidence.
2. `entry_events.csv`: source identity, cohort, declared/withdrawn/reinstated/final
   status, effective date, publication date, URL, source hash and extraction span.
3. `automatic_eligibility_evidence.csv`: documented eligibility basis, source
   dates and identity evidence. Unsupported college/international cases remain
   unresolved; they are not inferred from subsequent careers.
4. Source-specific identity tables and pre-draft rosters/statistics, using their
   stable source IDs. Legacy PID and NBA-ID aliases are optional separate maps.
5. Existing immutable inference PID manifests, held separately for compatibility
   checks and never consulted to select training candidates.

**Candidate construction:**

```text
for cohort in registered_training_years:
    freeze = rules[cohort].predraft_freeze
    evidence = records with publication_time <= freeze
    identity = resolve source IDs using evidence available by freeze
    entrants = latest confirmed entry status before freeze
    automatic = cases satisfying documented cohort-specific eligibility rules
    eligible = entrants still eligible at freeze UNION verified automatic cases
    unresolved = ambiguous identities, missing withdrawal status or missing rules
    freeze eligible/person_uid/cohort/source-evidence manifest before label join
```

Every candidate needs an attributable positive inclusion reason. Do not require
that the player eventually appears in the NBA, has an NBA ID, is drafted, has a
complete later career, or has usable model features. Do not remove a player by
looking up what he did after the freeze. Source gaps produce an explicit
`universe_partial` status; they are never silently equated with ineligibility.

Derive a stable `person_uid` from source identity resolution. Use an explicit
`(person_uid, eligibility_cohort)` observation key, keeping withdrawals and
re-entry history as dated events. Do not set cohort from NBA debut. Prevent the
same person appearing under different aliases in a training fold and its held-out
class, even when legacy PIDs differ.

**Feature construction:** left-join allowed raw pre-draft observations to this
frozen candidate table. Preserve candidates without measurements. Rebuild
college/context features from full eligible source-season pools, and use the
verified `vcmb_` sidecars or equivalent source-row joins. Do not seed the feature
scrape solely from the legacy 2,560 identities; that would reintroduce the old
membership restriction. Schema selection, imputation and scaling must use only
the relevant historical training fold.

**Labels remain a separate authority:** only after the candidate registry is
frozen, an as-of broker may attach outcomes from seasons ending no later than
Y−1 for a model predicting class Y. Preserve target observability/censoring and
follow-up metadata separately from predictors. Missing NBA IDs or absent source
matches do not prove a zero NBA outcome. Zero observed contribution requires a
complete as-of participation check; it must not be labeled a complete eventual
five-played-season career. The project's ordinal played-season target makes
delayed debuts and censored careers particularly important. This review does not
change that target or manufacture new negative labels.

## Bounded implementation sequence

1. Freeze the current original inference/benchmark manifests and source-only
   feature builders. Keep the old 42.5% result labeled uncertified.
2. Build a provenance-backed eligibility pilot for two or three well-documented
   historical years. Parse final entrant and withdrawal records, verify a bounded
   set of automatic-eligibility cases, and enumerate unresolved coverage.
3. Join those entries to the broader source identities and cached statistics.
   Report overlaps with legacy training PIDs and genuinely new pre-draft
   candidates using **identity counts only**. Do not examine NBA success to
   decide which new entries to retain.
4. Freeze and audit the resulting registry, then request a separate label-broker
   review. Only then run pre-2019 development comparisons with preregistered
   populations and censoring rules.
5. Extend year coverage after the pilot passes. Do not drop inconvenient test
   players or quietly replace the original benchmark while doing so.

Required negative checks: deleting all post-freeze source records leaves a
cohort byte-identical; perturbing NBA draft/career fields does not affect registry
membership or cohort assignment; future identity additions do not change old
joins; same-person aliases cannot cross train/test; missing features do not drop
candidates; and every original benchmark PID remains scoreable after prediction
freeze.

## Unresolved limits

This is a practical builder specification, not a claim that the full universe has
already been rebuilt. Missing original entrant records, incomplete automatic
eligibility evidence, international/older-year source coverage, identity
ambiguity, retrospective source vintages and first-played-season censoring remain
open. A combine-only or source-covered training population can be a useful
explicitly restricted experiment, but it must not be described as the complete
eligible population. The inherited benchmark has also been evaluated repeatedly;
population repair does not make it a pristine holdout.

## Calendar collection status at review completion

The separately authorized ESPN calendar collection finished at its 300-athlete
cap, using 728 of at most 900 requests. It produced 120 verified timelines, 97
partial timelines and 774 dated season-type participation records. The process
has exited; no caps were expanded. The aggregate final record is
`work/calendar_broker/calendar_extension/campaign_20260906/final_summary.json`.
The league calendar remains incomplete and no new records were automatically
promoted into the label broker. These later NBA participation records cannot be
used to define a historical pre-draft candidate universe.
