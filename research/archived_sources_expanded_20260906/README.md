# Archived draft report pilot

This is a source-validation package, not a model result. It contains factual statistics and deterministic text counts from contemporaneous draft reports. No NBA outcome files or test scores were accessed; no models were trained or selected here.

The combined historical pilot has 217 players, 2,787 observations, and 100 metrics across 2007–2014. These are 74 numerical Synergy metrics, 19 text metrics, and 7 older camp/agent reporting metrics. They are not 100 entirely new, independently validated predictive signals. Sparse fields remain missing.

## Files to integrate

| File | Content |
| --- | --- |
| `synergy_features_eligible.csv` | 111 players, 74 numerical Synergy metrics; excludes camp/agent fields |
| `text_features_eligible.csv` | 114 players, 19 deterministic report-text metrics |
| `features_eligible.csv` | All 217 historical players and all 100 metrics |
| `observations_eligible.csv` | Fact-level source URL, archived capture, publication date, evidence hash, units and extraction method |
| `metric_dictionary.json` | Units, denominators, family and missing-value rules |
| `coverage_controls.csv` | Family availability and observed-field counts for experimental coverage controls |
| `nba_text_features_eligible.csv` | Separate inference pilot: one verified report per year, 2019–2026; 8 rows, 19 text metrics |
| `nba_observations_eligible.csv` | Provenance for the 152 inference-pilot text observations |
| `source_manifest.json`, `nba_validation.json` | Source-level validation evidence |
| `public_manifest.json` | Explicit publication allowlist and file hashes |

`numeric_features_eligible.csv` includes camp/agent fields as well as Synergy. Use the Synergy-only file for the new numerical family test. `observations_candidate.csv`, unreviewed candidates and quarantined files are not eligible inputs. All article bodies, HTML, embedded page JSON and extraction contexts are private under `private/` and must never be included in the public data repository.

## Coverage at the development model cutoffs

Counts are exact pid matches against the identity roster. Recheck their intersection with each actual model input matrix during integration. The table counts players with at least one numerical value, then players with a value in a column also observed in that fold's training data.

| Validation draft | Training draft cutoff | Numeric training players | Numeric validation players | Validation players with training-observed column | Text training / validation players |
| --- | --- | --- | --- | --- | --- |
| 2012 | ≤2010 | 29 | 9 | 8 | 28 / 10 |
| 2013 | ≤2011 | 49 | 20 | 20 | 39 / 26 |
| 2014 | ≤2012 | 58 | 33 | 33 | 49 / 39 |

The folds have 15, 13 and 14 numerical metrics respectively that overlap training and validation observations. Many of the 74 total numerical fields are too sparse to learn reliably. `family_coverage.json` records exact observation and feature counts.

Use the corrected baseline with its existing folds, random seeds, outcome-season cutoffs and complete-class scoring denominator. Test numerical values, text values, and their joint addition separately. Include matched missingness controls: the same per-column observed/missing masks without the measured values, plus the supplied family-presence and count controls. Recompute count controls after any fold-specific column filtering. A gain driven by report availability alone does not establish value in the underlying statistics. Do not restrict scoring to covered prospects.

## Historical evidence and extraction rules

Twelve new DraftExpress archives passed validation for 2011–2014, with three earlier Synergy articles reused for 2009–2010. Original publication dates and exact historical archive captures must both precede midnight America/New_York on the first draft day. This deliberately excludes all draft-day daytime captures. The archive replay URL must match the requested snapshot without redirecting to a newer page.

The article body is the balanced outer font block after the dated headline, excluding navigation, player profile sidebars, Feedback and Read Next. This matters because a nested image-caption font previously truncated one 2012 article. For 2009–2010, extraction begins at Findings to exclude introductory retrospective comparisons with older NBA cohorts. Player sections require an exact same-cohort identity match; paired subjects and ambiguous attribution remain quarantined.

Numerical candidates are discovery aids only. Promotion requires manual source-context and denominator review, or explicit manual transcription checked against the archived article. Points per possession and points per shot remain separate. Jump-shot share of shots and jump-shot share of possessions remain separate. Some 2012 efficiency units follow the article's local scoring context rather than a unit repeated beside every number. Forty-three unreviewed candidates and one conflicting player/metric value remain excluded.

The text family is word count plus 18 fixed lexicon frequencies per 1,000 words. It measures topic coverage; it is neither sentiment nor an LLM-generated player grade. Lexicons and section hashes are public, but the copyrighted section text is private. There is no claim that text measures improve prediction before the development ablation.

## Inference pilot and the 2026 cutoff correction

Eight NBA-hosted reports were validated, one from each 2019–2026 class. For 2019–2020, extraction uses the unique Drupal report-body subtree. For 2021–2026, only `prospect.contentText` is allowed; season and display-name identity are checked, and any assigned draft round, pick or team causes quarantine. Navigation and other embedded metadata never become features. NBA publication timestamps are unavailable, so they remain null; the historical archive capture proves the report existed before the cutoff.

The 2019–2022 probes credit Synergy. The 2023–2026 probes are general NBA-hosted scouting reports, so numerical Synergy attribution is not claimed. This is only eight validated inference rows, not class-wide coverage. CDX discovery indexes provide a resumable continuation path; index hits are not yet eligible reports and may include duplicate or unsuitable URLs. A separate 2020 `stats.nba.com` prefix index yielded nine discovery URLs; none have been promoted.

The identity calendar originally used June 24 for the 2026 draft. The [NBA's announcement](https://pr.nba.com/2026-nba-draft-early-entry-candidates/) gives June 23 for round one and June 24 for round two. The universal pre-draft cutoff must use June 23. A probe admitted by the later date contained assigned draft metadata and was fully quarantined. Its replacement is a May 27 capture. `cutoff_overrides.json` records the correction; the main collector calendar must also be corrected before integration.

## Resume and reproduce

Run `discover.py` and `collect.py` to resume the bounded DraftExpress source collection. Existing source records are skipped; blocked or late sources remain quarantined. `repair_bodies.py` rebuilds bodies from already saved HTML with the same balanced parser and requires no network request. Run `extract.py` to generate candidates and deterministic text counts, review new numerical candidates into `numeric_review.json`, then run `finalize.py` and `package.py`. Candidate review must not be bypassed to increase coverage.

For the NBA pilot, run `discover_nba.py`, `collect_nba_pilot.py`, `validate_nba.py`, then `package.py`. The current collector intentionally fetches only one matched report per year; expand its queue deliberately for a full coverage run. All collection scripts use public archive endpoints with bounded concurrency and resumable local state. Scripts currently expect the shared `work/collectors/players.json` identity roster and the earlier pilot files one directory above.
