# Historical identity bridge verification

Both requested NBA-to-Basketball-Reference identity bridges are verified. Each
intended person's current structured Wikidata record explicitly publishes both
IDs, and the NBA ID matches the independently corroborated official historical
combine identity. The records are distinct from the corresponding fathers'
records, which have different NBA IDs, Basketball-Reference IDs and birth dates.

This use of current identity metadata was explicitly authorized for cross-system
identity correction. No current physical measurement, age, career statistic or
other feature is imported into a model. No WAR value is read or used to establish
an identity. Source response hashes, entity revisions, statement IDs, references
and identity-only projections are retained privately.

| Verification result | Count |
| --- | ---: |
| Requested identity bridges | 2 |
| Exact published ID pairs verified | 2 |
| Older father identities distinguished | 2 |
| Wrong-person cache subjects | 2 |
| Wrong-person cache files documented | 4 |
| Proposed historical calendar entries | 5 |
| Initiated search queries / direct HTTP requests | 2 / 5 |

The registry is community-maintained Wikidata. Its NBA-ID claims have no attached
reference in these snapshots; the IDs separately agree with the existing verified
official combine records. The review records that provenance limit instead of
claiming that Wikidata is an NBA-issued crosswalk. The published property labels
were also verified directly from the structured property records.

## Wrong-person cache evidence

For both intended historical prospects, the cached Wikipedia attention result
and its predraft article revision describe the father. The cached birth dates,
draft years and college affiliations belong to those older identities. The
article revisions themselves predate the intended prospect's draft, so a valid
timestamp did not prevent a wrong-person feature join.

The private audit preserves each original cache path and SHA256, the cached
article title and immutable revision URL, and source-person versus intended-person
identity facts. All four original cache files remain unchanged. This is bounded
evidence for a later quarantine update; it does not modify any feature package,
study, frozen input bundle or original cache.

## Proposed calendar entries

Five previously quarantined calendar metadata entries now have verified identity
bridges. The proposal retains their existing actual season/ordinal records through
2018. It contains no WAR values. Parent review and a separate bundle rebuild are
still required; no calendar, label or model promotion happens automatically.

`private/verified_identity_crosswalk.csv` records the two verified links, keeping
source candidate IDs, broad PIDs and legacy PIDs separate. The other central
private files are:

- `wrong_person_cache_audit.csv`: four original paths/hashes and the complete
  identity mismatch evidence.
- `wrong_person_cache_projections.json`: only historical name, birth/cohort and
  college facts extracted from those existing caches.
- `proposed_calendar_entries.csv`: five identity-verified season/ordinal proposals.
- `source_manifest.json`: entity revision IDs, retrieval times and source hashes.
- `Q*_identity_only.json`: restricted published identity claim projections.
- `network_log.json`: seven initiated requests/queries, below the cap of twelve.

The private directory has mode700 and files mode600. The exhaustive public
allowlist contains aggregate results and verification code only. It excludes
crosswalks, identities, birth dates, original cache paths, row-level calendars,
outcomes and labels. No publication has been performed.

## Validation

```sh
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_identity_bridge/verify.py
PYTHONDONTWRITEBYTECODE=1 python3 work/prior_population_identity_bridge/test_verify.py
```

The verifier is offline; it consumes the restricted source projections from this
bounded collection. Eight tests check wrong-parent substitution, wrong source
IDs, ambiguous or deprecated identity claims, independence from WAR-agreement
metadata, exact calendar preservation and unchanged original cache hashes.

No model was fit, no benchmark was scored, no 2019+ test outcome was read, and no
existing bundle was changed. This audit resolves two identities; it does not
certify all historical features or the complete training population.
