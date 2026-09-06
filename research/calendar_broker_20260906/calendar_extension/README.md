# ESPN calendar extension: source pilot and bounded collection

The initial pilot used 26 total requests/attempts, below its 30-request ceiling.
It established actual NBA participation dates in seasons ending 2023, 2024, and
2025, with separate regular-season and postseason source tables. It produced 11
season-type records (six regular-season, five postseason); two identity matches
also agreed exactly with their complete pre-2023 RAPTOR played-season calendars.
No WAR value, project answer file, model fit, or test score was read.

NBA CDN historical boxscore access returned 403 on the first request, and that
host was not retried. ESPN's public primary-source career-statistics service was
accessible. Its relevant endpoint patterns are:

- Identity metadata:
  `https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/athletes/ESPN_ID`
- Career regular-season statistics:
  `https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/ESPN_ID/stats`
- Career postseason statistics: the same endpoint with `?seasontype=3`.
- Candidate discovery:
  `https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2023/athletes?limit=1000`.

The collector uses only explicit `season.year`, matching `season.displayName`,
the `gamesPlayed` field identified by its column name, season type, and identity
metadata. It never infers continuity from debut/retirement years or derives dates
from draft year. Positive games establish participation; missing source tables
are not converted into zero games or proof of absence.

## Source traps detected and handled

1. The 2023, 2024, and 2025 athlete catalogs returned identical 628-ID sets. These
   are candidate discovery lists, **not verified historical player universes**.
   Missing athletes remain pending.
2. For a player without a postseason table, asking for `seasontype=3` may return
   the regular-season table and a filter still set to 2. The parser explicitly
   checks the returned filter. Such data never becomes postseason participation.
3. Some NBA athlete entries have no statistics table at all. They remain missing
   evidence rather than a manufactured empty career.
4. ESPN metadata supplies ESPN IDs, names, and birth dates; its `alternateIds`
   field is not an NBA-ID crosswalk. The collector uses the existing project's
   NBA IDs only after an exact unique normalized-name match. To mark a timeline
   verified, it also requires complete matching pre-2023 RAPTOR season sets and
   both explicitly requested source season-type tables. Other joins/timelines
   remain partial and require review.

## Authorized collection now running

The parent explicitly authorized a larger bounded collection after reviewing the
pilot. Its separate directory is `campaign_20260906/`.

- Up to 300 candidate athletes in original publisher catalog order.
- Up to two hours and 900 new requests, one sequential request per second at
  most. Requests for career tables occur only after a unique project-name match
  with an existing NBA ID and a relevant draft cohort through 2024.
- Cached responses are hash-checked and reused; completed athletes are resumable.
- HTTP 403 stops the source pending review. HTTP 429 stops immediately and
  enforces the source Retry-After or at least one hour before retry.
- An individual HTTP 404 remains an unresolved record/table while other athletes
  continue. This handling was added in `collector_v2.py` after the first source
  404 paused version 1. `execution_changes.json` preserves both code hashes; the
  original 300-athlete/900-request cap and wall-clock deadline were retained.
- `pilot_summary.json` updates after each completed candidate.
- `process.json` records the PID and exact launch arguments.
- `preregistered_plan.json` records caps, selection rules, and input/code hashes.
- Raw source JSON stays under private storage because it contains additional
  player information and scoring statistics unrelated to this task. Only
  calendar dates, identifiers, eligibility flags, and provenance are exported.
- No automatic promotion into the broker, model feature store, or training data.

`completed_athletes.json` contains per-player `timeline_verified`,
`timeline_partial`, source-table availability, identity-join provenance, and
recorded NBA seasons. `participation_dates.csv` is written when the bounded run
finishes; during the run, completed individual records are already persisted.
Do not tell users the entire calendar is complete based on the catalog or a
subset of verified timelines.

The parser checks in `test_calendar.py` passed using cached source responses:
explicit years, regular/postseason separation, ignored-filter rejection,
unavailable-postseason handling, and invariance to unrelated scoring statistics.
No network request is needed to run those checks.

Code, registration, request metadata, and aggregate summaries can be preserved in
the research repository. Keep raw responses and per-player post-draft calendar
files outside ordinary development/model mounts until the separate broker review.
