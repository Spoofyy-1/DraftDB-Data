# torvik_context — season-level college POPULATION and TEAM context

Novel-data collector for the NBA redraft model. Our current model inputs already carry each
prospect's *own* Torvik season line (the `tv_` columns in
`v4_build/data_v4/train_2000_2018.csv`). What they lack is the context that line sits in: how he
compared with every other D1 player his age that season, how much of his team he was, how good his
team and conference were, how available he stayed, and how he developed. This collector builds that
from Bart Torvik's two full-league CSV exports.

Everything here is derived from seasons with `year <= draft_year`, so every column is knowable on
draft night. Torvik's `pick` column — which tags a player with the NBA pick he would later become —
is dropped the moment the CSV is parsed and is used nowhere, not even for matching.

## Outputs

| file | contents |
|---|---|
| `features.csv` | 1,716 rows: `pid` + **110 numeric `tc_` columns**. Missing is empty, never 0. |
| `feature_dictionary.csv` | one row per `tc_` column: definition, fit window / leakage note, what an empty cell means. |
| `unmatched.csv` | `pid, draft_year, actual_pick, reason, n_name_candidates` for every prospect with no Torvik season (no names — join to the identity file locally). |
| `match_notes.csv` | the 6 prospects where data_v4's own `tv_` line points at a *different* Torvik player than this collector accepts (see "Findings"). |
| `provenance.csv` | one row per cached CSV: source URL, season, row count, bytes, sha256, fetch time, robots/UA terms. |
| `raw/` | 38 cached CSVs (124 MB), `adv_YYYY.csv` and `games_YYYY.csv` for 2008–2026. Re-runs are fully offline. |
| `run.log` | the last full run's output (verification, leakage checks, coverage, top-10 definitions). |
| `build.py`, `fetch_raw.py` | the collector. `python3 fetch_raw.py` (resumable, skips cached files) then `python3 build.py`. |

Both scripts are pure Python 3 + pandas/numpy and run in ~40 s from the cache. Nothing outside this
directory is written.

## Sources and terms

| endpoint | what it returns |
|---|---|
| `https://barttorvik.com/getadvstats.php?year=YYYY&csv=1` | every D1 player-season, 67 unlabelled columns, ~4.6–4.8k rows/season, 2008–2026 (90,739 rows total) |
| `https://barttorvik.com/getgamestats.php?year=YYYY&csv=1` | every team-game, 31 unlabelled columns, ~11k rows/season (206,196 total) |

`https://barttorvik.com/robots.txt` (read 2026-09-08) disallows `db.php`, `box.php`, `results.php`,
`playerstat.php`, `teamcast.php`, the `*-time-machine.php` pages and `/*.json`. **Neither export is
disallowed.** The `User-agent: *` block sets `Crawl-Delay: 10`, which `fetch_raw.py` honours: one
request every 10 s, exponential backoff on failure, descriptive User-Agent
(`DraftDB-research/1.0 (contact: mike@alphax.inc) non-commercial NBA draft research`). No disallowed
path is ever requested, no login, paywall or JS challenge is involved. Total: 38 requests, once.

## Inferred column mapping

The exports have no header row and the order is undocumented. It was inferred from the toRvik
package's field list, from Zion Williamson's known 2019 line, and from arithmetic identities inside
each row, then verified three independent ways (all printed by `build.py`).

### `getadvstats.php` — 67 columns

| # | name | # | name | # | name | # | name |
|---|---|---|---|---|---|---|---|
| 0 | player_name | 17 | twoPA | 34 | **rec_rank_raw** | 51 | obpm |
| 1 | team | 18 | twoP_per | 35 | ast_tov | 52 | dbpm |
| 2 | conf | 19 | TPM | 36 | rimmade | 53 | gbpm |
| 3 | GP | 20 | TPA | 37 | rimatt | 54 | **mpg** |
| 4 | Min_per | 21 | TP_per | 38 | midmade | 55 | ogbpm |
| 5 | ORtg | 22 | blk_per | 39 | midatt | 56 | dgbpm |
| 6 | usg | 23 | stl_per | 40 | rim_pct | 57 | oreb (per game) |
| 7 | eFG | 24 | ftr | 41 | mid_pct | 58 | dreb |
| 8 | TS_per | 25 | yr (class) | 42 | dunkmade | 59 | treb |
| 9 | ORB_per | 26 | ht | 43 | dunkatt | 60 | ast |
| 10 | DRB_per | 27 | num (jersey) | 44 | dunk_pct | 61 | stl |
| 11 | AST_per | 28 | porpag | 45 | **pick — DROPPED** | 62 | blk |
| 12 | TO_per | 29 | adjoe | 46 | drtg | 63 | pts |
| 13 | FTM | 30 | pfr | 47 | adrtg | 64 | role |
| 14 | FTA | 31 | year | 48 | dporpag | 65 | **tpa_per100** |
| 15 | FT_per | 32 | tpid (Torvik player id) | 49 | stops | 66 | **birthdate** |
| 16 | twoPM | 33 | hometown | 50 | bpm | | |

Four columns deserve a note.

* **34 `rec_rank_raw` is a score, not a rank.** It is a descending scale in steps of 0.2 with
  100.0 for the class's #1 recruit; only ~28% of player-seasons carry it. The ordinal rank is
  `501 - 5 * value`, which the builder stores as `rec_rank`. Evidence: in season 2019 the values
  100.0 / 99.8 / 99.6 / 99.4 / 99.2 belong to R.J. Barrett, Cam Reddish, Nassir Little, Bol Bol and
  Zion Williamson — the Rivals 2018 top five in order. (The task brief expected Zion to decode to
  rank 2; under this linear map, and under Rivals' own ordering, he is #5. The decoding is confirmed
  independently by `tc_tm_recrank_best = 1` for Zion, i.e. his best-ranked teammate is Barrett.)
* **45 `pick` is post-draft leakage** — the NBA pick the player later became, present on ~2% of
  rows. `build.py` drops it in `load_players()` and never reads it.
* **65 `tpa_per100` is three-point attempts per 100 team possessions.** Identified because
  `col65 / (TPA * 40 / minutes)` equals `100 / team tempo` for every row (Cornell 2019 tempo 70.8 →
  1.412; American 2019 tempo 67.8 → 1.476). It is the one shot-mix quantity not already in the
  `tv_` block, so it is passed through as `tc_tpa_per100`.
* **66 `birthdate` is filled with October 15 when the exact date is unknown** (27% of 2019 rows are
  `YYYY-10-15`, versus ~0.4% for any other month-day). The year still encodes the class-implied
  birth year, so ages remain usable; `tc_age_imputed` flags them.

### `getgamestats.php` — 31 columns

`0 date, 1 gtype, 2 team, 3 conf, 4 opp, 5 venue (H/A/N), 6 result ("W, 67-55"), 7 g_adjo,
8 g_adjd, 9-13 offensive four factors (ppp, eFG, TO%, OR%, FTR), 14-18 defensive four factors,
19 game_score (0-100 performance rating, monotone in adj_o - adj_d), 20 opp_conf, 21 side,
22 year, 23 tempo, 24 gameid, 25 coach, 26 opp_coach, 27 adj_margin, 28 opp_barthag,
29 box_json, 30 misc`.

`gtype` is `0` non-conference, `1` conference regular season, `2` conference tournament,
`3` **postseason tournament — NCAA *and* NIT/CBI/CIT** (142 teams in 2019, not 68). Column 28 is the
*opponent's* end-of-season Barthag, which is how each team's own Barthag is recovered (read it off
the rows where that team is the opponent).

## How the NCAA tournament is isolated

Torvik does not label which postseason tournament a `gtype 3` game belongs to, and it carries no
seeds. Rule used: build the team graph of all `gtype 3` games and take the **largest connected
component**. Tournament fields are disjoint — no team plays in two — so every component is exactly
one tournament, and the NCAA field is always the largest (NIT is a clean 32 second). Champion =
winner of the single game on the component's last date; Final Four = the teams playing on the
previous date with games.

This reproduces the correct field size and the correct champion and Final Four for every season
2008–2026: 65 teams in the 2008–2010 play-in era, 68 from 2011, 67 in 2021 (VCU's no-contest), and
none in 2020. Champions for 2008–2025 come out as Kansas, North Carolina, Duke, Connecticut,
Kentucky, Louisville, Connecticut, Duke, Villanova, North Carolina, Villanova, Virginia, —, Baylor,
Kansas, Connecticut, Connecticut, Florida — all correct.

**Seeds are not recoverable** from this export. There is no seed field, no region field, and a
bracket graph without labels cannot be seeded (the R64 seed-sum-17 structure is unidentifiable
without knowing which side of each pairing is which). In its place `tc_ncaa_wins_expected` regresses
tournament wins on a cubic in `log(end-of-season Barthag rank)`, fitted on tournament teams from
seasons **strictly before** the draft year, and `tc_ncaa_wins_resid` is the actual minus expected —
the same "did the team beat its seeding expectation" signal, sourced from a rating rather than a
seed. If seeds are wanted later they would have to come from another source.

## Matching prospects to Torvik players

Our pid-keyed inputs carry no college team name, so the brief's "normalised name + team" is
implemented as **normalised name + draft-year plausibility + independent corroboration**.

Normalisation strips accents and punctuation, lower-cases, and removes the suffixes Jr/Sr/II/III/IV/V.
Two keys are generated per name — the plain one and the one with a run of single-letter initials
joined — so `C.J. Williams` and `CJ Williams` both resolve.

Candidates for a prospect with draft year Y come from those keys, plus one more source: an exact
match of data_v4's own `tv_` line on `(adjoe, adrtg, stops)` rounded to 3 dp, which pins a unique
player-season. Then, in order:

1. keep candidates with a Torvik season in `[Y-7, Y]`;
2. **drop** any candidate whose non-imputed Torvik birthdate differs from the verified Wikipedia
   birthdate (`age_verified_wiki.csv`) by more than 400 days;
3. if exactly one candidate's birthdate agrees within 2 days, take it (`tc_match_rule = 3`);
4. else if exactly one candidate's final season matches data_v4's independent college source on
   *both* games played and minutes per game (`col_gp`, `col_mpg`), take it (`tc_match_rule = 4`);
5. else if exactly one candidate's final pre-draft season equals Y, take it (`tc_match_rule = 5`);
6. else if exactly one candidate survives, take it (`tc_match_rule = 2`);
7. else log `ambiguous_name` to `unmatched.csv` and emit nothing — never guess.

A prospect who ends up with **no** candidate gets one further pass, because Torvik carries the
college's given name where the identity file carries the NBA nickname. Candidates are the Torvik
players sharing his surname with a season in `[Y-7, Y]`, and one is accepted only if it is the *only*
one corroborated by the verified birthdate (within 2 days) or by exact `col_gp` **and** `col_mpg`
agreement (`tc_match_rule = 6`). This recovers 14 players, every one of them correct on inspection:
Bam Adebayo (Torvik: Edrice Adebayo), Mo Bamba (Mohamed), Bones Hyland (Nah'Shon), Cam Thomas
(Cameron), Bub Carrington (Carlton), Svi Mykhailiuk (Sviatoslav), Bill Walker (Henry), Kay Felder
(Kahlil), Joe Young (Joseph), Wes Iwundu (Wesley), Maurice/Moe Harkless, Jeff/Jeffery Taylor, Devyn
Marble (Roy Devyn) and Tony L. Mitchell. Nine of them, including Hyland and Thomas, have no Torvik
line at all in data_v4.

The cascade resolves 1,015 rows as a single surviving candidate (`tc_match_rule = 2`), 644 by
verified birthdate, 39 by `col_gp`/`col_mpg`, 4 by final-season-equals-Y and 14 by the surname pass; exactly one prospect (Mamadou Ndiaye, undrafted
2016, two D1 players of that name) stays ambiguous.

Thresholds are calibrated, not chosen: among 609 single-candidate prospects with a verified
birthdate, 591 agreed to the day and only one differed by more than a year (a genuine impostor,
5,835 days). Step 4's rule is worth its place because Torvik's final season and data_v4's college
source agree exactly on both GP and mpg for 99.7% of confidently matched players.

The final pre-draft season **F** is the player's last Torvik season with `year <= Y`.
`tc_match_tv_agrees` records whether the accepted player is the one data_v4's `tv_` columns point at.

## Feature families

`feature_dictionary.csv` has all 110 definitions. The design:

1. **Cohort percentiles and age curves** (`tc_pct_age_*`, `tc_resid_age_*`, `tc_z_age_*`) for bpm,
   obpm, dbpm, usg, TS, AST%, STL%, BLK%, ORB%, DRB% and porpag. The percentile is taken within
   `(season F, floor(age))` among D1 players with `Min_per >= 40` — a same-season population, which
   is causal because season F ends in April and the draft is in June. The residual is against a
   cubic `stat ~ age` fitted on `Min_per >= 40` player-seasons from seasons **strictly before Y**,
   refit for every draft year (expanding window), with age clipped to the fit population's 0.5/99.5
   percentiles. Age is measured at the season midpoint, 15 January.
2. **Team shares and teammate quality**: share of the team's positive-BPM minutes, of usage, points,
   assists and porpag; leave-one-out minutes-weighted teammate BPM and usage; best and top-2
   rotation teammate BPM (`Min_per >= 20`, because tiny-minute BPM reaches +141); best teammate
   recruiting rank and the count of top-100 recruits alongside him; a Herfindahl index of talent
   concentration.
3. **Team and conference strength**: minutes-weighted positive-BPM sum of the five on the floor,
   roster adjusted O and D ratings, conference strength in season F and in F-1 (the same conference
   membership, evaluated a year earlier), plus record, Barthag and rank, schedule strength, NCAA and
   conference-tournament results and the seed-expectation residual described above.
4. **Availability**: games played over team games for season F, over the whole career, and the worst
   single season; a count of whole missing seasons inside the career window and a flag for one
   between two seasons at the same school (redshirt / season-ending injury proxy).
5. **Development and precocity**: minutes-weighted least-squares slopes of bpm, usg, TS, AST%, STL%,
   BLK% and Min_per across his seasons, shrunk `n/(n+2)` toward the mean raw slope of **earlier
   draft classes**; BPM second difference; first-season BPM, age, minutes share and usage;
   age-adjusted freshman-BPM z. Shooting: career FT% and 3P% shrunk to a method-of-moments beta
   prior fitted on his *role's* player-seasons from years before Y with >= 20 attempts (all-D1
   fallback when the role is unknown, which is every 2008–09 season).
6. **Shot mix**: dunks and dunk attempts per 40, dunk %, rim attempts per 40, and 3PA per 100
   possessions. Rim/mid/three *shares* are already in `tv_` and are not duplicated.
7. **Scoring-overpay residuals**: points per 40 minus its same-season OLS prediction from usage and
   TS, and TS minus its same-season OLS prediction from usage, both fitted on that season's
   `Min_per >= 40` population.

## Verification of the mapping

`build.py` prints all three checks on every run.

**(a) Nine known player-seasons, 87 field assertions, all pass** — Zion Williamson 2019 (27 fields
including every rate, every make/attempt pair, jersey and birthdate), Kevin Love 2008, Blake Griffin
2009, Anthony Davis 2012, Buddy Hield 2016, Trae Young 2018, Ja Morant 2019, Cade Cunningham 2021,
Zach Edey 2024. Per-game counting stats are checked at a 3% tolerance because Torvik's universe is
D1 opponents only: Morant shows 31 games of his 33, and Murray State's team-game count is likewise
31, so the two sides stay consistent with each other.

**(b) Ten arithmetic identities over all 90,739 player-seasons, all at 100.00%** — `treb = oreb +
dreb`, `bpm = obpm + dbpm`, `gbpm = ogbpm + dgbpm`, the five made/attempted percentage pairs
(FT, 2P, 3P, rim, mid, dunk), and `eFG` from the makes.

**(c) 1,229 player-seasons cross-checked against the `tv_` columns already in data_v4**, an
independent parse of the same feed. All 31 checked pairs agree, 30 of them on >= 99.9% of rows.
`tv_jersey` differs on 18 rows — data_v4's jersey value comes from a different season of the same
player (Kyle Anderson's UCLA 5 vs a later 13, and similar) — which is a data_v4 quirk, not a
mapping question.

## Coverage

`features.csv` covers 1,716 of the 2,560 prospects in the identity file (which runs through the
2026 class).

| draft-year band | prospects | matched | rate | mean cell fill |
|---|---|---|---|---|
| 2000–2007 | 582 | 0 | 0.0% | — |
| 2008–2018 | 1,017 | 870 | 85.5% | 94.6% |
| 2019–2025 | 900 | 791 | 87.9% | 96.6% |
| 2026 (bonus) | 61 | 55 | 90.2% | 96.0% |

Per draft year (matched / prospects, mean share of non-empty `tc_` cells):

| 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 |
|---|---|---|---|---|---|---|---|---|
| 52/70, 62% | 60/71, 91% | 68/79, 96% | 75/88, 96% | 74/86, 97% | 76/91, 98% | 76/90, 98% | 70/81, 97% | 88/104, 98% |

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| 118/132, 97% | 113/125, 97% | 120/137, 98% | 96/112, 92% | 221/233, 97% | 83/97, 97% | 83/101, 97% | 96/114, 97% | 92/106, 97% |

The 844 unmatched break down as 582 prospects drafted before Torvik's data begins (2000–2007, all
empty as expected), 261 with no D1 season at all in 2008–2026, and 1 ambiguous name. The 261 are the
international and non-college route: Ricky Rubio, Brandon Jennings, Dario Šarić, Alperen Şengün,
Victor Wembanyama, Scoot Henderson, LaMelo Ball, Jalen Green, Shaedon Sharpe (signed at Kentucky but
never played a game) and so on — 162 of them drafted, 99 undrafted. Every one of the 41 remaining
unmatched first-round picks from 2019 on was checked by hand: all are international, G League
Ignite, Overtime Elite or NBL routes, so there is no false negative left in the first round.

## Findings worth passing on

* **data_v4 has at least six wrong Torvik matches**, listed in `match_notes.csv`. The one that
  matters is **Tristan Thompson (2011, pick 4)**: his `tv_` columns hold the season of a *different*
  Tristan Thompson, at North Texas (31 games, 32.3 mpg), while the real one played at Texas (36
  games, 30.9 mpg). data_v4's own `col_gp`/`col_mpg` and the verified birthdate (1991-03-13) both
  agree with Texas, so its `tv_` block and its `col_` block currently disagree with each other for
  him. The other five are undrafted players with common names (Chris Wright, Tony Mitchell, two
  Chris Smiths, Malachi Smith). This collector uses the corrected matches.
* **Nine draftees have no Torvik line at all in data_v4** that this collector does match, because
  Torvik files them under their given name — Bones Hyland and Cam Thomas among them. Worth folding
  back into the `tv_` block.
* **Torvik's 2008 and 2009 counting stats are unreliable.** Stephen Curry's 2009 line shows 127
  made threes on 327 attempts against an actual 162/384. The row is internally consistent (its
  `pts` reconstructs exactly from its own makes), so the aggregation, not the parse, is short. Rate
  stats and BPM for those seasons look sound. Treat `tc_ft_shrunk`/`tc_3p_shrunk` for the 2009–2010
  draft classes with care.

## Known gaps and limitations

* **2000–2007 is empty by construction.** Torvik's first season is 2008.
* **No assisted-shot share.** The 67 columns were enumerated and none carries assisted/unassisted
  splits; Torvik exposes them only through `playerstat.php`, which robots.txt disallows. The model
  inputs already carry `col_hm_assisted_*` from another source. Nothing is emitted here.
* **No tournament seeds** — see the section above; `tc_ncaa_wins_resid` is the substitute.
* **No shot-location data before season 2010**, so `tc_dunks_per40`, `tc_dunk_att_per40`,
  `tc_dunk_pct` and `tc_rim_att_per40` are empty for the 2008–2009 classes, and `role` is missing
  for those seasons, which sends their shooting priors to the all-D1 fallback.
* **The 2008 draft class is thin** (62% cell fill): one Torvik season means no career, no slopes,
  and no prior-season population for the age curves or the beta priors.
* **2020 has no NCAA tournament.** `tc_ncaa_*` is empty for that class rather than 0, since 0 would
  assert the team missed a bracket that never existed.
* **27% of Torvik birthdates are the October-15 filler.** Ages are still class-consistent (which is
  exactly the brief's fallback), and `tc_age_imputed` marks them. Ages come from Torvik on both
  sides of every percentile and curve so the population stays internally consistent; the verified
  Wikipedia birthdates are used for matching only.
* **GP is D1-games-only** on both sides of every availability ratio, so `tc_gp_share_*` is internally
  consistent but is not literally the player's share of his team's full schedule.
* **`tc_match_rule = 4` rows lean on data_v4's college match.** That source is right 99.7% of the
  time but it is not independent of data_v4's own errors; the column is emitted so those rows can be
  dropped if a future check wants only birthdate-confirmed matches.

## Re-running

```
cd /Users/kennakao/nba/datarebuild/novel/torvik_context
python3 fetch_raw.py      # only needed to add a season; skips anything already in raw/
python3 build.py          # ~40 s from cache; rewrites features.csv, feature_dictionary.csv,
                          # unmatched.csv, match_notes.csv and prints all verification + coverage
```

`fetch_raw.py` is resumable and idempotent: a cached file larger than 1 KB is never re-requested, so
a re-run costs zero network traffic. To pick up the next season, extend `SEASONS` in both scripts.
