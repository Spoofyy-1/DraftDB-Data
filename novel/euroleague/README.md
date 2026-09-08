# euroleague - international data spine (Euroleague / EuroCup / U18 ANGT)

Pre-draft international production for drafted players, built from the open
Euroleague API.  One row per `pid`, numeric columns only.

Generated 2026-09-08 14:34.  Pull status: **PARTIAL** - 1,653/12,882 box scores cached (12.8%). See _Resuming_ below; rerun `build.py` after the pull finishes.

## What this is

Three competitions, pulled game by game and aggregated **per player, per
competition, using only games played before that player's draft night**:

* **E - Euroleague** (`el2_*`), seasons E2000 (2000-01) onward
* **U - EuroCup** (`eu2_*`), seasons U2002 (2002-03) onward
* **J - U18 Adidas Next Generation Tournament** (`angt_*`), all tournaments 2002-03 onward

Euroleague and EuroCup are computed **separately and never pooled** - they are
different levels of competition (Vashro 1.61 vs 0.92).  The U18 club tournament
is never averaged into either; it lives only in `angt_*`.

## Source and endpoints

Host `https://api-live.euroleague.net` - open, unauthenticated, `robots.txt` is
empty (no restrictions expressed).  Endpoints used:

| endpoint | used for |
|---|---|
| `/v2/competitions` | competition catalogue (43 competitions) |
| `/v2/competitions/{comp}/seasons?limit=500` | season list per competition |
| `/v2/competitions/{comp}/seasons/{season}/games?limit=500&offset=N` | game list with exact timestamps (`utcDate`, `date`) |
| `/v2/competitions/{comp}/seasons/{season}/games/{gameCode}/stats` | full box score: per-player counting stats + `person` bio + registration dates |

Every response is cached verbatim under `raw/` (gzipped JSON), so every
re-build is offline and the pull is resumable.

### Rate and ToS notes

* Requests are throttled to **one per 1.1 s** with an adaptive slow-down: any
  HTTP 429 widens the gap by 0.4 s (cap 6 s) and triggers a 30 s+ cooldown; the
  gap only narrows again after 400 clean requests.  An initial probe at 2 req/s
  drew 429s, so the sustained rate was reduced.
* Descriptive `User-Agent` identifying the project and a contact address.
* No login, no paywall, no JS challenge, no Cloudflare bypass - the API is
  public and unauthenticated.  Only `GET` requests are issued.
* This is a non-commercial research use of published box-score facts.
  Euroleague Basketball owns the underlying data; redistribute the derived
  features, not the raw cache.

## Dating rule (no leakage)

Every box score carries an exact kick-off timestamp.  A game counts toward a
player's features **only if `utcDate` (falling back to `date`) is strictly
before 22:00 UTC on his draft date**, using the draft-night table in
`COLLECTOR_RULES.md`.  Nothing is filtered on a season label: a 2000-01
Euroleague season straddles the June-2001 draft, and only the games actually
played before that night are counted.

Draft class 2026 has no published cutoff in `COLLECTOR_RULES.md`.  Rather than
invent a draft night, those rows use a deliberately conservative
**2026-06-01** cutoff (earlier than any plausible draft date), so they can only
ever under-count.  They are flagged with `cutoff_inferred = 1`.

## Coverage

### Pull coverage

| code | competition | seasons | first | last | games played | box scores cached | % cached | seasons complete |
|---|---|---|---|---|---|---|---|---|
| E | Euroleague | 27 | 2000-10-15 | 2026-05-24 | 6603 | 189 | 2.9% | 2/27 |
| J | U18 ANGT | 66 | 2003-05-09 | 2026-05-24 | 1464 | 1464 | 100.0% | 66/66 |
| U | EuroCup | 25 | 2002-10-14 | 2026-04-28 | 4815 | 0 | 0.0% | 1/25 |

### Feature coverage by draft-year band

| draft years | drafted players in identity file | with pre-draft intl rows | % of class | with Euroleague mins | with EuroCup mins | with ANGT |
|---|---|---|---|---|---|---|
| 2000-07 | 582 | 21 | 3.6% | 18 | 0 | 3 |
| 2008-18 | 1017 | 37 | 3.6% | 1 | 0 | 36 |
| 2019-25 | 900 | 55 | 6.1% | 0 | 0 | 55 |
| 2026 | 61 | 7 | 11.5% | 0 | 0 | 7 |

### Block fill rates

| block | meaning | columns | median fill rate |
|---|---|---|---|
| el2_* | Euroleague | 55 | 16% |
| eu2_* | EuroCup | 26 | 0% |
| yng_* | young senior minutes | 9 | 100% |
| angt_* | U18 ANGT | 26 | 84% |
| club_* | clubs / registrations | 4 | 100% |
| tier_* | league tier | 3 | 16% |
| bio_* | bio | 1 | 99% |

## Matching to the identity file

`tabular_names.csv` (2,560 drafted players, 2000-2025) plus verified
birthdates for 947 of them (`age_verified_wiki.csv`).  Rule-based only:

1. **Normalise** both names: NFKD accent-strip, lowercase, drop punctuation and
   generational suffixes (`jr sr ii iii iv v`), then sort the tokens.  Sorting
   makes the API's `SURNAME, FIRSTNAME` match the identity file's
   `Firstname Surname` and survives multi-part surnames
   (`VAN DEN SPIEGEL, TOMAS`).
2. **Draft-year plausibility**: the season of the person's first game must be
   `<= draft_year`.
3. **Birthdate agreement**: where a verified birthdate exists on our side and
   the API supplies one, the **birth years must match**; a differing year
   rejects the candidate.  Day-level agreement is normally exact (it held for
   every matched pid where both dates existed), but the API carries the
   occasional data-entry error - Kristaps Porzingis is listed as 1995-04-02
   against a verified 1995-08-02 - so a same-year day mismatch keeps the match
   and sets `birth_day_mismatch = 1` in `matches.csv` instead of silently
   dropping a real player.  The year alone still separates namesakes: it is
   what rejects Patrick Baldwin **Sr.** (1972) from Patrick Baldwin Jr.
4. **Age window** where we have no verified birthdate: a real drafted *pick*
   must be 16-27 at his draft (the 947 verified draftees span 18.5-24.8, so an
   older namesake is rejected); rows with a null `actual_pick` are NBA-entry-year
   rows and are allowed 16-40.
5. A person matches only if **exactly one** identity row survives; anything
   ambiguous is logged, never guessed.
6. One `pid` may legitimately own several API person codes (the U18 competition
   uses a different code space from the senior ones).  If a pid's codes disagree
   on birthdate, all of them are dropped and logged.

Result: **125 person-code matches covering 125 pids**
(1 of them
matched on birth year with a flagged day-level mismatch),
of which **120 have at least one pre-draft game** and appear in
`features.csv`.  `unmatched.csv` holds 3 rows:

| reason | persons |
|---|---|
| birthdate_conflict | 2 |
| draft_year_before_first_season | 1 |

Persons whose names never appear in the identity file at all are *not* logged:
that is the overwhelming majority of the 6,006 European players in the
API and would drown the report.  Only name hits that were *rejected* (and
ambiguous cases) are reported.

## Files

| file | contents |
|---|---|
| `features.csv` | **the deliverable** - `pid` + 127 numeric columns, one row per pid |
| `provenance.csv` | per pid: person codes, competitions, seasons, games used, first/last game date, the exact cutoff applied |
| `coverage.csv` | per competition-season: games played vs box scores cached, complete flag |
| `unmatched.csv` | rejected and ambiguous name matches with the reason |
| `matches.csv` | accepted person-code -> pid map |
| `player_games.csv.gz` | per-player-game table (every game, not just pre-draft) |
| `registrations.csv.gz` | person x competition x season x club with registration start/end |
| `raw/` | verbatim API cache (`seasons/`, `games/`, `stats/`, `done/`) |
| `pull.py` / `build.py` / `validate.py` / `make_readme.py` / `finish.sh` | collector, builder, quality gate, doc generator, auto-rebuild watcher |

`player_games.csv.gz`, `registrations.csv.gz`, `matches.csv` and
`unmatched.csv` contain **player names** and are covered by the local
`.gitignore`, as is `raw/`.  This directory sits inside the DraftDB-Data git
repo, which has a public remote - only `features.csv`, `provenance.csv`,
`coverage.csv` and the scripts are name-free.

## Feature definitions

Units: minutes are minutes (the API reports `timePlayed` in seconds), ages are
in years (`days / 365.25`), rates are per 40 minutes, percentages are
fractions (0-1).  **Missing is empty, never 0.**  A count that is genuinely
zero (e.g. `eu2_games = 0` for a player who never appeared in the EuroCup) is
written as 0; a *rate* with no denominator (his `eu2_ts`) is left empty.

### `el2_*` (Euroleague) and `eu2_*` (EuroCup) - identical definitions, computed separately

| column | definition |
|---|---|
| `*_games` | games played before the cutoff (minutes > 0) |
| `*_dnp` | pre-draft games he was in the box score but played 0 minutes |
| `*_starts` | games started, counted only over games where the starting five was actually recorded |
| `*_start_games` | games where the `startFive` flag was reliable (exactly five flagged on that side) - the denominator for `*_starts` |
| `*_start_rate` | `*_starts / *_start_games` |
| `*_min` | total minutes |
| `*_min_share` | his minutes / his team's minutes available, summed over every game he was in the box score (DNPs included in the denominator).  Team minutes available = sum of that team's player minutes in that game, i.e. 200 for a 40-minute game, scaling correctly for overtime |
| `*_pts40 *_oreb40 *_dreb40 *_ast40 *_stl40 *_blk40 *_tov40 *_pf40 *_pir40` | per-40-minute rates |
| `*_ts` | true shooting: `PTS / (2 * (FGA + 0.44*FTA))` |
| `*_efg` | effective FG%: `(FGM + 0.5*3PM) / FGA` |
| `*_3par` | `3PA / FGA` |
| `*_ftr` | `FTA / FGA` |
| `*_ftpct` `*_3ppct` `*_2ppct` | free-throw, three-point, two-point percentage |
| `*_usage` | `100 * (FGA + 0.44*FTA + TOV) * (TeamMin/5) / (Min * (TeamFGA + 0.44*TeamFTA + TeamTOV))`, aggregated over the games he played |
| `*_pm40` | plus/minus per 40 minutes, **only over games that actually record it** (see limitations) |
| `*_ls_<same>` | every metric above recomputed over his **last pre-draft season** in that competition |
| `*_age_first` `*_age_last` | age at his first / last pre-draft game in that competition |
| `*_seasons` | distinct seasons with a pre-draft game |
| `*_trend_pts40` `*_trend_pir40` | last pre-draft season minus first pre-draft season (empty when only one season) |

`pir` is the API's own `valuation` field - the standard European Performance
Index Rating.

### `yng_*` - senior minutes accrued young (E and U only)

| column | definition |
|---|---|
| `yng_min_e` `yng_min_u` | senior minutes played before his 20th birthday, Euroleague and EuroCup separately |
| `yng_min_senior` | the two combined |
| `yng_games_u20` | senior games played before turning 20 |
| `yng_age_first_senior` | age at his first senior (E or U) game |
| `yng_min_age18` `yng_min_age19` | minutes played while aged 18.0-18.99 / 19.0-19.99 |
| `yng_min_share_age18` `yng_min_share_age19` | minutes share over those same games |

### `angt_*` - U18 Adidas Next Generation Tournament (competition J only)

Never averaged into `el2_*` or `eu2_*`.

| column | definition |
|---|---|
| `angt_has` | 1 if he has any pre-draft ANGT game |
| `angt_tournaments` | distinct tournaments |
| `angt_games` `angt_starts` `angt_start_rate` `angt_min` `angt_min_share` | as above |
| `angt_pts40 ... angt_pir40`, `angt_ts angt_efg angt_3par angt_ftr angt_ftpct angt_3ppct angt_2ppct angt_usage` | as above |
| `angt_age_first` | age at his first pre-draft ANGT game |
| `angt_rel_age` | his age minus the **mean age of that tournament's field**, averaged over his tournaments weighted by games.  Negative = young for the field |

### `club_*`

| column | definition |
|---|---|
| `club_n_senior` | distinct clubs he appeared for in E/U before the draft |
| `club_n_all` | distinct clubs across all three competitions |
| `club_registrations` | registration records (person x competition x season x club) starting before the cutoff |
| `club_midseason_moves` | of those, the ones whose `startDate` is more than 30 days after that competition-season's first game - i.e. he joined mid-season |

### `tier_*` and other

| column | definition |
|---|---|
| `tier_best` | Vashro level-of-competition rating of the **highest venue he played pre-draft**: Euroleague 1.61, EuroCup 0.92, ANGT -0.65 |
| `tier_e` `tier_u` | 1.61 / 0.92 when he appeared in that competition, else empty |
| `bio_height_cm` | listed height in his **last pre-draft** box score (teenagers grow, so the latest pre-draft observation is used) |
| `birth_src_wiki` | 1 if ages use the verified wiki birthdate, 0 if they use the API's |
| `cutoff_inferred` | 1 for the 2026 class (conservative 2026-06-01 cutoff), else 0 |
| `intl_any` | always 1 - a merge indicator, so pids absent from this file are distinguishable from pids with no international games |

Vashro's ratings come from the 2015 fansided "Deep Dives: Measuring Level of
Competition Around the World" article
(<https://fansided.com/2015/11/06/deep-dives-measuring-level-of-competition-around-the-world/>).
The table also lists Adriatic League 0.82, which is kept in the code's lookup
but is never populated.  The API does expose an `AL` competition, but it is an
empty shell: `/v2/competitions/AL/seasons` returns 6 season entries
(`AL000`-`AL005`, 2000-2005) and every one of them reports **0 games**
(probed 2026-09-08).  Adriatic production therefore cannot be collected from
this source and would need a different provider.

## Known limitations

1. **Plus/minus is sparse.**  Most pre-2010 box scores do not record it.  It is
   flagged **per game** (a game carries plus/minus iff some player in it has a
   non-zero value), so a player in a game without the data gets an empty
   `*_pm40` rather than a fabricated 0.  In the 2000-01 Euroleague season
   exactly 1 game of 72 records it.
2. **`startFive` is not always recorded.**  Some old box scores flag nobody, a
   few flag more than five.  `*_starts` is counted only over game-sides where
   exactly five players are flagged, and `*_start_games` reports that
   denominator.
3. **Corrupt birthdates in the API.**  Two patterns were found and are filtered
   out rather than propagated: persons in the 2005-06 U18 tournament with a
   1998 birth year (age 8), and a large block in the 2008-09 / 2009-10 U18
   seasons whose birthdate sits exactly 20.0 years before the tournament (a
   placeholder).  U18 field means are computed only over ages 14.0-19.0 (real
   U18 fields top out at 18.4) and require at least 10 valid ages; our own
   players' U18 ages must fall in 13.0-19.5 and senior ages in 14.0-45.0, else
   the age feature is left empty.  Where a player's birthdate is taken from the
   API rather than the verified file, the value recorded in his **senior** box
   scores is preferred over the U18 one.
4. **The J competition bundles qualifying tournaments**, so `angt_tournaments`
   counts qualifiers and finals alike.
5. **No Adriatic/ABA, national leagues or FIBA youth national-team data.**  A
   player whose best pre-draft venue was the Adriatic League (Jokic, Micic,
   Bogdanovic and most Balkan prospects) shows only the competitions collected
   here, so `tier_best` is a **floor, not a ceiling**.  The Adriatic League is
   not obtainable from this API at all (see above).  The same is true of the
   ~35 national-league codes the catalogue advertises: `SP`, `IT`, `GR` and
   `TU` each list 6 seasons (2000-2005) and return **0 games** (probed
   2026-09-08), so only `E`, `U` and `J` carry real data here.
6. **Height is 85% populated, weight ~6%** - weight is not emitted.
7. `min_share` counts only games he was in the box score for; games he missed
   through injury or non-registration are not in the denominator, so it
   measures role when available, not availability.
8. **The 2020 draft (18 November 2020) falls mid-season.**  The 2020-21
   European season had already tipped off, so for that class the "last
   pre-draft season" (`*_ls_*`) is a handful of October/November games rather
   than a full campaign.  `*_ls_games` reports the sample size, so a model can
   down-weight it; every other class has a clean season boundary between the
   last European game and draft night.
9. `*_trend_*` is empty for anyone with a single pre-draft season in that
   competition - which is most players.
10. **The early draft classes are truncated by the source.**  The API's oldest
    Euroleague season is 2000-01 and its oldest EuroCup season is 2002-03, so
    nobody in the 2000 class can have a pre-draft game at all (they appear in
    no row here), the 2001-02 classes have at most one or two seasons of
    history, and `*_seasons` / `*_trend_*` for them reflect the source's start
    date rather than the player's actual career.  From roughly the 2004 class
    onward a European prospect's full pre-draft Euroleague history is present.
11. **Zero versus unknown.**  `*_games`, `*_min`, `yng_min_*`, `club_*` and
    `angt_has` are written as a true `0` when the player genuinely never
    appeared (coverage is complete for the seasons pulled).  Every *rate* with
    no denominator is left empty, as is any age we could not date.

## Rebuilding and resuming

Everything downstream of `raw/` is offline and idempotent.

```sh
cd /Users/kennakao/nba/datarebuild/novel/euroleague

# resume the pull (skips finished seasons and already-cached games)
nohup python3 pull.py J E U >> run.log 2>&1 &

# how big is the remaining job?
python3 pull.py --count

# rebuild every derived table from the cache (no network)
python3 build.py                 # coverage -> parse -> match -> features
python3 build.py features        # just re-aggregate
python3 make_readme.py           # refresh this file's numbers
python3 validate.py              # quality gate, exits non-zero on failure
```

`validate.py` re-runs the checks used to develop this collector: one row per
pid, numeric-only columns, **no game at or after the draft cutoff**, no rate
populated for a player with no minutes, every rate inside a plausible range,
and internal consistency (`*_ls_min <= *_min`, under-20 minutes <= total senior
minutes, `starts <= start_games`, `yng_min_senior == yng_min_e + yng_min_u`).

Checkpointing: a season is marked done with a marker file in `raw/done/` only
when **every** played game in it was fetched or returned a genuine 404.  A
transient failure leaves the game uncached and the season un-marked, so the
next run retries exactly what is missing.  Individual game files are skipped if
already present, so a resume mid-season costs nothing.

`finish.sh` waits for the running pull to exit and then reruns `build.py`
automatically, so `features.csv` becomes final without intervention.

Progress: `tail -f run.log`, or `python3 build.py coverage` then read
`coverage.csv` (`complete` = 0 marks seasons still missing box scores).
