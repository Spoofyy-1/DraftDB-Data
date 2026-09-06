# Dated mock-rank extension, 2015–2026

This bounded source package adds **764 verified rank observations from 18 archived primary mock lists**. It contains 212 exact same-cohort player identities for 2015–2018 and 388 separate inference identities for 2019–2026. No model was trained or scored, and no draft results or NBA outcome fields were read for collection, feature construction, joining or verification.

The collector stopped at **42 network attempts**, below the 45-attempt limit. The original 2007–2014 consensus package and the R8s experiment were not modified by this work. All 54 original consensus public hashes still match. A read-only comparison against the original R8s prototype finds parent-owned revisions; these are reported in `verification.json` without changing them.

## Data files and joins

`features_training_2015_2018.csv` and `features_inference_2019_2026.csv` use the existing four numeric definitions: `vcons_mock_mean_rank`, `vcons_mock_best_rank`, `vcons_mock_rank_range` and `vcons_mock_n_sources`. There is one vote per publisher/player. Range is missing with only one publisher. Unlisted or unmatched players remain missing; their rank is never replaced with a bottom rank, zero or an actual selection.

`rank_observations.csv` provides per-fact source, cutoff, capture, table and rank-fact hashes. `publisher_ranks_eligible.csv` separates publishers; the serious David Kay route is identified as `walter_serious`, distinct from the quarantined canonical Walt route. `validated_sources.json` includes both eligible and quarantined attempts, while `metric_dictionary.json` defines the numeric fields.

The sidecars read **only `pid` and `draft_year`** from the original input files. They preserve the complete original identities and row ordering. All eight test identity sequences also exactly match the public site clone. No `was_drafted` filter is applied.

| Test year | Original rows | Rows with verified ranks | Explicitly missing |
| --- | ---: | ---: | ---: |
| 2019 | 137 | 51 | 86 |
| 2020 | 112 | 54 | 58 |
| 2021 | 233 | 46 | 187 |
| 2022 | 97 | 48 | 49 |
| 2023 | 101 | 48 | 53 |
| 2024 | 114 | 49 | 65 |
| 2025 | 106 | 47 | 59 |
| 2026 | 61 | 45 | 16 |

The training sidecar preserves all 1,458 original rows; 200 have extension ranks. The 2015/2016/2017/2018 intersections with the current model universe are 42/55/56/47. Twelve eligible source identities do not occur in the original training universe and remain excluded from that sidecar. These are **extension-only** sidecars: 2000–2014 cells are missing because this package adds 2015 onward. Join the frozen earlier source package separately rather than overwriting its existing values.

## Source rules and limitations

Every eligible source has an exact, nonredirected archive response before midnight America/New_York on the first draft date. Its target-year heading, explicit mock update date and complete table or known partial boundary are verified. Update calendar dates must also be strictly before the draft date. Publication date is unavailable and recorded as null; the archived availability proof and source update date are retained separately.

DX 2015–2017 and NBADraft 2015–2026 have 60 literal ordinal positions. Later NBADraft pages repeat a sticky first-round table: duplicates must agree on every rank/name/profile/field-presence fact. The 2022–2024 tables include explicit nonplayer forfeited-slot placeholders. Those placeholders are excluded from identities, and following ranks retain their literal mock positions without compression.

The serious Walter/David Kay sources for 2018–2020 are explicitly **partial top-15 lists**, with navigation marking the continuation at picks 16–30. Their lower-rank coverage is absent by design. The serious 2021–2023 archive route had no eligible index records. Coverage changes and partial lists constrain the meaning of source count and disagreement. This is a small dated rank pilot, not comprehensive final-market consensus.

Several snapshots are stale: NBADraft 2019 was updated in May; the Walter 2020 forecast was updated in September 2019; and the accepted 2026 snapshot is from May 8. The later June 23, 2026 snapshot was captured before the midnight-Eastern cutoff, but its update string says June 23 without a timezone. It is quarantined; the first draft date is correctly June 23, not June 24.

**Publisher-quality caveat:** the canonical Walter 2018/2019 pages explicitly describe themselves as fake/humorous mocks. They are quarantined, and only the separately linked serious David Kay pages are eligible in this extension. A read-only look at the frozen Walter 2007/2008 sources found humorous commentary, with no equivalent fake-mock notice; their dated rank facts were not modified here. Dates verify availability, not the forecasting quality of a publisher. All source-family testing should retain matched coverage controls.

Identity matching uses unique exact normalized names within the same draft year. No fuzzy matches, suffix substitutions or inferred aliases are allowed. The unmatched-name report preserves omissions for later independent identity work.

## Historical bio inventory

`historical_bio_inventory.json` counts fields present in the same archived player cells; it does not extract or certify numeric bio features. DX 2015/2016/2017 provides age, height, weight and position on 45/52/52 matched rows respectively; the 2017 extended table also exposes wingspan on 48 matched rows. NBADraft tables provide historical height, weight, position and class fields for matched players through 2026. DX 2015/2016 class data and Walter top-15 heading fields are inventoried where explicitly present.

Full archived bodies and isolated table bodies remain under `private/`. No current biography page was fetched. A future extractor should verify exact cell boundaries and numeric units before use; the inventory alone does not make those bio values eligible. Public deliverables contain factual rank data, source metadata and counts, without full article text.

## Verification and resumability

The collector reuses existing CDX indexes where available, logs every network attempt and rejects redirected captures. One NBADraft 2016 fallback response was fetched during a disk-full event but could not be saved; its single documented repeat is recorded in `recovery.json`. Requests now have a 500 MiB free-space guard, and metadata writes are atomic. A completion marker freezes further network requests for this bounded package.

`verify.py` replays all 764 matched facts from saved source bodies and tests eight malformed-boundary cases: truncated rounds, wrong years, ambiguous player links, conflicting sticky tables, missing DX blocks, changed DX column headings, truncated partial lists and a changed serious-source author. Cutoff and quarantine checks pass. `public_manifest.json` is the explicit publication allowlist and excludes all private source bodies. The package is ready for parent review and publication; it is not connected to any model runner.
