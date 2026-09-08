# fiba_youth - age-relative FIBA youth-tournament feature block

Pre-draft features built from FIBA's own competition archive for men's
U15-U19 national-team tournaments, 2000-2025, plus Nike Hoop Summit
World Select participation from Wikipedia.

This block is deliberately **separate** from the existing `intl_*`
inputs.  The project's current inputs fold crude youth lines
(`intl_youth_pts36`, `intl_youth_n`) into the international *pro*
season block, which mixes a 16-year-old's U16 EuroBasket week with a
grown man's Liga ACB season and penalises college players.  Everything
here is instead **age-relative**: every rate is z-scored inside the
field of the tournament the player actually played in, and age is
expressed relative to that same field's mean age.  Nothing in this
directory writes to `data_v4` or to any existing input file.

## Outputs

| file | rows | contents |
|---|---|---|
| `features.csv` | 2560 | one row per pid in the identity file, 18 numeric `fy_*` columns, missing = empty |
| `player_tournaments.csv` | 871 | one row per matched pid x tournament: level, dates, games, minutes, per-40 rates, shooting rates, age, team finish, and the tournament field's mean/SD for age and every per-40 stat |
| `field_tournaments.csv` | 317 | one row per tournament actually parsed: id, level, dates, team count, roster size, qualified-field size, field mean/SD age, URL |
| `unmatched.csv` | 14 | FIBA youth players whose name hit the identity file but were rejected or ambiguous, with the reason |
| `provenance.csv` | 484 | pid -> FIBA person id, tournaments used, source URLs |

Raw pages are cached gzipped under `raw/pages/`, sitemaps under
`raw/sitemaps/`, and the per-tournament extraction (which doubles as
the crawl checkpoint) under `raw/parsed/`.  Re-runs are offline.

## Sources

* `https://www.fiba.basketball/en/history-sitemap_index.xml` - the 259
  competitions in the FIBA archive (fetched 2026-09-08).
* `https://www.fiba.basketball/en/history/<comp>/sitemap_index.xml` -
  the editions of one competition.
* `https://www.fiba.basketball/en/history/<comp>/<eventId>/players` -
  event metadata, team list, and the **full player field** with dates
  of birth, nationality, position and games played.
* `https://www.fiba.basketball/en/history/<comp>/<eventId>/teams/<team>`
  - per-player tournament totals for that team and the team's final
  ranking.
* `https://en.wikipedia.org/wiki/Nike_Hoop_Summit` - the "Alumni
  selected in the NBA draft" table (Name / Draft Year / NHS Year(s) /
  NHS Team), revision 1361318085 captured 2026-06-27T04:11:52Z.

The `/stats` (leaders) tab was **not** used: it only returns the top 50
per category, which cannot define a field distribution.  Team pages give
the complete field at 1 + n_teams requests per edition.

## Competitions crawled

Selection rule applied to the 259 archive competitions: keep every
men's national-team competition at age category U15-U19.  Excluded:
women's events (slug contains `womens`), U20 and older, club
competitions, 3x3, and the U18 All-Star Game.

`editions` counts every edition in the competition's sitemap;
`in range` counts those with season 2000-2025 that returned a player
field.  A cancelled edition (e.g. the 2020 U17 World Cup) contributes 0
roster rows.

| competition | level | scope | div | age | editions | in range | years | roster rows | URL |
|---|---|---|---|---|---|---|---|---|---|
| `276-fiba-u19-basketball-world-cup` | 4 | world | A | U19 | 20 | 10 | 2003-2023 | 1915 | https://www.fiba.basketball/en/history/276-fiba-u19-basketball-world-cup |
| `249-fiba-u17-basketball-world-cup` | 3 | world | A | U17 | 11 | 8 | 2010-2024 | 1245 | https://www.fiba.basketball/en/history/249-fiba-u17-basketball-world-cup |
| `254-fiba-u18-afrobasket` | 3 | continental | A | U18 | 17 | 11 | 2000-2022 | 1017 | https://www.fiba.basketball/en/history/254-fiba-u18-afrobasket |
| `256-fiba-u18-americup` | 3 | continental | A | U18 | 15 | 11 | 2002-2024 | 848 | https://www.fiba.basketball/en/history/256-fiba-u18-americup |
| `258-fiba-u18-asia-cup` | 3 | continental | A | U18 | 19 | 11 | 2000-2022 | 966 | https://www.fiba.basketball/en/history/258-fiba-u18-asia-cup |
| `263-fiba-u18-eurobasket` | 3 | continental | A | U18 | 53 | 26 | 2000-2023 | 5066 | https://www.fiba.basketball/en/history/263-fiba-u18-eurobasket |
| `266-fiba-u18-oceania-championship` | 3 | continental | A | U18 | 7 | 7 | 2002-2016 | 224 | https://www.fiba.basketball/en/history/266-fiba-u18-oceania-championship |
| `224-fiba-u16-afrobasket` | 2 | continental | A | U16 | 10 | 9 | 2007-2023 | 815 | https://www.fiba.basketball/en/history/224-fiba-u16-afrobasket |
| `225-fiba-u16-americup` | 2 | continental | A | U16 | 10 | 8 | 2009-2023 | 767 | https://www.fiba.basketball/en/history/225-fiba-u16-americup |
| `228-fiba-u16-asia-cup` | 2 | continental | A | U16 | 8 | 7 | 2009-2023 | 1202 | https://www.fiba.basketball/en/history/228-fiba-u16-asia-cup |
| `235-fiba-u16-eurobasket` | 2 | continental | A | U16 | 51 | 26 | 2000-2023 | 4767 | https://www.fiba.basketball/en/history/235-fiba-u16-eurobasket |
| `237-fiba-u16-oceania-championship` | 2 | continental | A | U16 | 4 | 4 | 2009-2015 | 120 | https://www.fiba.basketball/en/history/237-fiba-u16-oceania-championship |
| `250-fiba-u17-oceania-championship` | 2 | continental | A | U17 | 5 | 4 | 2017-2023 | 237 | https://www.fiba.basketball/en/history/250-fiba-u17-oceania-championship |
| `114-cbc-u18-championship` | 1 | zone | B | U18 | 2 | 2 | 2005-2008 | 0 | https://www.fiba.basketball/en/history/114-cbc-u18-championship |
| `123-centrobasket-u15-championship` | 1 | zone | B | U15 | 10 | 7 | 2011-2022 | 558 | https://www.fiba.basketball/en/history/123-centrobasket-u15-championship |
| `125-centrobasket-u16-championship` | 1 | zone | B | U16 | 1 | 1 | 2009-2009 | 0 | https://www.fiba.basketball/en/history/125-centrobasket-u16-championship |
| `127-centrobasket-u17-championship-qualifiers` | 1 | zone | B | U17 | 2 | 1 | 2022-2022 | 0 | https://www.fiba.basketball/en/history/127-centrobasket-u17-championship-qualifiers |
| `128-centrobasket-u17-championship` | 1 | zone | B | U17 | 11 | 9 | 2007-2023 | 819 | https://www.fiba.basketball/en/history/128-centrobasket-u17-championship |
| `131-centrobasket-u18-championship` | 1 | zone | B | U18 | 4 | 2 | 2002-2003 | 0 | https://www.fiba.basketball/en/history/131-centrobasket-u18-championship |
| `133-centrobasket-u19-championship` | 1 | zone | B | U19 | 1 | 1 | 2005-2005 | 0 | https://www.fiba.basketball/en/history/133-centrobasket-u19-championship |
| `141-cocaba-u15-championship` | 1 | zone | B | U15 | 2 | 2 | 2010-2014 | 70 | https://www.fiba.basketball/en/history/141-cocaba-u15-championship |
| `143-cocaba-u16-championship` | 1 | zone | B | U16 | 7 | 5 | 2008-2019 | 349 | https://www.fiba.basketball/en/history/143-cocaba-u16-championship |
| `145-cocaba-u17-championship` | 1 | zone | B | U17 | 3 | 3 | 2007-2011 | 0 | https://www.fiba.basketball/en/history/145-cocaba-u17-championship |
| `148-cocaba-u19-championship` | 1 | zone | B | U19 | 1 | 1 | 2005-2005 | 36 | https://www.fiba.basketball/en/history/148-cocaba-u19-championship |
| `172-european-youth-olympic-days-basketball-tournament-for-junior-men` | 1 | zone | B | U16 | 8 | 2 | 2000-2002 | 0 | https://www.fiba.basketball/en/history/172-european-youth-olympic-days-basketball-tournament-for-junior-men |
| `174-fiba-africa-u16-zonal-championship-for-men` | 1 | zone | B | U16 | 3 | 3 | 2008-2012 | 46 | https://www.fiba.basketball/en/history/174-fiba-africa-u16-zonal-championship-for-men |
| `221-fiba-u15-oceania-championship` | 1 | zone | B | U15 | 5 | 3 | 2018-2022 | 151 | https://www.fiba.basketball/en/history/221-fiba-u15-oceania-championship |
| `223-fiba-u16-afrobasket-qualifiers` | 1 | zone | B | U16 | 9 | 8 | 2015-2023 | 41 | https://www.fiba.basketball/en/history/223-fiba-u16-afrobasket-qualifiers |
| `226-fiba-u16-asia-cup-caba-qualifier` | 1 | zone | B | U16 | 3 | 2 | 2019-2023 | 79 | https://www.fiba.basketball/en/history/226-fiba-u16-asia-cup-caba-qualifier |
| `227-fiba-u16-asia-cup-gba-qualifier` | 1 | zone | B | U16 | 4 | 3 | 2018-2023 | 155 | https://www.fiba.basketball/en/history/227-fiba-u16-asia-cup-gba-qualifier |
| `229-fiba-u16-asia-cup-saba-qualifier` | 1 | zone | B | U16 | 3 | 2 | 2019-2023 | 95 | https://www.fiba.basketball/en/history/229-fiba-u16-asia-cup-saba-qualifier |
| `230-fiba-u16-asia-cup-sea-qualifiers` | 1 | zone | B | U16 | 3 | 2 | 2017-2023 | 108 | https://www.fiba.basketball/en/history/230-fiba-u16-asia-cup-sea-qualifiers |
| `231-fiba-u16-asia-cup-waba-qualifier` | 1 | zone | B | U16 | 3 | 3 | 2017-2022 | 176 | https://www.fiba.basketball/en/history/231-fiba-u16-asia-cup-waba-qualifier |
| `232-fiba-u16-eurobasket-qualifiers` | 1 | continental | B | U16 | 28 | 0 | - | 0 | https://www.fiba.basketball/en/history/232-fiba-u16-eurobasket-qualifiers |
| `233-fiba-u16-eurobasket-division-b` | 1 | continental | B | U16 | 22 | 19 | 2005-2023 | 4408 | https://www.fiba.basketball/en/history/233-fiba-u16-eurobasket-division-b |
| `234-fiba-u16-eurobasket-division-c` | 1 | continental | B | U16 | 21 | 18 | 2002-2023 | 1433 | https://www.fiba.basketball/en/history/234-fiba-u16-eurobasket-division-c |
| `236-fiba-u16-european-challengers` | 1 | continental | B | U16 | 1 | 1 | 2021-2021 | 334 | https://www.fiba.basketball/en/history/236-fiba-u16-european-challengers |
| `253-fiba-u18-afrobasket-qualifiers` | 1 | zone | B | U18 | 6 | 4 | 2014-2022 | 156 | https://www.fiba.basketball/en/history/253-fiba-u18-afrobasket-qualifiers |
| `257-fiba-u18-asia-cup-gba-qualifier` | 1 | zone | B | U18 | 3 | 3 | 2018-2022 | 204 | https://www.fiba.basketball/en/history/257-fiba-u18-asia-cup-gba-qualifier |
| `259-fiba-u18-asia-cup-saba-qualifier` | 1 | zone | B | U18 | 1 | 1 | 2018-2018 | 60 | https://www.fiba.basketball/en/history/259-fiba-u18-asia-cup-saba-qualifier |
| `260-fiba-u18-asia-cup-waba-qualifier` | 1 | zone | B | U18 | 2 | 2 | 2018-2022 | 106 | https://www.fiba.basketball/en/history/260-fiba-u18-asia-cup-waba-qualifier |
| `261-fiba-u18-eurobasket-division-b` | 1 | continental | B | U18 | 22 | 19 | 2005-2023 | 4363 | https://www.fiba.basketball/en/history/261-fiba-u18-eurobasket-division-b |
| `262-fiba-u18-eurobasket-division-c` | 1 | continental | B | U18 | 22 | 17 | 2001-2023 | 1322 | https://www.fiba.basketball/en/history/262-fiba-u18-eurobasket-division-c |
| `264-fiba-u18-european-challengers` | 1 | continental | B | U18 | 1 | 1 | 2021-2021 | 382 | https://www.fiba.basketball/en/history/264-fiba-u18-european-challengers |
| `329-south-american-u15-championship` | 1 | zone | B | U15 | 11 | 9 | 2008-2022 | 810 | https://www.fiba.basketball/en/history/329-south-american-u15-championship |
| `331-south-american-u16-championship` | 1 | zone | B | U16 | 9 | 6 | 2001-2007 | 179 | https://www.fiba.basketball/en/history/331-south-american-u16-championship |
| `333-south-american-u17-championship` | 1 | zone | B | U17 | 11 | 9 | 2005-2023 | 803 | https://www.fiba.basketball/en/history/333-south-american-u17-championship |
| `335-south-american-u18-championship` | 1 | zone | B | U18 | 6 | 3 | 2000-2022 | 96 | https://www.fiba.basketball/en/history/335-south-american-u18-championship |
| `346-waba-u17-championships` | 1 | zone | B | U17 | 1 | 1 | 2019-2019 | 0 | https://www.fiba.basketball/en/history/346-waba-u17-championships |

### Editions present, top-tier competitions

The archive is not gap-free.  Years actually captured, 2000-2025:

* `276-fiba-u19-basketball-world-cup`: 2003, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023
* `249-fiba-u17-basketball-world-cup`: 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024
* `254-fiba-u18-afrobasket`: 2000, 2002, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022
* `256-fiba-u18-americup`: 2002, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2021, 2022, 2024
* `258-fiba-u18-asia-cup`: 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2022
* `263-fiba-u18-eurobasket`: 2000, 2000, 2000, 2002, 2002, 2002, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023
* `266-fiba-u18-oceania-championship`: 2002, 2006, 2008, 2010, 2012, 2014, 2016
* `224-fiba-u16-afrobasket`: 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023
* `225-fiba-u16-americup`: 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023
* `228-fiba-u16-asia-cup`: 2009, 2011, 2013, 2015, 2018, 2022, 2023
* `235-fiba-u16-eurobasket`: 2000, 2001, 2001, 2001, 2003, 2004, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023
* `237-fiba-u16-oceania-championship`: 2009, 2011, 2013, 2015
* `250-fiba-u17-oceania-championship`: 2017, 2019, 2021, 2023

The FIBA U19 World Cup editions of **2001 (Japan) and 2005
(Argentina) are absent from FIBA's own competition sitemap**, so no
player from those tournaments is in this block.  That is a source gap,
not a filter, and it falls on the 2001-2008 draft classes.

### Level ladder (`fy_best_level`)

* **4** - U19 World Cup
* **3** - U17 World Cup / U18-U19 continental division A
* **2** - U16-U17 continental division A
* **1** - division B/C, qualifier, challenger or sub-continental zone event

Two further rule-based adjustments on top of that ladder.

**Same-season multi-phase records.** Before about 2005 FIBA files a
European championship as several events under one season - e.g. U18
EuroBasket 2000 appears as a 29-team qualifying round played in August
1999, an 18-team second round in April 2000, and the 12-team final
round in July 2000.  Within one competition-season the event with the
smallest field is treated as the final round and keeps its level; the
others drop one rung.  Each remains a separate row with its own dates
and its own field distribution, because each really was a separate
tournament, so `fy_n_tournaments` counts them separately.

**Small continental fields.** A division-A
continental championship whose field has fewer than 6 teams drops one
rung.  The Oceania U16/U17/U18 championships are usually just Australia
versus New Zealand, and beating New Zealand twice is not the same test
as a 16-team U18 EuroBasket.  `field_tournaments.csv` carries `n_teams`
so the demotion is auditable.

## Parsing rules

fiba.basketball is a Next.js app that server-renders its data into the
RSC "flight" payload.  Extraction is purely rule-based:

1. Concatenate every `self.__next_f.push([1,"..."])` argument and
   JSON-unescape each one (`json.loads('"'+chunk+'"')`), which
   preserves accented names exactly.
2. Event metadata = the object at `"fibaSourceDatas":{...}`, sliced by
   brace balancing and parsed with `json.loads`.  Fields used:
   `season`, `start`, `end`, `gender`, `ageCategory`, `fibaZone`,
   `competitionCategory`.
3. Team list = the first `"teams":[{"teamId"...` array.
4. Player field = every `"player":{...}` object carrying a
   `playerId` on the `/players` page.  Some rows emit
   `"team":"$hh"` RSC back-references instead of an inline team
   object; those get their team from the team pages via `teamId`.
5. Per-player totals = the `"playerInCompetitionTeamStatistics":[...]`
   array on each team page.  Team finish = `"finalRanking":<int>`.
6. Only rows with `gender` in {Men, boys, male} and `season` in
   2000-2025 are kept.

Derived quantities (all from totals, never from the site's rounded
per-game numbers):

```
minutes      = totalPlayTimeInSeconds / 60
<stat>40     = total<Stat> * 40 / minutes
pir40        = totalEfficiency * 40 / minutes      (FIBA efficiency/PIR)
usage40      = (FGA + 0.44*FTA + TOV) * 40 / minutes
TS%          = PTS / (2 * (FGA + 0.44*FTA))
eFG%         = (FGM + 0.5*3PM) / FGA
3PAr         = 3PA / FGA        FTr = FTA / FGA    FT% = FTM / FTA
```

### Tournament field distribution

Age is measured at the tournament's **last day**.  For a normal 10-day
event that is within a week of the start; for the few pre-2005 records
where FIBA merged qualifying and final phases into one entry spanning
months, it is the date of the final phase.  Age-relative features are
unaffected by the choice because the whole field uses the same
reference date.

* **Age field** = every rostered player with a listed date of birth
  whose age at the tournament start is in [13, 21] years; values
  outside that are DOB data errors and are dropped, not clamped.
* **Stat field** = players with >= 3 games **and** >= 40 total
  minutes.  Per-40 rates explode for 3-minute cameos, so they are
  excluded from the mean/SD that define the z-scores.  Both counts are
  in `field_tournaments.csv` (`n_roster`, `n_qualified`) and in every
  `player_tournaments.csv` row.
* Mean and SD are the sample mean and sample SD (n-1).  A z-score is
  left empty when the field SD is 0 or the field has < 2 members.

## Dating

Every tournament carries `start` and `end` dates from the event
metadata.  A tournament is used for a player only if its **end date is
strictly before that player's draft-night cutoff** (22:00 UTC on the
dates listed in `COLLECTOR_RULES.md`, reproduced in `build.py`).  This
matters: the U19 World Cup is usually played in late June or early
July, so for example the 2017 edition (2017-07-01 to 2017-07-09) is
*post*-draft for a 2017 draftee and pre-draft for a 2019 draftee, and
is filtered accordingly.  Nothing is dated by season label alone.

Nike Hoop Summit: the game is played in April, always before that
year's draft; a roster row is used only when its NHS year <= the
player's draft year.  The Wikipedia revision id and timestamp are
recorded (`1361318085`, `2026-06-27T04:11:52Z`).

## Matching rules

Identity file:
`/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv`
(2,560 rows).  Verified birthdates for 947 pids:
`/Users/kennakao/nba/datarebuild/age_verified_wiki.csv`.

Matching is done once per **FIBA person** (`playerId` is stable across
editions), not per row, so a player's tournaments cannot disagree.

1. Normalise both sides: NFKD, strip combining accents, map
   `Ø ø Đ đ Ł ł`, lower-case, drop punctuation, drop trailing
   `Jr/Sr/II/III/IV/V`, squeeze whitespace.
2. Primary key `"first last"`; if that has no identity hit, fall back
   to `"last first"` (FIBA reverses some names).
3. Candidates must satisfy **tournament year <= draft year**.
4. If FIBA lists a date of birth:
   * the player's age at at least one of his tournaments must be in
     [14, 20];
   * if the pid has a verified birthdate in `age_verified_wiki.csv`,
     the **birth years must agree exactly**, otherwise the candidate is
     rejected (this is what separates the two Justin Jacksons);
   * otherwise `draft_year - birth_year >= 16`.
5. If FIBA lists no date of birth: `0 <= draft_year - first tournament
   year <= 8`.
6. Exactly one surviving candidate -> match.  Zero or more than one ->
   written to `unmatched.csv` with the reason; never guessed.
7. Post-check: if two FIBA persons claim the same pid (there are
   several Marko Simonovics), keep the one whose birth year implies a
   normal draft age (`17 <= draft_year - birth_year <= 28`) when that
   singles one out; otherwise drop them all.  Every drop is logged.

**Second pass (legal name vs common name).** FIBA uses passport names,
so pass 1 misses `Benjamin Simmons` -> `Ben Simmons`,
`Guillermo Hernangomez` -> `Willy Hernangomez`,
`Michael Gilchrist` -> `Michael Kidd-Gilchrist`,
`Rowan Barrett` -> `RJ Barrett`.  For FIBA persons still unmatched, a
second pass requires **all** of: the FIBA date of birth equal to the
verified birthdate in `age_verified_wiki.csv` to the exact day; at least
one shared surname token; tournament year <= draft year; and an age at
some tournament in [14, 20].  Exactly one survivor -> match; more
than one -> logged as ambiguous.  A pid already claimed by pass 1 is
never reused.  This pass is only possible for the 947 pids with a
verified birthdate, and it is still an exact-key join - no fuzzy string
similarity is used anywhere.

**Draft classes without a documented cutoff.** `COLLECTOR_RULES.md`
lists draft-night cutoffs for 2000-2025.  The identity file also
contains a 2026 class; those pids get every column empty (not 0),
because without a cutoff no record can be certified pre-draft.  Add the
date to `CUTOFF` in `build.py` and re-run to fill them in.

Note that `draft_year` in the identity file is the year the player
entered the NBA universe, which for a few undrafted-then-signed players
is later than their actual draft class; the rules above therefore do
not impose an upper bound on draft age beyond the age-at-tournament
window.

Hoop Summit rows are matched on normalised name **and** draft year
(exact), with a single fallback: if the normalised name is unique in the
identity file and the identity draft year is >= the table's draft year,
the unique candidate is accepted.

## Features (`features.csv`)

All columns are numeric; empty means unknown, never 0.  Only
tournaments ending before the draft-night cutoff contribute.
"Latest" always means the last such tournament by end date.

| column | definition |
|---|---|
| `fy_has_youth` | 1 if the player has >= 1 pre-draft FIBA U15-U19 tournament in this archive, else 0.  0 is a real observation (searched, not found), subject to the coverage caveats below. |
| `fy_n_tournaments` | Number of those tournaments. |
| `fy_best_level` | Max level ladder value over them (4/3/2/1 as above). |
| `fy_age_rel_last` | Age in years at the latest tournament minus that field's mean age.  Negative = younger than the field. |
| `fy_age_rel_min` | Minimum (most negative) age-minus-field-mean over all pre-draft tournaments. |
| `fy_underage_flag` | 1 if in any pre-draft tournament the player was >= 1.0 year younger than the field mean, else 0. |
| `fy_pts40_z_last` | Points per 40 at the latest tournament, z-scored in that tournament's qualified field. |
| `fy_pir40_z_last` | FIBA efficiency (PIR) per 40 at the latest tournament, z-scored in the same field. |
| `fy_ts_z_last` | True-shooting % at the latest tournament, z-scored in the same field. |
| `fy_ast40_z_last` | Assists per 40, z-scored in the same field. |
| `fy_stl_blk40_z_last` | (Steals + blocks) per 40, z-scored against the same field's steals+blocks per 40. |
| `fy_usage_proxy_z_last` | (FGA + 0.44*FTA + TOV) per 40, z-scored in the same field. |
| `fy_best_pts40_z` | Max points-per-40 z over all pre-draft tournaments. |
| `fy_best_pir40_z` | Max PIR-per-40 z over all pre-draft tournaments. |
| `fy_z_trend` | PIR-per-40 z at the latest tournament minus PIR-per-40 z at the first.  Empty when the player has only one tournament. |
| `fy_minutes_share_last` | Minutes per game at the latest tournament / 40. |
| `fy_team_finish_last` | The player's team's final ranking at the latest tournament (1 = winner). |
| `fy_hoop_summit_world` | 1 if the player appears on a Nike Hoop Summit **World Select** roster in a year <= his draft year, 0 if he appears only on the USA roster or not at all.  Empty for draft years outside 1995-2022, which the Wikipedia table does not cover. |

`player_tournaments.csv` additionally carries, per player-tournament:
tournament id, competition id, event id, level, age group, scope,
division, year, start/end dates, games, minutes, age at tournament,
team finish, `pts40 reb40 oreb40 dreb40 ast40 stl40 blk40 tov40 pir40
usage40`, `ts efg tpar ftr ftpct`, and for each of those the
tournament field's `field_<stat>_mean` and `field_<stat>_sd`, plus
`field_age_mean`, `field_age_sd`, `field_n_roster`, `field_n_qual`.

## Coverage

### By draft-year band

| band | with FIBA youth data | drafted players | share |
|---|---|---|---|
| 2000-2007 | 38 | 582 | 6.5% |
| 2008-2018 | 212 | 1017 | 20.8% |
| 2019-2025 | 195 | 900 | 21.7% |

### US vs international

The identity file has no nationality column, so the split below uses a
read-only proxy from the frozen v4 inputs: a pid with a non-empty
`col_gp` has NCAA season data and came through US college basketball.
(`intl_gp` is unusable for this: the crude youth lines were merged into
the `intl_*` pro block, so US high-schoolers with one FIBA youth
appearance carry `intl_gp` too - exactly the contamination this block
exists to replace.)

| group | with FIBA youth data | players | share |
|---|---|---|---|
| US / NCAA-track (col_gp present) | 266 | 1867 | 14.2% |
| non-NCAA, i.e. international track | 170 | 552 | 30.8% |
| not present in the v4 inputs | 9 | 141 | 6.4% |

Among the players actually covered, FIBA nationality splits **USA 173 /
other 271** - USA Basketball sends full-strength teams to the U17 and
U19 World Cups, so this block is not an internationals-only feature.

Nike Hoop Summit: 39 pids flagged as World Select.

## Terms of service and robots

* `https://www.fiba.basketball/robots.txt` (fetched 2026-09-08)
  disallows only `/login`, `/register`, `/welcome`,
  `/forgot-password`, `/auth-callback` and their localised variants.
  Nothing under `/en/history/` is disallowed, and the file advertises
  the sitemaps this collector uses.
* FIBA Terms and Conditions section 4 is a standard copyright
  reservation over site "Content" (pictures, graphics, logos, texts,
  videos, animations, sounds, games and other works); there is no
  anti-crawling, anti-robot or rate clause.  This collector keeps the
  fetched pages only as a local cache for reproducibility and publishes
  only derived numeric aggregates, no FIBA text, images or video.
* Requests: one connection, >= 1.1 s apart, exponential backoff with
  jitter on 429/500/502/503/504, descriptive User-Agent
  `DraftDB-Research/1.0 (non-commercial NBA draft research; contact
  mike@alphax.inc)`.  No login, no paywall, no JS challenge, no
  Cloudflare bypass: the pages are plain server-rendered HTML.
* Wikipedia is read through the public MediaWiki API with the same
  User-Agent; content is CC BY-SA and only two derived bits are kept.
* Sites the project bans (sports-reference, kenpom, synergy, realgm,
  proballers, eurobasket.com, legabasket, tblstat, acb.com, nikeeyb,
  EYBL) were **not** contacted.

## Known limitations

1. **Archive depth.** FIBA's per-player box scores thin out before the
   mid-2000s: some editions from 2000-2004 list rosters without dates
   of birth or without per-player totals.  A player with no DOB gets no
   age-relative feature (empty, not 0) even when his rate stats parse.
   This is why the 2000-2007 draft band is much thinner than the later
   ones - it is a source-coverage effect, not a signal.
2. **`fy_has_youth = 0` is asymmetric across eras** for the same
   reason.  Any model using it should be aware that a 2001 draftee's 0
   is weaker evidence than a 2021 draftee's 0.
3. **The Hoop Summit source stops at the 2022 draft** (the Wikipedia
   article carries a `Missing information: 2023-2025 NBA drafts` tag),
   so `fy_hoop_summit_world` is empty for those draft years rather than
   0.  It is also derived from a table of *drafted* alumni, which is
   fine here because the universe is drafted players, but it would not
   generalise to undrafted prospects.
4. **Name matching is conservative.** Players whose name normalises to
   more than one identity row, or whose FIBA birth year contradicts the
   verified birthdate, are dropped and logged rather than guessed, so
   coverage is a slight under-count.
5. **Final ranking is a team outcome**, not a player one, and small
   fields (some zone events have 4-6 teams) make it a coarse variable.
6. **Division B/C and zone events have weak fields**, so a big z-score
   there is worth much less than the same z at a U19 World Cup;
   `fy_best_level` is provided so a model can interact the two.

## Running and resuming

```sh
cd /Users/kennakao/nba/datarebuild/novel/fiba_youth
nohup python3 -u crawl.py >> run.log 2>&1 &   # crawl (resumable)
python3 hoop_summit.py                        # Wikipedia, seconds
python3 build.py | tee build.log              # features from cache
python3 make_readme.py                        # regenerate this file
```

`crawl.py` checkpoints one JSON per tournament in `raw/parsed/`; an
event whose file exists with `"complete": true` is skipped, and every
HTTP response is cached under `raw/pages/`, so re-running after an
interruption costs only the un-fetched pages.  `crawl.py <prefix>`
restricts the run to competitions whose slug starts with `<prefix>`.
`build.py` reads only the cache and can be re-run at any time, including
while the crawl is still going - it simply reports whatever is on disk.

To stop the crawl, find it with `pgrep -f 'python3 -u crawl.py'` and
kill that pid only (never a broad pattern).
