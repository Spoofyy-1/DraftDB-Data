# gamelogs — game-level college features from ncaahoopR_data (`gl2_` prefix)

Per-game NCAA Division I box scores for every drafted player in the identity file, turned into
opponent-quality splits, an NCAA-tournament residual, consistency/trend, availability, and
clutch/role features.

* `features.csv` — 1,691 rows, `pid` + **147 numeric columns**, one row per pid, missing = empty.
* `unmatched.csv` — every pid/season we could not use, with the reason.
* `provenance.csv` — sources, URLs, access method, terms, retrieval dates.
* `raw/` — offline cache: `box_<season>.csv.gz`, `schedules.csv.gz`, `rosters.csv.gz`,
  `wiki/<year>_<mode>.json`, `tree.txt`, and `ncaa_repo/` (a blobless shallow clone; re-runs
  need no network).
* `work/` — intermediates: `games.csv.gz`, `team_ratings.csv`, `player_seasons.csv`,
  `match_log.csv`, `tourney_games.csv`, `tourney_team.csv`, `seeds.csv`, `seeds_provenance.csv`.
* `run.log` — the background download log.

## Pipeline (run in this order; every step is idempotent and offline after the first run)

```
python3 consolidate.py      # sparse-checked-out schedules/rosters -> raw/*.csv.gz
python3 build_ratings.py    # game linkage + team ratings          -> work/games.csv.gz, work/team_ratings.csv
python3 match_players.py    # pid -> (season, team)                -> work/player_seasons.csv, work/match_log.csv
python3 fetch_boxes.py      # box scores for those team-seasons    -> raw/box_<season>.csv.gz   [network]
python3 fetch_seeds.py      # Wikipedia brackets                   -> work/seeds.csv            [network]
python3 build_tourney.py    # NCAA field/seeds/PASE                -> work/tourney_*.csv
python3 build_features.py   # everything above                     -> features.csv, unmatched.csv
```

`fetch_boxes.py` is the only long job. It is checkpointed per season (a season whose
`raw/box_<season>.csv.gz` exists is skipped), so **to resume it just re-run it**:
`cd /Users/kennakao/nba/datarebuild/novel/gamelogs && nohup python3 fetch_boxes.py >> run.log 2>&1 &`.
It completed in ~75 s on this machine (24 seasons, 79,749 team-games, 871,644 player-game rows,
13 MB gzipped) because the blobless clone lets one `git checkout` per season pull all of that
season's blobs in a single packfile request. To widen the set of team-seasons, edit
`work/player_seasons.csv` (or re-run `match_players.py`), delete the affected
`raw/box_<season>.csv.gz`, and re-run.

## Source

[`lbenz730/ncaahoopR_data`](https://github.com/lbenz730/ncaahoopR_data) (MIT) — ESPN play-by-play,
box scores, rosters and schedules for D-I, seasons 2002-03 … 2025-26, laid out as
`<season>/box_scores/<Team>/<game_id>.csv`, `<season>/schedules/<Team>_schedule.csv`,
`<season>/rosters/<Team>_roster.csv` (rosters exist from 2008-09). Play-by-play was **not**
downloaded. The repo is multi-GB, so we never cloned it whole: a
`git clone --filter=blob:none --depth 1 --no-checkout` (9.6 MB) gives the entire file tree
offline, and sparse-checkout then fetches only the ~2,500 team-season directories we need.

### Opponent linkage — no name matching
A `game_id` appears in **both** teams' schedule files, so the opponent of every game is resolved
exactly, in team-directory space (90.2% of game ids have both sides in the archive; the rest are
games against non-D-I opponents). Opponent *display* names are never string-matched.

## Team strength for the opponent tiers (documented choice)

| seasons | source | how |
|---|---|---|
| ending 2008 – 2026 | **Bart Torvik end-of-season team ratings**, `https://barttorvik.com/<year>_team_results.csv` (already cached under `datarebuild/tracking_raw/torvik_team_*.csv`; no new requests were made) | teams ranked by `barthag`; rank ≤ 50 = top-50, ≤ 100 = top-100 |
| ending 2003 – 2007 | **archive-derived ridge margin rating** (Torvik starts in 2008) | ridge/Massey least squares on point margin over all D-I-vs-D-I games in `raw/schedules.csv.gz`, with a home-court term, margins capped at ±22 and λ = 25; teams ranked by rating |

`barttorvik.com/getgamestats.php` (the endpoint named as permitted) was fetched once for 2019 to
check whether it carries seeds — it does not — and is **not** used. `playerstat.php`, `box.php`,
`*.json`, kenpom and sports-reference.com were never touched.

Team-directory ↔ Torvik name resolution lives in `teams.py` (normalisation + directional/state
expansions + an explicit alias table). **99.6%** of Torvik team-seasons map, and **zero**
Torvik teams ranked in the top 150 of any season fail to map, so the tier cut is not distorted by
name misses. Teams present in the archive but absent from Torvik (IUPUI, Houston Baptist, …) are
ranked 999 — all are far outside the top 100 by the archive rating too.

Cross-check of the two rating systems over the 19 overlapping seasons: Spearman ρ = 0.84–0.94
(median 0.92), top-50 set overlap 31–42 / 50, top-100 overlap 70–85 / 100. `gl2_tier_src_torvik`
records, per player, the share of that season's opponents whose tier came from Torvik (1.0 for
seasons ending 2008+, 0.0 before), so the era difference is visible to the model.

Opponents that are not in the archive (non-D-I buy games) are treated as **outside** the top 100
but still count in "all games".

## Dating rule (pre-draft only)

Every box-score row is dropped unless its **game date** is strictly before that player's
draft-night cutoff (the table in `COLLECTOR_RULES.md`; 2026 uses 2026-06-24, extrapolated).
No feature is computed from a season label. In practice NCAA seasons end in early April and every
draft is in June (2020: 18 November), so the filter is not binding — it is applied anyway.

Team ratings, tournament fields and seeds are all determined on Selection Sunday / the end of the
same NCAA season, i.e. months before the draft that uses them. **One documented deviation:**
the Wikipedia bracket articles for 2003, 2004, 2005 and 2011 did not yet contain a
machine-readable bracket at the June cutoff (they used ASCII-art brackets), so for those four
years the *current* revision was parsed instead. `work/seeds_provenance.csv` records the mode,
revision id and timestamp for every year (18 of 22 are pre-draft revisions). The underlying fact —
which seed a team received — was public in March of that season, so no post-draft information
enters; only the transcription is later.

## NCAA tournament detection

Field and seeds come from the Wikipedia bracket templates: each `{{NTeamBracket}}` chunk yields
`RD1-team<i>` entries, seeded either by an explicit `RD1-seed<i>` or (the 2008-2010 style) by the
template's fixed first-round order `[1,16,8,9,5,12,4,13,6,11,3,14,7,10,2,15]`. Names are mapped to
team directories with the same `teams.ekey` resolver (1,429 / 1,474 = 97%; the residue is teams
absent from the archive that season).

A tournament game is any archive game played on/after **Selection Sunday + 2 days** (First Four
Tuesday; Selection Sunday = the unique Sunday in [Mar 11, Mar 17] of the season-ending year) in
which **both** sides are in that year's field. Conference tournaments end on Selection Sunday and
the NIT/CBI/CIT fields are disjoint from the NCAA field, so no date-window guessing is needed and
neutral-site flags (absent before 2007-08) are not required.

**End-to-end check: the champion this produces is the correct NCAA champion in all 22 detected
seasons** (Syracuse 2003 … Florida 2025). 2020 is empty (tournament cancelled) and 2025-26 is
incomplete in the archive.

### PASE (wins above seed expectation)
Expected wins for a seed are estimated on **prior tournaments only**: for a tournament in year *Y*
the table is the mean wins per seed over every detected tournament with year < *Y*
(leave-future-out). Before three prior tournaments are available the fallback is the published
1985-2002 seed means in `build_tourney.py:PRIOR_SEED_WINS`. `gl2_pase = wins − expected`, split
into `gl2_pase_pos = max(pase,0)` and `gl2_pase_neg = min(pase,0)`.

## Identity matching (rule-based; ambiguity is logged, never guessed)

Names are normalised (accents stripped, punctuation removed, Jr/Sr/II/III/IV/V dropped, lower-cased).
Candidate `(season, team)` pairs for a pid come from, in priority order:

1. **rosters** (2008-09 →): exact normalised full-name match, season-ending year in `[draft_year−5, draft_year]`.
2. **Torvik player table** (2008 →): normalised full name; team mapped through `teams.ekey`.
3. **Wikipedia infobox `college`** (all years): `[[Link|College]] (YYYY–YYYY)` parsed by regex, the
   year span intersected with the plausible window. Used alone for pre-2008 drafts, and as the
   tie-breaker when 1/2 disagree.

A pid is dropped if its latest evidence season is more than one year before the draft
(`stale_last_season`) or if two teams remain for the same season (`ambiguous_team`).

**Box-score confirmation.** ESPN box scores abbreviate names (`Z. Williamson`, `C.J. Fair`,
`R. Powell Jr.`). A row is the player's when the surname matches and the box initials are a prefix
of the player's first name; where several variants match, the one whose initials match *exactly*
wins, and variants that appear **in the same game** are treated as different people and the pid is
rejected (`ambiguous_box_name` — e.g. Marcus vs Markieff Morris at Kansas). Where a roster exists,
two roster players with the same surname and first name also reject the pid
(`ambiguous_roster_name`). A player-season needs ≥ 2 games to be kept.

The 2003-2008 ESPN dumps corrupt some names by appending the initial/position or doubling the
string (`K. DurantK`, `C. PaulC. PaulG`, `A. HorfordA`). `clean_box()` collapses a doubled prefix
and strips a trailing capital that follows a lower-case letter. This recovers ~60 additional
players (Kevin Durant, Al Horford, Chris Paul, …).

**Rows with `MIN = "NA"`** are counted as not played and reported in `gl2_dnp_rows`; the archive
uses NA both for true DNPs and for missing minutes, and the two cannot be told apart.

## Availability denominators

The observable team schedule is the set of games the archive actually has a **box score** for —
using the schedule file instead would turn archive gaps into phantom missed games.
`gl2_team_g` is that count, `gl2_team_g_sched` the schedule count and `gl2_box_completeness`
their ratio (mean 0.94–1.01 per season, 0.39 for the partial 2025-26 season).

## Feature definitions

`GmSc` is Hollinger's game score:
`PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM) + 0.7·OREB + 0.3·DREB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TO`.
"per-40" is `40 · total / total minutes` over the games in the subset (not a mean of per-game rates).
Unless stated, features describe the **final pre-draft season** — the latest season with ≥ 2
matched games before the cutoff; `_car` suffixes aggregate over every matched season.

**Meta**

| column | definition |
|---|---|
| `gl2_final_season_end` | season-ending year of the season the features describe |
| `gl2_final_is_predraft_season` | 1 if that year equals the draft year (0 = the draft-year season is missing from the archive) |
| `gl2_n_seasons` | matched college seasons with usable box data |
| `gl2_seasons_no_archive` | matched seasons that produced no usable box data |
| `gl2_season_gaps` | seasons between the first and last matched season with no data |
| `gl2_tier_src_torvik` | share of the season's opponents whose tier rank came from Torvik |
| `gl2_box_completeness` | box-covered team games ÷ scheduled team games |

**1 — opponent-quality splits.** `gl2_g_all`, `gl2_g_t100`, `gl2_g_t50` = games vs all / top-100 /
top-50 opponents. Season aggregates: `gl2_mpg`, `gl2_ppg`, `gl2_gmsc_pg`, per-40
`gl2_{pts,reb,ast,stl,blk,tov,gmsc}40`, efficiency `gl2_{fg,fg3,ft,ftr,efg,ts}`. The same
per-game block restricted to each tier (≥ 3 games required):
`gl2_t100_{mpg,ppg,rpg,apg,spg,bpg,topg,gmsc,fg,fg3,ft,ftr,efg,ts}` and `gl2_t50_*`.
Deltas (tier **minus overall**): `gl2_d100_{pts,reb,ast,stl,blk,tov,gmsc}40`,
`gl2_d100_{fg,fg3,ft,ftr,efg,ts}`, `gl2_d100_mpg`, and `gl2_d50_*`.

**2 — NCAA tournament residual.** `gl2_ncaa_g` (tournament games the player played),
`gl2_team_ncaa_w` (team wins), `gl2_seed`, `gl2_exp_wins`, `gl2_pase`, `gl2_pase_pos`,
`gl2_pase_neg`, `gl2_final4`, `gl2_champion`. Per-40 tournament-minus-regular-season deltas
(≥ 2 tournament games): `gl2_ncaa_d_{pts,ast,reb,stl,tov,gmsc}40`, `gl2_ncaa_d_mpg`,
`gl2_ncaa_d_ts`. Career: `gl2_ncaa_g_car`, `gl2_ncaa_w_car`, `gl2_final4_car`,
`gl2_champion_car`, `gl2_best_seed_car`.

**3 — consistency and trend.** `gl2_gmsc_mean`, `gl2_gmsc_sd`, `gl2_gmsc_skew` (sample skewness),
`gl2_gmsc_cv`; `gl2_share_gmsc_above_1sd` / `gl2_share_gmsc_below_1sd` = share of games more than
one SD above / below the season mean. Last-10-games minus season (needs ≥ 14 games):
`gl2_last10_d_{pts,gmsc}40`, `gl2_last10_d_mpg`. Late (on/after 1 Feb) minus early (needs ≥ 5 each
side): `gl2_late_d_{pts,gmsc,ast,reb}40`, `gl2_late_d_mpg`, `gl2_late_d_ts`.

**4 — availability.** `gl2_gp`, `gl2_team_g`, `gl2_team_g_sched`, `gl2_avail` = gp ÷ team games,
`gl2_missed`, `gl2_dnp_rows`. `gl2_absence_blocks` = runs of ≥ 3 consecutive team games missed
where the player averaged ≥ 15 minutes in the ≤ 5 played games immediately before **and** after
the run (≥ 2 games required on each side, so a season-opening or season-ending absence does not
count); `gl2_absence_max_len` is the longest such run. Career: `gl2_gp_car`, `gl2_team_g_car`,
`gl2_avail_car`, `gl2_absence_blocks_car`; whole missing seasons are `gl2_season_gaps` and
`gl2_seasons_no_archive`.

**5 — clutch and role.** `gl2_min_share` = player minutes ÷ team minutes (≈ 0.20 is a 40-minute
player), `gl2_start_share`. Close games (final margin ≤ 5) vs blowouts (≥ 20), each needing ≥ 3
games: `gl2_n_close`, `gl2_n_blowout`, `gl2_close_mpg`, `gl2_close_gmsc40`, `gl2_close_d_mpg`,
`gl2_close_d_gmsc40`, `gl2_close_d_ts`, `gl2_blow_mpg`, `gl2_blow_d_mpg`,
`gl2_close_minus_blow_gmsc40`, `gl2_close_minus_blow_mpg`. Site splits: `gl2_n_neutral`,
`gl2_neutral_d_gmsc40`, `gl2_away_minus_home_gmsc40`.

## Coverage

| draft-year band | pids with features | identity rows | coverage |
|---|---|---|---|
| 2000-01 (before the archive) | 0 | 134 | 0.0% |
| **2002-07** | 142 | 448 | 31.7% |
| **2008-18** | 783 | 1,017 | 77.0% |
| **2019-25** | 712 | 900 | 79.1% |
| 2026 (partial season) | 54 | 61 | 88.5% |
| total | 1,691 | 2,560 | 66.1% |

Per draft year: 2000-04 = 0%; 2005 45%, 2006 65%, 2007 72%, 2008 71%, 2009 85%, 2010 82%,
2011 75%, 2012 77%, 2013 69%, 2014 77%, 2015 75%, 2016 77%, 2017 76%, 2018 82%, 2019 77%,
2020 77%, 2021 87%, 2022 78%, 2023 74%, 2024 74%, 2025 79%, 2026 89%.

Why pids are missing (`unmatched.csv`, 1,440 rows / 1,188 pids; 869 pids end up with no row):

| reason | rows | meaning |
|---|---|---|
| `no_college_evidence` | 616 | no NCAA college found — international, prep-to-pro, JUCO, G-League |
| `name_not_in_box` | 382 | on the roster but never in a box score (red-shirt, transfer sit-out year, a nickname the box uses: Sheldon McClellan appears only as "S. Mac") |
| `fewer_than_2_games` | 166 | fewer than two usable games that season |
| `no_box_scores_in_archive` | 143 | the team-season is absent from the archive |
| `stale_last_season` | 122 | last college season more than one year before the draft |
| `ambiguous_box_name` / `ambiguous_roster_name` / `ambiguous_team` | 11 | two players could not be told apart — logged, never guessed |

## Known limitations

* **The archive is thin before 2004-05.** 2002-03 has box scores for 21 teams / 36 games and
  2003-04 for 166 teams / ~8 games per team, so draft classes 2000-2004 get no rows at all and
  2005-2007 are partial. Team ratings for 2003-2007 come from the archive itself, not Torvik.
* **Whole team-seasons are missing** from the archive (Florida 2010-11 and 2012-13, Georgetown and
  Ohio State 2012-13, UCLA 2017-18, …): 104 of the 2,649 needed team-seasons (3.9%). Affected
  players either lose a season (`gl2_seasons_no_archive` > 0) or drop out entirely.
* **Individual box scores are occasionally missing or have `MIN = NA`** (Chris Paul has NA minutes
  in 2 of his 31 Wake Forest 2004-05 games), which slightly understates availability. See
  `gl2_dnp_rows` and `gl2_box_completeness`.
* **2025-26 (draft 2026) is a partial season** — `gl2_box_completeness` ≈ 0.39, no tournament, and
  the 2026 cutoff date is extrapolated. Treat those 54 rows accordingly.
* Where the draft-year season is missing, features describe the most recent season that is present;
  `gl2_final_is_predraft_season = 0` marks those rows.
* Seeds/PASE exist only for tournament teams (1,005 of 1,691 rows) and tournament deltas only for
  players with ≥ 2 tournament games (668 rows). Empty ≠ zero.
* Two rating systems across eras (Torvik 2008+, archive-derived before): ρ ≈ 0.92 but the top-50
  cut differs by ~10 teams per season, so `gl2_d50_*` is noisier pre-2008. `gl2_tier_src_torvik`
  flags it.
* Everything is opponent-adjusted only through the tier cut; no pace or usage adjustment.

## Terms of service

MIT-licensed GitHub data pulled over the ordinary git/HTTPS protocol; Torvik CSVs were already
cached by the project's own polite (2 s spacing) puller and only one new Torvik request was made;
Wikipedia through the public MediaWiki API at 1.5 s spacing with a descriptive User-Agent
(`DraftDB-research/1.0 (mike@alphax.inc)`). No robots.txt-restricted path, paywall, login or
bot-challenge was involved. sports-reference.com, kenpom, synergy, realgm and the Torvik
`playerstat.php`/`box.php`/`*.json` endpoints were not contacted. Player names stay on this Mac:
`features.csv`, `unmatched.csv` and everything in `work/` are pid-keyed and numeric (the two
identity intermediates `work/player_seasons.csv` and `raw/rosters.csv.gz` hold names and must not
leave the machine). `unmatched.csv` carries no player names except the ESPN box-score abbreviations
in the 11 ambiguity rows, which are what a human needs to resolve them.
