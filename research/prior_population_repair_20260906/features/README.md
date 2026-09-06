# Eight-member feature repair

Feature-only factual inputs for the eight corroborated 2012–2014 source members missing from the current research pool. Every member remains in every table, including those without observations. This package contains no outcome labels, actual draft positions, model scores or benchmark claim.

`numeric_feature_join.csv` has eight rows, the metadata key `candidate_id,draft_year`, and 148 numeric fields. No names, broad or legacy player IDs, teams, source IDs, or draft positions are learner columns. Identity crosswalks and source-name matches stay in `private/`.

| Family | Numeric fields | Rows with observations |
| --- | ---: | ---: |
| Historical college context | 41 | 7 |
| Verified pre-draft mock ranks | 4 | 6 |
| Archived mock profile fields | 10 | 6 |
| Source-reported Synergy figures | 74 | 5 |
| Fixed-lexicon report counts | 19 | 5 |

College fields reproduce the inherited source-only 41-column definitions. The raw field allowlist excludes actual pick, birthdate and height columns. Each selected source season is no later than the draft year and at most one year earlier; this permits the reviewed 2013 member with a final 2012 college season. These are retrospectively retrieved historical facts: their original publication vintage is not verified. One 2012 member has only an uncorroborated longer first-name form in the college cache and remains missing; no new alias was inferred.

Mock facts are re-extracted from the existing six verified DraftExpress/NBADraft.net 2012–2014 tables. Table boundaries, 60-row coverage, original rank hashes, publication dates, capture times and exact reviewed same-year identities are checked. The profile uses one whole source row, preferring DraftExpress, then NBADraft.net; BMI always uses that same row's listed size. Profile age is the source's reported snapshot age. Listed size is not an official measurement; source-listed class and playing roles retain the original definitions. Missing mock coverage and one-source rank spread remain missing.

Scouting fields reuse pinned source-verified records through reviewed broad/legacy identity links. Two additional uniquely named 2014 sections, already present in pinned archives, supply five factual metrics and the existing fixed lexicons. Full source bodies remain private in the source package; this repair stores facts, units, denominators, provenance hashes and word counts. All archived sources predate midnight in America/New_York on the appropriate draft date. Lexicons are literal word frequencies, not player grades.

Reproduce with `python3 work/prior_population_repair/features/build.py`; validate with `python3 work/prior_population_repair/features/test_features.py`. The builder verifies the original public source manifests before extracting and does not modify them. This is an internal candidate package; publishing and model integration were outside this task.
