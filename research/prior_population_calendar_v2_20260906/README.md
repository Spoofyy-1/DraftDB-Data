# Private historical population calendar candidate v2

The new pilot preserves all **eight** repaired 2012–2014 memberships, with
185 candidate features and **693 observed feature values**. One independently
verified name alias adds 41 historical college values. Every other member and
feature cell matches the preceding candidate package.

Two cross-system identities were revalidated against the raw official combine
records, the exact published NBA/Basketball-Reference ID pairs, pinned entity
revisions and distinct father identities. Five existing historical seasonal WAR
cells were checked only after identity approval; each agrees with the unchanged
original training value. The source definition remains historical RAPTOR WAR,
including the existing combined regular-season/playoff measurement.

The published Wikidata NBA-ID statements have no attached reference. The audit
records this limitation and separately verifies the IDs against official combine
data. No current birth date, measurement or other biography value becomes a
predictor. The historical college table's original release vintage remains
unverified, as in the preceding source-only feature package.

The six other memberships still lack verified eligible NBA/WAR records. They
remain present, with missing labels. No missing record is converted to zero,
and membership is never chosen using NBA participation.

## Cutoff-specific candidate bundles

For predicted draft Y, each private bundle contains only memberships from earlier
cohorts whose recorded availability date is no later than December31 of Y−1.
Seasonal labels are independently restricted to actual `season_end <= Y−1`.
The preparation directory contains later-cutoff candidates and private identities;
it is not a model sandbox. Any later worker must receive only its selected
cutoff's reviewed files and explicit feature allowlist.

| Predicted draft | Allowed NBA season end | Prior members retained | Eligible seasonal labels | Members with labels |
| --- | ---: | ---: | ---: | ---: |
| 2013 | 2012 | 2 | 0 | 0 |
| 2014 | 2013 | 5 | 1 | 1 |
| 2015 | 2014 | 8 | 3 | 2 |
| 2016 | 2015 | 8 | 5 | 2 |
| 2017 | 2016 | 8 | 5 | 2 |
| 2018 | 2017 | 8 | 5 | 2 |
| 2019 | 2018 | 8 | 5 | 2 |

These counts describe a bounded population repair. No model has been run, no
2019+ test outcome has been read and no accuracy improvement is claimed.

## Horizon and maturity semantics

The pilot exposes horizons h=1…5 explicitly. A target summing the first h recorded
NBA seasons is complete only when all h seasonal records are observed by the
cutoff. Elapsed calendar years alone do not establish that condition. A person
with three observed NBA seasons is not silently assigned two additional zero
seasons to complete h=5.

`targets_by_horizon.csv` separates:

- The count of eligible, actually observed seasons.
- Calendar years elapsed and whether the calendar horizon has passed.
- Whether the first-h-observed-season horizon is complete.
- A complete-horizon target, missing until completeness is established.
- The observed partial sum, missing when no eligible record exists and explicitly
  marked as a censored observation when the full horizon is incomplete.

Observed partial sums are not automatically substituted for complete-horizon
targets. This explicit target view is for review; it does not silently change an
existing model's objective or the benchmark measurement. Any later training
must declare its horizon/missingness policy and use only permitted observations.

## Private files

- `private/features_master.csv`: all eight source memberships and 185 predictors.
- `private/feature_alias_provenance.json`: the one exact identity-supported college
  repair, source row/player ID, source hash and unchanged-cell checks.
- `private/approved_identity_metadata.csv`: two independently rechecked identities.
- `private/approved_calendar_metadata.csv`: five actual season/ordinal records
  approved as metadata for this candidate version.
- `private/verified_season_labels_through2018.csv`: the five verified historical
  values; labels remain separate from predictors.
- `private/unresolved_members.csv`: all six still-unresolved label memberships.
- `private/label_provenance.csv`, `private/source_pins.json`: source definition,
  value consistency and unchanged original-input hashes.
- `private/cutoffs/predict_YYYY/`: `features.csv`, `eligible_season_labels.csv`,
  `label_status.csv`, `targets_by_horizon.csv`, `joined_pilot.csv` and a manifest.

The joined table is a review artifact containing predictors and explicitly named
`y_` target columns. The manifest lists the 185 permitted predictors; metadata and
target columns are never predictors. Prefer the separate feature/season-label
tables for any later worker implementation.

All identity, feature, calendar and label files remain private. Private directories
have mode700 and files mode600. The five-file public allowlist contains only this
report and aggregate verification. No publication has been performed.

## Minimal honest incorporation path

1. Preserve the complete source-defined membership index as the left side of all
   joins; this pilot contributes eight repaired rows without availability-based
   membership filtering.
2. Use the two approved identities and their observed season labels only inside
   the appropriate historical cutoff. Keep incomplete horizons explicit and
   choose a documented objective before model fitting.
3. Obtain dated participation/label evidence for the six unresolved members.
   Until then, the population repair is partial; do not claim that all missing
   historical members have become fully labelled training cases.
4. Rebuild and validate a new isolated candidate bundle. Keep the old studies,
   frozen inputs and original retrospective test pool unchanged. Test this
   population repair independently of unrelated model changes.

No production bundle, calendar, model, original source or cache was modified.
No model fitting, benchmark scoring, network request or automatic promotion was
performed. `model_ready` remains false.

## Reproduction and checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_calendar_v2/build.py
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_calendar_v2/test_build.py
```

Nine tests pass: earlier-cohort and cutoff enforcement, invariance to changed or
added future season values, preservation of six unresolved members, separation
of elapsed time from complete observed horizons, explicit partial-sum handling,
the exact single 41-field feature repair, mismatched cohort/duplicate identity
rejection, and unchanged original sources with no identity predictors.
