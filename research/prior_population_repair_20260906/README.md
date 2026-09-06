# Eight-member historical population repair inventory

This pilot keeps **all eight** previously corroborated missing 2012–2014
memberships. It is a source-join inventory and candidate-data package, not a
training run or an evaluation. Membership never depends on NBA participation,
feature coverage or label availability.

The combine reconstruction supplies 37 candidate columns, with **177 observed
values across all eight rows**. Every source is a cached official same-year
combine record joined by a previously corroborated player ID. The requested
season and every source row's season were checked. Missing measurements stay
missing; no current biography, researched fill, imputation, age or new NBA data
is used.

The combined feature candidate table now contains **185 columns and 652 observed
values across all eight rows**. These are repaired observations for this pilot;
they are not a claim of 185 newly discovered feature definitions.

| Feature family | Candidate columns | Members with observations |
| --- | ---: | ---: |
| Official combine | 37 | 8 |
| Historical college context | 41 | 7 |
| Verified predraft mock ranks | 4 | 6 |
| Archived mock profile fields | 10 | 6 |
| Source-reported Synergy figures | 74 | 5 |
| Fixed-lexicon report counts | 19 | 5 |

The combined table is a strict ID/year left join. It contains neither labels nor
private identity fields, and preserves missing values. One college name alias
remains uncorroborated and missing. A final college season one year before the
draft is carried only under the existing explicit one-year-gap policy. Historical
college release vintages remain unverified; dated mocks and scouting sources have
their existing archive/cutoff checks.

Two members have candidate historical WAR calendars containing **five actual
seasons in total**. All five corresponding original training WAR cells agree
with the historical RAPTOR source within 1e-5. The earlier calendar builder had
rejected these exact-name homonyms globally. Restricting the source to seasons
after the independently fixed cohort and through 2018 leaves one possible
calendar for each.

Those five records remain **quarantined**. An explicit cross-system NBA-ID to
RAPTOR/Basketball-Reference-ID bridge has not been independently verified.
Agreement with existing WAR is a consistency check, not independent identity
proof. The other six members have no accepted eligible WAR record in this
cache; their labels remain missing. No zero is inferred from absence.

## Model and data boundaries

- Canonical pilot row metadata is `candidate_id, draft_year`. Source IDs are
  inherited from the complete prior-draft registry, not generated from draft
  positions, NBA participation or labels.
- Broad-key PID, legacy model PID, names and NBA IDs remain separate in the
  private crosswalk. They are not candidate predictors.
- `data/combine_feature_candidates.csv` preserves all eight rows, including
  missing feature cells. `candidate_id` and `draft_year` are join/fold metadata,
  not numeric predictors.
- `private/label_candidates_through2018.csv` contains five reviewed candidates;
  it is not an approved model-label file. `private/approved_labels.csv` is empty
  by design. A worker must never receive this whole preparation directory.
- The cutoff inventory uses an explicitly stated December 31 information
  cutoff for prior membership and an independent NBA `season_end <= Y-1`
  label cutoff. It keeps actual season gaps and delayed debuts. It never computes
  a season as draft year plus ordinal.
- No 2019+ answer file is opened and no actual draft-order value is inspected or
  used. Numeric WAR is
  inspected only for the eight pilot identities, after selecting actual source
  seasons no later than 2018. Only matching prior ordinal cells are compared.
- This pilot does not alter the complete 180-member registry, source packages,
  existing training data, original inference pools or retrospective benchmark.

## Files

- `data/pilot_member_index.csv`: complete eight-member identifier/year index.
- `data/combine_feature_candidates.csv`: 37 predraft combine candidate features.
- `data/combined_feature_candidates.csv`: all 185 reviewed candidate features,
  with all eight source memberships retained.
- `data/combined_feature_manifest.json`: exact input/output hashes, field list
  and observed-cell counts for the combined table.
- `data/combine_feature_dictionary.json`, `data/combine_sources.json`: transforms,
  source columns, requested seasons and hashes.
- `data/coverage.json`, `data/manifest.json`, `data/validation.json`: aggregate
  inventory, scope and tests.
- `private/member_crosswalk.csv`: the reviewed source/broad/legacy identities.
- `private/combine_row_provenance.csv`: exact source row/ID joins.
- `private/join_inventory.csv`: per-member feature and label statuses.
- `private/label_inventory_by_cutoff.csv`: all eight members at each cutoff,
  including empty calendars and explicit missing-label status.
- `private/label_candidates_through2018.csv`, `private/label_provenance.csv`:
  quarantined candidate values and source/calendar provenance.
- `private/approved_labels.csv`: empty; no automatic label promotion.
- `features/`: completed cached Torvik/mock/scouting feature inventory, source
  evidence and eight feature-integrity tests; see its README.

Private metadata has directory mode 700 and file mode 600. The public allowlist
excludes every private identity, row-level NBA calendar, outcome and label file.
No publication has been performed.

## Concrete remaining repairs

1. Confirm the two cross-system label identities through an independent ID
   crosswalk or an authoritative source showing both identities. The matching
   historical values are already present; no new target definition is needed.
2. For the other six, obtain complete, dated NBA participation evidence through
   each historical cutoff using the known official IDs. A lack of records in
   one WAR source cannot establish zero production. Preserve missing status
   while evidence is incomplete.
3. Resolve source-feature aliases and publication-vintage limits independently
   of label values. Retain the entire pilot as the left side of each join.
4. Only after those reviews, assemble a separately frozen, per-cutoff training
   package with a documented missing-label policy. Do not repair a population
   by dropping members whose features or labels are inconvenient.

`model_ready` is false. This work supplies data-repair evidence, not an accuracy
claim. No model was fit, no benchmark was scored, and no network request was made
by the root inventory builder.

## Reproduction and validation

```sh
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_repair/build_inventory.py
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_repair/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_repair/assemble_features.py --feature-file work/prior_population_repair/features/numeric_feature_join.csv
```

Nine tests check future-source invariance, delayed debut and season gaps,
homonym rejection/disclosure, future cutoff rejection, missing-record handling,
full pilot preservation, identifier exclusions and the absence of automatic
label promotion. These checks do not fit a model.

The feature package's eight tests passed independently. Four assembly checks
passed: row-order invariance, rejection of a missing member, rejection of a target
column and preservation of the exact observed/missing-cell count.
