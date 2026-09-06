# Historical drafted-only registry: 2012–2014 pilot

The registry contains **all 60 selected players in each of three prior drafts**,
180 memberships total. Inclusion starts from complete contemporary draft-result
lists and never requires an NBA ID, NBA participation, a legacy model row,
feature availability or outcome availability. No outcomes were inspected, and
no model was fit or scored.

For prediction year Y, a membership is usable only when `draft_year < Y` and
its recorded availability date is no later than the explicitly configured
information cutoff. The NBA season cutoff for labels is a separate rule.
Historical selection membership can therefore be known without revealing the
current prediction class's selection order or career outcomes.

## Sources

Canonical lists are the complete draft-night reports by Hoops Rumors:
[2012](https://www.hoopsrumors.com/2012/06/2012-nba-draft-results.html),
[2013](https://www.hoopsrumors.com/2013/06/2013-nba-draft-results.html),
[2014](https://www.hoopsrumors.com/2014/06/2014-draft-results.html).
Each of their 60 numbered selections is crosschecked against Associated Press
draft-night records syndicated by [TheSpread for 2012](https://www.thespread.com/nba-news/sp-2041481404/),
[CT Post for 2013](https://www.ctpost.com/sports/article/2013-nba-draft-selections-4632115.php),
and [Fox News for 2014](https://www.foxnews.com/sports/2014-nba-draft-team-by-team).

All six lists contain every ordinal from 1 through 60 exactly once. The 2013
Hoops Rumors article numbers round two 1–30; the parser uses that explicit round
to obtain overall selections 31–60. Team descriptions sometimes refer to the
recipient after a trade; team fields and trade commentary are not exported.
There are ten normalized-name disagreements between the paired sources.
Variants and possible source typos remain visible for review, not silently
rewritten. For example, AP's 2012 syndication prints `Kyle Quinn` while the
independent contemporary list gives `Kyle O'Quinn`.

Primary NBA history URLs and several live syndicated pages could not be
retrieved. CT Post's AP article was directly available through a web-tool page
view; the other five complete source texts were available in the web tool's
indexed results. The manifest distinguishes those representations. Hashes
identify retrieved text, not raw HTML. Historic availability relies on publisher
datelines; independent archival snapshots were not recovered. The 2014 AP
syndication also shows a 2015 update, so the 2014 availability date relies on the
separate contemporary Hoops Rumors report. These source limitations do not
authorize filling missing records from current biographies or NBA outcomes.

## Outputs and model boundary

- `data/membership_registry.csv`: all 180 source memberships, names, dates and
  provenance status. Metadata only, not a numeric feature matrix.
- `data/source_name_variants.csv`: names appearing in the paired result records;
  variants are candidate identity evidence requiring review.
- `data/identity_crosswalk_suggestions.csv`: optional links to the 83,977-row
  broad identity key and same-cohort legacy identities. Only `pid`, `player_uid`,
  `player_name` and `draft_year` are read as applicable. No legacy actual-pick
  field or NBA ID is consulted.
- `data/training_population_gaps.csv`: every selected member without a uniquely
  matched existing training row, including unresolved spelling cases.
- `data/model_row_index_2015.csv`: an example identifier-only index as of
  2014-12-31. It has all 180 rows and only `candidate_id` and `draft_year`.
- `protected/actual_draft_positions.csv`: actual positions and source row
  locations, kept outside both the public allowlist and model row index.
- `data/manifest.json`, `data/coverage.json`, `data/leakage_checks.json`: sources,
  hashes, counts, scope and bounded validation.

Candidate IDs hash the observed canonical name and cohort year, never the pick.
The model row index is sorted by candidate ID, not draft order. Downstream
feature building must left-join onto that full index and keep missing rows;
identity resolution and observed-label censoring are separate stages. Neither
the metadata directory nor `protected/` belongs in a model sandbox.

| Year | Source memberships | Unique legacy-name suggestions | Other broad-name suggestions | Unresolved identity suggestions | Existing training candidates matched |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2012 | 60 | 56 | 1 | 3 | 55 |
| 2013 | 60 | 49 | 4 | 7 | 48 |
| 2014 | 60 | 55 | 2 | 3 | 53 |

The apparent gap list is **not a count of confirmed missing people**. Names-only
matching deliberately leaves unresolved cases. In 2013, the source names
`Dennis Schroeder`, `Glen Rice Jr.`, and `James Ennis` have plausible same-cohort
legacy variants `Dennis Schroder`, `Glen Rice`, and `James Ennis III`; those
suggestions are documented but not automatically certified. Likewise, a source
selected player can exist in the legacy cohort with an incomplete selection
flag. Consequently these name-match counts need not equal prior counts of
nonmissing legacy actual-pick fields. The source-derived roster, not those
counts, determines complete membership.

## What remains unresolved

Global identity links need independent verification, especially aliases,
homonyms and multiple source identities in the broad key. No candidate is
discarded while that work is pending. Missing NBA evidence is not proof of a
zero career outcome. Label calendars, censoring, historical feature joins and
cohorts outside 2012–2014 are outside this pilot. `model_ready` remains false.

This is a model trained conditional on prior actual selection, not an assertion
that the full pre-draft eligible population is reconstructed. The original
inference pools and 392-row 2019–2025 retrospective benchmark remain unchanged.
No 2019+ draft-order source was saved or used in the build.

## Reproduction

The builder is offline and requires the private cached source texts and local
identity/input files. It uses the existing pandas/pyarrow environment:

```sh
work/.venv/bin/python work/verified_prior_drafts/build.py
python3 work/verified_prior_drafts/test_build.py
```

Nine tests check complete source rosters, current/future cohort exclusion,
publication cutoff enforcement, independence from draft positions and row
order, missing identities, ambiguity, unsupported years and source-derived IDs.
No real or synthetic model fitting occurs. The private-source test skips if
those unpublished captures are unavailable.

`PUBLIC_ALLOWLIST.json` is exhaustive. It excludes full copyrighted bodies,
protected positions, broad identity catalogs and all unspecified files.
