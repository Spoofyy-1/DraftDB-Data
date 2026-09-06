# Source-first historical eligibility pilot

This bounded pilot extracts factual entry/withdrawal records from six dated NBA
Communications releases for 2012–2014. Inclusion starts with the source lists.
No NBA ID, later NBA participation, career outcome, draft pick, legacy model row,
or successful identity match is required. No models or test scores were run.

| Draft year | Remaining early entrants in final release | Withdrawals | Initial-only unresolved name forms | Source-local registry IDs |
| --- | ---: | ---: | ---: | ---: |
| 2012 | 56 | 11 | 0 | 67 |
| 2013 | 60 | 18 | 2 | 80 |
| 2014 | 57 | 18 | 0 | 75 |

There are 372 factual source events and 222 source-local cohort IDs. These are
not 222 certified distinct people. The two unresolved 2013 initial name forms
are retained rather than silently merged with different spellings in the final
release. The initial/final aggregate totals also differ by one in 2012 and 2013;
the pilot does not invent a reconciliation.

## Files and source evidence

- `data/entry_events.csv`: normalized name, affiliation, source category, observed
  declaration/withdrawal/final-entry status, claimed availability date, URL,
  source-view line and capture hash. Exact individual filing/withdrawal dates
  remain null because the releases do not establish them.
- `data/eligibility_registry.csv`: status as of each year's final release date;
  positive eligibility requires an explicit final-list row. Initial declarations
  without a matched final decision remain unresolved.
- `data/identity_crosswalk_suggestions.csv`: optional exact normalized-name
  suggestions from `player_key.parquet`, reading only `pid`, `player_uid`, and
  `player_name`. Every suggestion requires identity review. There are 147 unique
  name suggestions, 10 ambiguous matches and 65 source-only IDs. None is removed.
- `data/draft_discussed_only.csv`: explicit empty schema for separately supplied
  dated mock discussion evidence. A mock does not confer eligibility.
- `data/manifest.json`, `data/coverage.json`: source hashes/dates, cohort rules,
  counts and unresolved limits. `data/leakage_checks.json` records bounded checks.

The primary final releases are dated [June 19, 2012](https://pr.nba.com/2012-nba-draft-early-entry-candidates/),
[June 18, 2013](https://pr.nba.com/early-entry-candidates-withdraw-2013-nba-draft/),
and [June 17, 2014](https://pr.nba.com/2014-nba-draft-withdrawals/).
The corresponding initial releases establish the withdrawal deadlines:
[2012](https://pr.nba.com/entry-candidates-2012-nba-draft/),
[2013](https://pr.nba.com/nba-early-entry-candidates-2013-nba-draft/),
[2014](https://pr.nba.com/2014-nba-draft-early-entry-candidates/).
The 2012 initial list is linked as an attachment and was not collected.

A direct HTTP request returned 403 and was not retried. The accessible primary
page text views supplied by the web tool are stored only under `private/`.
Their SHA-256 values identify that exact retrieved representation, **not** raw
HTTP HTML. Retrieval/observation happened in September 2026. Historical
availability relies on the NBA publisher's old datelines; no independently dated
archive snapshot was recovered. Full page bodies and additional biographical
columns are excluded from the public allowlist.

## Limits before training

This is a complete extraction of the named early-entry sections in the three
final releases, not a complete draft-eligible universe. Seniors and other
automatically eligible candidates remain uncollected; 2007–2011 remains outside
this pilot. A final-list status means the NBA listed the candidate as remaining
at that release date after its withdrawal deadline. Later corrections or
eligibility changes between that date and draft night have not been collected.
The registry cutoff is consequently the release date, not draft night.

Source-local candidate IDs include the observed cohort, category and normalized
name. They are not global person IDs. Resolve aliases and homonyms using dated
source identity evidence before joining features/labels or preventing the same
person from crossing folds. Exact name equality in the broad key is only a
suggestion and never certifies identity. Missing NBA evidence is not a zero
outcome. Label eligibility, actual season dates and censoring must be handled
separately after the candidate registry is fixed. `model_ready` remains false.

The simpler fallback is a **historical drafted-only training registry**. For
prediction year Y, membership of an earlier draft class can be used once that
draft's result date is before the configured information cutoff. Retain every
member of each selected class, exclude pick values from features, and censor
unobserved outcomes independently. This differs from filtering by future NBA
participation and is not itself future leakage. It trains conditional on prior
selection and requires disclosure when predicting a broader prospect pool.
NBA season-label cutoffs and source-publication cutoffs should be separate
explicit rules; a prior season ending before its subsequent draft does not
automatically authorize that draft's membership at that earlier date.

For either approach, preserve all original inference rows and the original
392-row scored 2019–2025 benchmark outside the model. A reconstructed training
registry must not silently shrink the benchmark. The complete original
benchmark is a fixed retrospective population; it is not proof that every
historically eligible player was included.

## Reproduction and bounded checks

From the workspace root, using the existing pandas/pyarrow environment:

```sh
work/.venv/bin/python work/verified_eligibility/build.py
python3 work/verified_eligibility/test_build.py
```

The builder is offline and needs the private captured source views plus the
identity key. Public factual CSVs, their hashes and source URLs remain available
without redistributing those views. Eight tests cover unresolved declarations,
withdrawal timing, future-record invariance, missing identity preservation,
ambiguous names, NBA-ID independence, contradictory records and exact section
counts. The cached-source test skips when private views are absent.

`PUBLIC_ALLOWLIST.json` is exhaustive. Nothing under `private/`, no broad identity
key, and no outcome/calendar collection should be published with this pilot.
