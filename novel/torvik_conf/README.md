# torvik_conf — conference play versus full season

Novel-data collector for the NBA redraft model. For every prospect matched by the sibling collector
`../torvik_context`, this takes his **final pre-draft Torvik season F** and adds two things the model
does not have: what his line looked like **in conference games only**, and the **delta** (conference
minus full season) for every rate and per-game statistic.

The motivation is schedule quality. A full-season college line mixes November cupcakes with January
league play, and the mix is not the same for every prospect: a high-major freshman's non-conference
slate is padded, a mid-major's is a gauntlet of money games. The conference-only split holds the
opponent pool roughly fixed within a team's own league and asks whether the production survived it.

Everything is derived from season F, whose conference regular season ends in early March. Every
draft is in June. Every column here is knowable on draft night.

## Outputs

| file | contents |
|---|---|
| `features.csv` | 1,716 rows: `pid` + **53 numeric `tcf_` columns**. Missing is empty, never 0. |
| `README.md` | this file. |
| `provenance.csv` | one row per cached CSV — 19 conference-only pulls plus the 19 reused full-season files: URL, season, row count, uncompressed and gzipped bytes, sha256, fetch time, robots/UA terms. |
| `verify_conyes.csv` | the per-season verification table reproduced below. |
| `raw/` | 19 gzipped conference-only CSVs (12 MB) + the `robots.txt` that was read. Re-runs are fully offline. |
| `run.log` | the last full run: verification, coverage, delta distributions. |
| `build.py`, `fetch_raw.py` | the collector. `python3 fetch_raw.py` (resumable, skips cached files) then `python3 build.py` (~2 min, cache only). |

Pure Python 3 + pandas/numpy. Nothing outside this directory is written.

## Sources and terms

| endpoint | role |
|---|---|
| `https://barttorvik.com/getadvstats.php?year=YYYY&conyes=1&csv=1` | **conference games only**, same 67 unlabelled columns, 2008–2026, 85,104 player-seasons. Fetched here. |
| `https://barttorvik.com/getadvstats.php?year=YYYY&csv=1` | full season, 90,739 player-seasons. **Reused** from `../torvik_context/raw/adv_YYYY.csv.gz` — not re-downloaded. |
| `https://barttorvik.com/getgamestats.php?year=YYYY&csv=1` | team-games. Reused from the same cache, only to *verify* `conyes=1` (see below). |

`https://barttorvik.com/robots.txt` (read 2026-09-09, cached verbatim at `raw/robots.txt`) disallows
`db.php`, `box.php`, `results.php`, `playerstat.php`, `teamcast.php`, the `*-time-machine.php` pages,
`/*.json`, `/cgi-bin/` and any URL containing `t1l=` or `t2l=`. **`getadvstats.php` is not
disallowed**, and the request carries neither `t1l` nor `t2l`. The `User-agent: *` block sets
`Crawl-Delay: 10`, which `fetch_raw.py` honours: one request every 10 s, exponential backoff on
failure, descriptive User-Agent
`DraftDB-research/1.0 (contact: mike@alphax.inc) non-commercial NBA draft research`. No login,
paywall or JS challenge is involved. **Total network cost: 19 season requests + 1 robots.txt, once.**

> **Flagged for the operator.** Beyond the `User-agent: *` group, this robots.txt also carries
> `Disallow: /` blocks for a list of *named* crawlers, and two of those names are
> **`ClaudeBot`** and **`anthropic-ai`** (alongside GPTBot, Google-Extended, Bytespider, PerplexityBot,
> Applebot, bingbot, Amazonbot, SemrushBot and others — the standard AI-crawler and SEO-scraper block
> list). The sibling `torvik_context` README does not mention this. Under the robots.txt standard the
> applicable group is chosen by product-token match, and this collector's token is `DraftDB-research`,
> which matches only `*` — so these 19 requests are permitted by the file as written. They are also
> user-initiated research on the site owner's own published CSV export, 19 requests at the site's
> requested 10 s spacing, with the operator's real contact address in the header. Still, the site
> owner has signalled that he does not want general AI-crawler traffic, so the judgement call is
> recorded here rather than buried: if you would rather not pull this endpoint from an
> agent-driven script at all, the cache under `raw/` is complete and `build.py` never touches the
> network again.

Years before 2008 are never requested. The endpoint silently serves the **current** season for them,
which would be a silent mislabelling rather than an error; `build.py` asserts the year column of
every cached file equals the requested year anyway.

## Verification that `conyes=1` really restricts the export to conference games

Another agent reported the parameter; it was not taken on trust. `build.py` prints this table on
every run and asserts every column of it (`verify_conyes.csv`).

Four independent checks:

1. **Schema and mode marker.** The conference export returns the same 67 columns in the same order,
   so `../torvik_context`'s inferred mapping is reused unchanged. Column 33, which carries the
   player's hometown in the full-season export, holds the literal string **`conf`** on all 85,104
   conference rows — the export stamps its own mode. Asserted per season.
2. **The year column equals the requested year** on all 85,104 rows, every season. Asserted.
3. **GP and minutes drop.** Joined on `tpid` within a season, conference GP ≤ full-season GP for
   ≥99.98% of rows and strictly less for 92–99%; aggregate GP ratio 0.52–0.69 and minutes ratio
   0.53–0.69, never above 0.75. Asserted.
4. **An independent cross-check the brief did not ask for.** Each team's maximum conference GP is
   compared with that team's game count in the *separate* `getgamestats.php` feed, split by `gtype`.
   It equals the **`gtype == 1`** (conference regular season) count for **99.4–100% of the 331–365
   teams in every one of the 19 seasons**, and equals the `gtype ∈ {1,2}` count (which would add the
   conference tournament) for only 6–13%. So `conyes=1` means **conference regular season only —
   conference tournaments are excluded.** Asserted both ways.

```
   yr   conf   full  yrOK    GP<=     GP<   min<=    min<  GPratio  minRatio   tm  =gtype1  =gtype1+2
 2008   4195   4588     1 100.000% 98.140% 99.762% 98.474%    0.539     0.549  331   100.0%      13.3%
 2009   4316   4589     1 100.000% 97.660% 99.791% 97.799%    0.535     0.541  343    99.4%      13.1%
 2010   4387   4698     1 100.000% 98.268% 99.567% 98.290%    0.530     0.538  345   100.0%      11.9%
 2011   4298   4548     1 100.000% 98.976% 99.814% 98.860%    0.524     0.532  345   100.0%      11.0%
 2012   4350   4586     1 100.000% 98.690% 99.793% 98.598%    0.524     0.530  345   100.0%      11.0%
 2013   4351   4608     1 100.000% 98.023% 99.747% 98.184%    0.540     0.546  345   100.0%      12.2%
 2014   4465   4722     1 100.000% 98.544% 99.866% 98.455%    0.544     0.552  350   100.0%       9.4%
 2015   4459   4723     1 100.000% 98.408% 99.798% 99.013%    0.555     0.563  350    99.4%      10.0%
 2016   4434   4696     1 100.000% 97.925% 99.684% 97.812%    0.556     0.563  351    99.4%       9.1%
 2017   4442   4742     1 100.000% 98.244% 99.617% 98.762%    0.550     0.561  351   100.0%       7.1%
 2018   4417   4703     1 100.000% 98.279% 99.525% 98.506%    0.548     0.558  351   100.0%       6.0%
 2019   4420   4739     1  99.977% 98.213% 99.751% 98.643%    0.550     0.561  353   100.0%       8.2%
 2020   4429   4733     1 100.000% 97.765% 99.503% 98.239%    0.590     0.600  353   100.0%      39.1%
 2021   4733   4970     1 100.000% 91.844% 98.648% 94.126%    0.683     0.690  345   100.0%       9.6%
 2022   4701   5011     1 100.000% 97.150% 99.511% 98.043%    0.576     0.587  358    98.3%       7.5%
 2023   4760   5043     1 100.000% 97.374% 99.475% 98.319%    0.569     0.580  363   100.0%       7.2%
 2024   4644   5002     1 100.000% 97.868% 99.677% 98.665%    0.566     0.576  361   100.0%       7.5%
 2025   4682   5060     1 100.000% 97.800% 99.658% 99.146%    0.575     0.587  364   100.0%       9.1%
 2026   4621   4978     1 100.000% 98.161% 99.632% 99.221%    0.576     0.591  365    99.7%       9.3%
```

**Two apparent outliers are themselves confirmations, not failures.**

* **2021** is the only season where `GP<` falls below 95% (91.8%) and the GP ratio jumps to 0.683
  from the 0.52–0.59 of every other season. That is COVID: most non-conference scheduling was
  cancelled, so a large minority of players genuinely played nearly all their games in conference.
  A parameter that did nothing could not produce a season-specific shift of exactly that shape.
* **2020** is the only season where the `gtype ∈ {1,2}` agreement rises to 39%. That is the March
  2020 shutdown: the conference tournaments were cancelled part-way, so for many teams there were no
  conference-tournament games to add. The conference **regular** seasons had finished, so the 2020
  class's conference line is complete.

**Do the deltas behave?** A fifth, softer check. Raw offensive rating falls in conference play
(mean `tcf_d_ortg` = −0.80) and raw defensive rating rises, i.e. worsens (`tcf_d_drtg` = +2.42),
which is what a stronger opponent pool should do. But **opponent-adjusted** offence barely moves
(`tcf_d_adjoe` = +0.28) — the adjustment absorbs exactly the effect the raw number picks up, which
is what it exists to do. Usage, 3PA rate and per-game rebounds and assists are centred on zero
(role is stable); minutes share rises (`tcf_d_minper` = +1.50) as rotations tighten out of the
blowout-heavy non-conference slate. Nothing here is fitted, so none of it was arranged.

## Matching prospects to Torvik players

**Not reimplemented.** `build.py` imports `../torvik_context/build.py` by file path and calls its
`load_players()`, `load_prospects()` and `match()`, so the `pid → (tpid, F)` mapping is **identical
to that collector's by construction**, not merely similar: same normalisation, same
draft-year-plausibility window, same birthdate corroboration, same cascade, same 1,716 matched
prospects and same final pre-draft season F. See that collector's README for the cascade itself.

Two mechanical notes. The sibling loaders ask for `adv_YYYY.csv` while the cache on this disk holds
only `adv_YYYY.csv.gz` (under 1 GB free), so a small context manager redirects `.csv` → `.csv.gz`
when and only when the plain file is absent; nothing is decompressed to disk. And the sibling module
is imported by path rather than with `import build`, because this file is also called `build.py`.

The conference line is then joined on `(tpid, F)`. Both feeds are asserted unique on that key.
Torvik's post-draft `pick` column is dropped from **both** feeds at load and read nowhere.

## Feature definitions

53 columns, all `tcf_`-prefixed, all for season **F** (the player's last Torvik season with
`year ≤ draft_year`).

| column | definition |
|---|---|
| `tcf_season_final` | season F itself (e.g. 2019). Repeated from `tc_season_final` so this block stands alone. |
| `tcf_conf_gp` | **conference games played** in season F. |
| `tcf_conf_gp_share` | **share of season games played in conference** = `tcf_conf_gp` / full-season GP. |

Then, for each statistic below, **two** columns: `tcf_<stat>` is the conference-only value, and
`tcf_d_<stat>` is **conference minus full season**.

| stat | column in the 67-column export | meaning |
|---|---|---|
| `usg` | `usg` | usage rate |
| `ortg` | `ORtg` | offensive rating (raw) |
| `adjoe` | `adjoe` | adjusted offensive rating |
| `drtg` | `drtg` | defensive rating (raw) |
| `adrtg` | `adrtg` | adjusted defensive rating |
| `bpm` / `obpm` / `dbpm` | `bpm` / `obpm` / `dbpm` | box plus/minus, offensive, defensive |
| `ts` | `TS_per` | true shooting % |
| `efg` | `eFG` | effective field goal % |
| `ast_per` | `AST_per` | assist rate |
| `tov_per` | `TO_per` | turnover rate |
| `orb_per` / `drb_per` | `ORB_per` / `DRB_per` | offensive / defensive rebound rate |
| `stl_per` / `blk_per` | `stl_per` / `blk_per` | steal / block rate |
| `ftr` | `ftr` | free-throw rate, FTA/FGA ×100 |
| `tp3_pct` | `TP_per` | 3P% |
| `tpar` | derived, `TPA / (TPA + twoPA)` | **3PA rate** — share of field goal attempts taken from three |
| `tpa100` | `tpa_per100` | 3PA per 100 team possessions (the export's own rate; kept alongside `tpar` because they answer different questions — shot mix versus volume) |
| `porpag` | `porpag` | PORPAGATU |
| `minper` | `Min_per` | **minutes share** — % of team minutes played |
| `pts_pg` / `reb_pg` / `ast_pg` | `pts` / `treb` / `ast` | points / rebounds / assists **per game** |

Both raw and adjusted ratings are carried on each side because the pair is informative: the raw
delta measures how much harder the conference schedule was, the adjusted delta measures what
survived the adjustment.

**Empty, never zero.** A percentage on zero attempts is unknown, not 0: `tcf_tp3_pct` is empty when
the player took no conference threes (that is the 9.3% gap in its coverage), and `tcf_ts`,
`tcf_efg`, `tcf_ftr`, `tcf_ortg` and `tcf_tpar` are empty when he attempted no conference field
goals. The same guard is applied to the full-season side before differencing, so a delta is empty
whenever either side is.

## Coverage

`features.csv` has one row per matched prospect: 1,716 of the 2,560 in the identity file. 1,694 of
them (98.7%) carry a conference line.

| draft-year band | prospects | rows | rate | with conference line | mean cell fill |
|---|---|---|---|---|---|
| 2000–2007 | 582 | 0 | 0.0% | 0 | — |
| **2008–2018** | **1,017** | **870** | **85.5%** | **857** | **98.1%** |
| **2019–2025** | **900** | **791** | **87.9%** | **782** | **98.7%** |
| 2026 (bonus) | 61 | 55 | 90.2% | 55 | 99.9% |

Per draft year (rows / prospects, with conference line):

| 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 |
|---|---|---|---|---|---|---|---|---|---|
| 52/70, 51 | 60/71, 60 | 68/79, 68 | 75/88, 74 | 74/86, 73 | 76/91, 74 | 76/90, 74 | 70/81, 69 | 88/104, 87 | 118/132, 116 |

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| 113/125, 111 | 120/137, 117 | 96/112, 95 | 221/233, 218 | 83/97, 83 | 83/101, 83 | 96/114, 95 | 92/106, 91 | 55/61, 55 |

The 844 prospects with no row are exactly the sibling collector's unmatched set — 582 drafted before
Torvik's data begins, 261 with no D1 season (international, G League Ignite, OTE, NBL), 1 ambiguous
name. The 2008 class is not thin here the way it is in `torvik_context`: this block needs only
season F, not a career.

## Known limitations

* **2000–2007 is empty by construction.** Torvik's first season is 2008.
* **22 matched prospects have no conference line at all** and are left empty rather than zeroed.
  Every one of them is a player who barely appeared: full-season GP median 5.5, max 12 — he left,
  was injured, or was ruled ineligible before conference play began. Across the whole feed, 6.2% of
  full-season player-seasons have no conference row, and their median GP is 4.
* **Small conference samples are real.** Median conference GP is 18 (range 1–20), but 62 of the
  1,694 prospects played 10 or fewer conference games and 17 played 5 or fewer. A delta computed on
  6 games is mostly noise. `tcf_conf_gp` is emitted precisely so a consumer can down-weight or drop
  those rows; **no minimum-games filter is applied here.**
* **Conference tournaments are excluded** (proved above), so `tcf_conf_gp_share` never reaches 1.0
  in a normal season — its median is 0.529.
* **Torvik's `mpg` is rounded in the export**, so reconstructed minutes (`mpg × GP`) can put
  conference minutes a hair above full-season minutes for very-low-minute players: 302 of 85,103
  joined player-seasons (0.355%), all bench cases like 3 games at 0.75 mpg. One row in 19 seasons
  (Ricky Gouety, Stetson 2019: 15 conference games against 2 full-season games) has conference GP
  above full-season GP, and one conference row has no full-season counterpart at all. These are
  upstream aggregation glitches, not parse errors; none of the three affects a matched prospect.
* **The 2008 and 2009 counting stats are unreliable upstream** — `../torvik_context` documents that
  Torvik's made/attempted totals for those two seasons are short (Stephen Curry's 2009 threes read
  127/327 against an actual 162/384). Rate stats and BPM look sound. Treat `tcf_tp3_pct`,
  `tcf_ftr` and `tcf_tpar` for the 2009–2010 draft classes with care.
* **Conference strength is not controlled here.** A +2 BPM delta in the Big Ten and in the Southland
  are not the same event. `../torvik_context` already carries conference-strength columns
  (`tc_conf_*`); the intended use is to interact them with these deltas rather than to duplicate them.
* **No opponent-quality split inside conference play** (home/away, top-half/bottom-half). The
  `getgamestats.php` feed is team-level, and player-level game logs live behind `playerstat.php`,
  which robots.txt disallows. Nothing is emitted for it.

## Re-running

```
cd /Users/kennakao/nba/datarebuild/novel/torvik_conf
python3 fetch_raw.py      # skips every cached file; a re-run costs zero network traffic
python3 build.py          # ~2 min from cache; rewrites features.csv, verify_conyes.csv, provenance.csv
```

`fetch_raw.py` takes an optional list of years (`python3 fetch_raw.py 2027`) to extend the range;
`SEASONS` in `build.py` must be extended to match.
