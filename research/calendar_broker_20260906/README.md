# Calendar-correct expanding broker prototype

The verified subset is implemented and prepared on the server. No model was fit,
no test score was read, and no running experiment, vault answer, or core research
script was changed.

| Predicted draft | Allowed season end | Latest verified label season | Training players | Dated labels | Complete source calendar through cutoff? |
| --- | --- | --- | --- | --- | --- |
| 2019 | 2018 | 2018 | 1,313 | 4,137 | Yes |
| 2020 | 2019 | 2019 | 1,418 | 4,467 | Yes |
| 2021 | 2020 | 2020 | 1,534 | 4,808 | Yes |
| 2022 | 2021 | 2021 | 1,627 | 5,151 | Yes |
| 2023 | 2022 | 2022 | 1,753 | 5,547 | Yes |
| 2024 | 2023 | 2022 | 1,753 | 5,547 | No: 2023 missing |
| 2025 | 2024 | 2022 | 1,753 | 5,547 | No: 2023–24 missing |
| 2026 | 2025 | 2022 | 1,753 | 5,547 | No: 2023–25 missing |

Counts include verified historical cohorts beginning in 2000. A frozen model's
chosen training-window filter must still be applied inside each worker. These
counts describe data availability, not measured predictive improvement. They do
not imply complete player coverage: ambiguous identities and eligible WAR
mismatches are excluded, with counts recorded in each manifest. Players with no
verified NBA season by the cutoff are excluded rather than assigned a zero based
on later career information. All original inference rows are retained; the frozen
scorer must select the complete original benchmark pool after prediction freeze.

The source publisher documents `season`, Basketball Reference player identity,
and combined regular-season/playoff `war_total` in its
[RAPTOR data dictionary](https://github.com/fivethirtyeight/data/tree/master/nba-raptor).
Both the historical and modern GitHub CSVs end in 2022. The publisher's advertised
2023 latest CSV now redirects to an unrelated HTML page, so it was rejected. The
handoff `prospects.parquet` has only flattened ordinal targets, not a season
timeline; it cannot supply the missing calendar.

## Paths

- Source and executable prototype: `work/calendar_broker/broker.py`.
- Adversarial checks: `work/calendar_broker/test_broker.py`.
- Aggregate-only results safe for the research data repository:
  `work/calendar_broker/aggregate_coverage.json`.
- Server prototype directory:
  `/home/ubuntu/nba/handoff/calendar_broker_prototype`.
- Prepared per-year bundles:
  `/home/ubuntu/nba/handoff/calendar_broker_prototype/bundles/YYYY`.

Each bundle contains input predictors, dated eligible labels, all inference rows,
and a manifest with provenance and SHA-256 fingerprints. The newer-cohort training
labels remain on the server; they were not copied into the public research repo.
Do not publish the complete broker source directory or all-year training bundles
alongside ordinary development model inputs. The code and aggregate audit can be
published separately.

## Boundary enforced by the implementation

1. For predicted draft Y, keep source NBA seasons ending at or before Y−1 before
   matching any identities. Use exact unique normalized names; ambiguous names
   are rejected. A future name collision cannot change an earlier match.
2. Assign each recorded NBA played season its ordinal. Preserve delayed debuts
   and gaps. Never compute `season_end = draft_year + ordinal`.
3. Consider only project identities from draft cohorts before Y. Open an earlier
   cohort's answer file only if its source calendar contains an eligible season.
   The answer file for Y or a later cohort is never opened, including for hashing
   or schema inspection.
4. Inspect only the existing ordinal WAR cells corresponding to those eligible
   dates. Require agreement within 1e-5 with the published RAPTOR value. Any
   eligible mismatch rejects that player's labels; later ordinal values do not
   participate in validation, identity selection, targets, or zero filling.
5. Export only verified eligible labels and declared predictors. Actual picks,
   rounds, player names, NBA identifiers, drafted flags, and outcome columns are
   absent from model predictors. PID and draft year are join/fold metadata and
   must never be offered to the predictor as numeric features.
6. Refuse an incomplete source calendar by default. The prepared 2024–26 bundles
   use an explicit partial-calendar flag and declare their older 2022 ceiling.
   They are conservative subsets, not complete expanding-data bundles.

`test_broker.py` passes adversarial checks for delayed debut, a missed season,
future-source and future-target perturbations, current-cohort exclusion, and
eligible mismatch rejection. Future perturbations leave the eligible calendar
and training-label data frames identical; source provenance hashes naturally
change when source files change.

## Integration before any expanding evaluation

Freeze the selected model, feature list, seeds, horizons, and benchmark pools from
development work. Do not select them by testing these prepared bundles.

Launch a **fresh worker for each predicted year**, with only that one year's
bundle mounted read-only. Mount the fixed model code and pretrained checkpoint
separately, and give it a fresh writable prediction directory. The worker must not
see this broker, its raw source files, the vault, the parent bundles directory,
another year's bundle, or an earlier process's fitted state/cache. Repeat the
existing namespace, network, forbidden-path, hash, and feature-column checks.

Write the year's prediction and manifest hashes before allowing the independent
scoring authority to read its answers. Preserve the full original drafted
benchmark pool; do not score only successfully source-matched players. Missing
calendar coverage constrains training only. 2026 remains prediction-only.

This prototype certifies label calendar boundaries, not all inherited feature
provenance or prospective model-selection purity. The existing benchmark has
already been repeatedly inspected historically. Do not call it an untouched
holdout.

## Completing the 2023–25 calendar

The next accepted source must give actual NBA participation by player and season,
covering both regular season and playoffs (a playoff-only debut must not disappear).
Prefer official NBA IDs, joined to the existing identity table, with source URL,
retrieval date, raw hash, and documented season convention. Append verified dates
to the historical calendar and reject duplicate/inconsistent seasons. Retain the
existing project WAR definition for those dates; newer reconstructed DARKO-based
WAR need not equal RAPTOR. The association between each later ordinal and its
actual season still needs proof from the joined complete season timeline.

Roster membership, a current `firstYear`/`lastYear` range, and draft year plus an
ordinal are insufficient evidence because they do not establish played-season
gaps. Do not promote partial 2022 bundles to complete expanding status merely by
changing the manifest cutoff.
