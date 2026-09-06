# Historical prior-draft identity gap review

This bounded, offline review preserves all **180 selected memberships** in the
existing 2012–2014 source registry. It reviews its 24 apparent identity/training
gaps using only names, identifiers and historical source dates. It does not
select members using NBA participation, key availability, feature availability
or labels.

Two apparent gaps resolve to existing research rows after explicit source-ID
alias review. **22 selected members are still absent from the research table.**
The original 156 non-gap mappings are inherited; this review does not independently
certify every one of those links.

| Draft year | Complete source memberships | Apparent gaps reviewed | Existing rows recovered | Still absent |
| --- | ---: | ---: | ---: | ---: |
| 2012 | 60 | 5 | 0 | 5 |
| 2013 | 60 | 12 | 2 | 10 |
| 2014 | 60 | 7 | 0 | 7 |
| Total | 180 | 24 | 2 | 22 |

Of the 24 reviewed cases:

- **10 have a corroborated identity bridge** from a same-year official combine
  `PLAYER_ID` to a unique broad-key NBA-prefixed `player_uid`. Two already have
  research rows; eight still need rows. A missing `nba_id` field does not discard
  an otherwise explicit identity UID.
- **4 have provisional unique exact-name links.** The dated source name and
  unique key name agree, but no independent dated source-ID corroboration was
  recovered. These remain pending; they are not automatically promoted.
- **10 have no accepted global identity bridge.** Their source-derived candidate
  IDs and historical memberships remain present. Similar spelling alone does
  not establish an identity.

The 22 absent rows consist of five with an existing legacy identity, seven with
only a broad-key identity link or suggestion, and ten with source-only identity.
None has been given invented features or a zero label.

## Evidence and boundaries

Membership is inherited from the complete contemporary source rosters and their
independent AP crosschecks in `../verified_prior_drafts/`. Actual positions are
kept in that package's protected file; this review never parses that file or any
legacy actual-pick field. It does not read 2019+ draft-result sources.

For official combine evidence, the requested `parameters.SeasonYear` and **every
row's `SEASON`** must agree with the corresponding 2012, 2013 or 2014 source year.
Only the name and player ID are extracted. The NBA's 2013 initial and final
early-entry releases corroborate one spelling change with an identical club.
An identity-only record from the 2012–13 D-League cache also corroborates the
relevant combine ID. No statistical values from that cache are parsed.

The cached combine records describe historical seasons; an independently
observed historical snapshot is not available. Existing identity catalogs are
used only as crosswalks. Their existence or NBA-ID fields are not evidence that
someone was eligible, played in the NBA, or has an observable label.

The **broad-key PID and legacy model PID are separate namespaces**. All seven
reviewed links with both IDs have different PID strings. The private crosswalk
retains both; it never renames existing rows or merges them by PID equality.
Names, NBA IDs and crosswalk metadata must remain outside model sandboxes.

The review performs no fuzzy matching. Explicit alias decisions are restricted
to the documented source/cohort cases. Homonyms with different official IDs are
rejected, and a similar international surname is left unresolved because it has
no dated ID bridge.

## Files

- `data/coverage.json`: aggregate counts and limitations.
- `data/gap_statuses.csv`: all 24 reviewed source candidate IDs and statuses;
  contains no names, global PIDs, NBA IDs, positions or labels.
- `data/all_membership_statuses.csv`: all 180 original source candidate IDs,
  preserving membership and distinguishing reviewed gaps from inherited links.
- `data/manifest.json`: source hashes, parsed-column lists and explicit exclusions.
- `data/validation.json`: bounded test and scope results.
- `private/reviewed_crosswalk.csv`: local reviewed links and evidence strength,
  with broad and legacy PID namespaces kept separate.
- `private/evidence.csv`: local source-name/ID evidence, dates, paths and hashes.
- `private/rejected_matches.csv`: explicit homonym and similarity-only rejections.
- `private/unresolved_and_provisional.csv`: the complete list of ten unresolved
  and four provisional identity links, with individual reasons.
- `private/missing_research_rows.csv`: all 22 absent source memberships.

The private directory has mode 700 and its files mode 600. No private file or
identity catalog is in `PUBLIC_ALLOWLIST.json`. Public files describe a population
audit; they are not model input matrices.

## Practical next step

Use the complete, source-derived 180-row index as the left side of future feature
and censored-label joins. Keep source candidate IDs for unresolved identities.
Resolve the eight missing rows whose identity bridges are already corroborated
before considering provisional links. For each historical prediction cutoff,
membership dates, predraft feature dates and observable label seasons must be
checked independently. Do not treat absence from an NBA source as a zero outcome.

The prior actual-draft registry is usable only for earlier cohorts whose
selection was already known at the prediction cutoff. It does not define the
current prediction class or alter the original retrospective evaluation pool.

This work does not build feature/label rows, inspect WAR values, fit a model,
score a test, fetch new data, modify the prior registry, or certify a model.
`model_ready` remains false.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 work/.venv/bin/python work/verified_prior_drafts_identity/audit.py
PYTHONDONTWRITEBYTECODE=1 python3 work/verified_prior_drafts_identity/test_audit.py
```

Nine tests cover ambiguous identities, conflicting IDs, missing NBA-ID fields,
cross-cohort combine rows, wrong requested seasons, absence of general fuzzy or
suffix rules, preservation of the full source population, explicit pending rows,
and separation of PID namespaces. No model is run by the tests.
