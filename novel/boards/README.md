# boards -- big board vs mock draft (NBADraft.net, DraftExpress, The Stepien)

Talent-versus-fit features built from Wayback Machine captures of public big boards and mock drafts. The board side is the new information: the model already carries a dated multi-publisher MOCK consensus, so nothing here rebuilds mock consensus -- what is new is each publisher's *board* (pure talent ranking) and the **board-minus-mock gap within the same publisher**, plus board momentum and analyst dispersion.

Everything is derived from `web.archive.org` only. The live sites are never contacted (nbadraft.net is Cloudflare-gated; draftexpress.com no longer serves these pages). Requests are serialised at >= 1.05 s apart with a keep-alive session, exponential backoff on 429/503, at most one CDX listing in flight, and a descriptive User-Agent identifying the project and a contact address. All captures are cached under `raw/`, so re-runs are offline.

## Files

| file | contents |
|---|---|
| `features.csv` | pid + numeric `bb_*` columns, one row per player |
| `provenance.csv` | pid, source, capture timestamp and URL behind each *final* value |
| `unmatched.csv` | listed names that could not be tied to a pid, with the reason |
| `raw/index.csv` | every snapshot the discovery pass found (source, url, timestamp) |
| `raw/fetch_plan.csv` | the captures actually selected for download |
| `raw/<source>/<ts>_<hash>.html.gz` | raw mementos (`id_` flag, unrewritten) |
| `raw/parsed.jsonl.gz` | one JSON record per parsed capture (rank, name, pos, school, class, age, ht, wt, change) |
| `raw/year_reassignments.csv` | captures the content check moved to another class (`<year>`), dropped as belonging to no adjacent class (`DROPPED`, mostly stale pages), or refused as a results table (`RESULTS_LEAK`) |
| `raw/capture_usage.csv` | every capture that survived all checks, with its final class year, entry count and days-before-draft |
| `run.log` | crawl log |

## URL patterns collected

**NBADraft.net big board** (`nd_board`)
```
https://www.nbadraft.net/ranking/bigboard/          (single rolling URL, 2008-2025)
```
100 entries; columns Rank, Change, Player, Height, Weight, Pos, School/Team, Class.

**NBADraft.net editorial mocks** (`nd_mock`) and crowd consensus (`nd_crowd`)
```
/mocks/{YYYY}_nba_mock_draft.html      2001-2009
/mock{YYYY}.htm                        2001-2002
/{YYYY}mock_draft                      2010-2016
/{YYYY}-nba-mock-draft-{v}/            2017-2025  (v = revision number)
/extended-nba-mock-draft-{N}-0/        two-round editions
/nba_mock_drafts/consensus             crowd aggregate, 2009-2018 (underscore path)
/nba-mock-drafts/consensus/            crowd aggregate, 2019-2025 (hyphen path)
```
Discovery was a single CDX domain listing (`url=nbadraft.net&matchType=domain&filter=original:.*[Mm]ock.*`), which returns every mock URL the site has ever used, rather than guessing per-year URLs.

**DraftExpress** (`dx_board`, `dx_mock`, `dx_mockx`)
```
/rankings/Top-100-Prospects/           one page of 100   (2008-2014)
/rankings/Top-100-Prospects/{2,3,4}/   25 per page       (2015-2017)
/rankings/Top-100-Prospects/printable  (2017)
/nba-mock-draft/{YYYY}/                2007-2017
/nba-mock-draft-extended/{YYYY}        two rounds
```

**The Stepien** (`stepien`)
```
/{YYYY}-draft-rankings/                composite board (tier headers)
/{YYYY}-individual-rankings/           analyst grid (one column per analyst)
/YYYY/MM/DD/<analyst>s-...-big-board/  dated single-analyst posts
```

## Capture acceptance rule (dating)

Draft-night cutoffs are the project list (22:00 UTC on draft day). A capture is used for draft class Y only if it satisfies one of:

1. **Pre-draft.** Capture timestamp < cutoff(Y), and the calendar rule below assigns it to class Y.
2. **Frozen final board.** Timestamp is after cutoff(Y) but before 15 Aug of Y. NBADraft.net and DraftExpress freeze the board after the draft and only reset to the next class in late August, so such a capture still shows the *final pre-draft* board. It is accepted only if the content check below agrees the top entries are class-Y players.
3. **DraftExpress on-page stamp.** From ~2012 the Top-100 page prints "This Ranking was last updated on <date>". A capture is accepted when either the capture timestamp or the parsed last-updated date is before the draft; the last-updated stamp is also the key used to stitch the paginated 25-per-page era back into one 100-man board.
4. **Mocks with the year in the URL** are accepted up to 40 days after the draft (the page is frozen and self-labelled), because the URL, not the timestamp, identifies the class.

**Calendar rule.** For a rolling board URL, a capture at time t belongs to class Y where Y = t.year if t < cutoff(t.year); the window (cutoff(Y), 15 Aug of Y] is the frozen class-Y board; and t after 15 Aug of Y belongs to class Y+1. This handles the shifted 2020 (18 Nov) and 2021 (29 Jul) drafts automatically.

5. **Stepien dated posts are dated by publication, not capture.** A post at `/2018/06/19/...` was knowable on 19 June 2018 even if the archive only captured it in July, so the publication date in the path drives both the class year and the days-before-draft.

**Content check.** For every board capture, the fraction of its top 30 names that are drafted players of class Y-1 / Y / Y+1 is computed against the identity file. The calendar year is kept unless another year beats it by >= 0.10 in that fraction, in which case the board is reassigned and logged to `raw/year_reassignments.csv`. This both verifies the frozen-board case and catches sites that reset early or late.

This check is what keeps *stale* pages out. nbadraft.net leaves old "extended mock draft" URLs (`/extended-nba-mock-draft-81`, `/nba-mock-draft-73`) live and heavily crawled for years, still frozen on the 2013 class; DraftExpress likewise served a 2017 board long after it stopped updating. Such a capture agrees with no adjacent class and is dropped rather than mistaken for a later board. The planner also prefers capture URLs that name the class (`/2016mock_draft`, `/2019-nba-mock-draft-3/`) over undated ones so the request budget is not spent on those pages in the first place.

**Results-leakage guard.** A post-draft mock capture is additionally refused when too many of its picks land exactly on the real draft slot. Across 464 strictly pre-draft mock captures the exact-agreement rate never exceeded 0.27 (median 0.09); nbadraft.net's `/mocks/2008_nba_draft.html`, a results table sitting on a mock-shaped path, scores 1.00. The cutoff is 0.35, which clears every genuine mock observed and refuses the results pages; refusals are logged as `RESULTS_LEAK` in `raw/year_reassignments.csv`.

**State de-duplication.** The archive often captures the same published board many times. Captures are collapsed to distinct *board states* (signature = the full list of (rank, normalised name) pairs), keeping the earliest capture of each state. Momentum sums and mock-volatility standard deviations therefore count each published update once, not once per crawl. The signature must be the whole board: hashing only the top 25 collapses a complete 100-man board into an earlier state that happens to share its top 25, which once left a single 25-entry page standing as the "final" 2016 DraftExpress board. For the same reason the final board is chosen from states with at least 50 entries whenever any exist.

**Horizon readings.** `*_30d` / `*_60d` take the latest state at or before that horizon, but never one more than 120 days older than the horizon, so a preseason board can never stand in for a one-month-out reading.

## Parsing notes by layout era

Rule-based extraction only (regular expressions and a fixed NBA-franchise dictionary). No scouting prose is stored anywhere -- only rank, name, position, school/team, class, listed age, height, weight and the board's own movement arrow.

| source / era | markup | extraction |
|---|---|---|
| nd_board 2008-2018 | `<table class="nba_ranking bigboard">` | 8 `<td>` per row: rank, change (arrow gif + `+n`/`-n`), player link, ht, wt, pos, school, class |
| nd_board 2019-2025 | `<table class="big-board-table">` | same column order; the player cell wraps first/last name in separate `<span>`s |
| nd_mock 2001-2008 | two-column `<table>` | one `<tr>` holds BOTH pick N and pick N+30; a cell is a player when its text is `Name 6-10 240 POS School Class`; team cells are rejected with a franchise dictionary |
| nd_mock 2009-2025 | one pick per `<tr>` | rank cell + a `/players/<slug>` link |
| nd_crowd all | same `<tr>` shape as the mock | pick + player |
| dx 2008-2009 | `<table class=lotto>`, **unquoted** attributes | `/profile/Name-<id>/` link preceded by a `<td>rank</td>`; meta line `19 years old, 6' 10" 239lbs.` |
| dx 2010-2014 | `<table class="bluecells">`, 4 sub-tables of 25 | same, plus `<font size=1>age, class<br>ht wt<br><a /clubhouse/>school</a>` |
| dx 2015-2017 | `<div class="ranking-item">` + `<div class="numero">` | rank in `<font size="5">N.</font>`; `18.7 years old  |  6'9"  |  196 lbs` |
| dx mock all years | `<font size="5">N.</font>` + team logo + profile link | pick number, player, school, class, decimal age |
| stepien composite 2020 | `<div class="rank-card"><h3>Name</h3>` (no number) | the 2020 board dropped explicit numbering ("order within tiers is fluid"); rank is the card's ordinal position, which is the order the site presents |
| stepien composite | `<div class="rank-card"><h3>N. Name</h3>` with `<div class="rank-tier"><span>Tier N</span>` | rank, name, school, tier |
| stepien analyst grid | `<table class="tablepress rankings-table">` | header row = analyst names; each cell is `Tier.OverallRank` (e.g. `3.06`) or `NR` |
| stepien dated posts | WordPress `entry-content` | `N. Player Name` at the start of a heading/paragraph/list item, with `Tier N` headers |

A DraftExpress rank token is bound to the *nearest preceding* rank marker before each `/profile/` link, and only the first occurrence of each rank is kept, so sidebar and 'related' links cannot inject phantom entries.

## Name matching

Names are normalised (NFKD accent strip, lower-case, punctuation and `Jr/Sr/II/III/IV/V` suffixes removed, parenthetical text dropped) and matched **only within the same draft class** as the identity file records for that pid. Three rules are tried in order and each must be unique inside the class:

1. exact normalised full name;
2. first initial + last name (handles `C.J.` / `CJ`, `Nikola` / `Niko`);
3. last name alone, when the class contains exactly one such surname and the first initials agree.

Anything ambiguous or unresolved is written to `unmatched.csv` with the reason (`ambiguous_exact`, `ambiguous_initial`, `ambiguous_last`, `no_candidate`) and never guessed. Most `no_candidate` rows are board entries for players who were never drafted or never reached the NBA and so are absent from the identity file by construction.

## Captures used, by source and draft class

`used / planned` per class. **planned** counts captures the planner assigned to that class from the URL or the calendar rule and selected for download; **used** counts captures that parsed into at least one ranked entry AND survived the dating, content and leakage checks, counted under their *final content-verified* class. The two are indexed differently, so `used` can exceed `planned` in a row that absorbed captures the content check moved in from the neighbouring class (and the neighbour's row is correspondingly short). Compare the totals, not the individual ratios.

| class | nd_board | nd_mock | nd_crowd | dx_board | dx_mock | dx_mockx | stepien |
|---|---|---|---|---|---|---|---|
| 2001 | - | 1/5 | - | - | - | - | - |
| 2002 | - | 2/6 | - | - | - | - | - |
| 2003 | - | 1/6 | - | - | - | - | - |
| 2004 | - | 7/7 | - | - | - | - | - |
| 2005 | - | 2/6 | - | - | - | - | - |
| 2006 | - | 4/8 | - | - | - | - | - |
| 2007 | - | 3/7 | - | - | - | - | - |
| 2008 | - | 1/7 | - | - | 12/8 | - | - |
| 2009 | 14/16 | 15/20 | 10/10 | 15/8 | 18/23 | - | - |
| 2010 | 16/18 | 6/20 | 10/10 | 12/6 | 35/36 | - | - |
| 2011 | 28/27 | 16/20 | 10/10 | 14/9 | 28/30 | - | - |
| 2012 | 24/27 | 13/20 | 10/10 | 60/53 | 24/40 | - | - |
| 2013 | 25/26 | 6/20 | 10/10 | 23/15 | 20/38 | - | - |
| 2014 | 17/17 | 16/20 | 10/10 | 35/26 | 15/40 | 0/3 | - |
| 2015 | 53/57 | 16/20 | 10/10 | 89/69 | 23/40 | 11/8 | - |
| 2016 | 33/45 | 16/20 | 10/10 | 148/171 | 29/40 | 4/8 | - |
| 2017 | 57/52 | 13/20 | 10/10 | 112/157 | 37/40 | 0/3 | - |
| 2018 | 41/44 | 14/20 | 10/10 | 0/13 | 16/40 | 0/3 | 13/15 |
| 2019 | 17/22 | 16/20 | 9/10 | 0/9 | 0/19 | 0/1 | 15/25 |
| 2020 | 27/27 | 6/20 | 10/10 | 0/21 | 0/12 | - | 18/42 |
| 2021 | 17/17 | 10/20 | 10/10 | 0/1 | 0/32 | - | - |
| 2022 | 210/201 | 5/20 | 9/10 | 0/3 | - | - | 4/4 |
| 2023 | 233/239 | 10/19 | 10/10 | 0/2 | - | - | - |
| 2024 | 13/16 | 13/20 | 9/10 | 0/2 | - | - | - |
| 2025 | 14/14 | 12/20 | 10/10 | 0/3 | - | - | - |
| **total** | 839/865 | 224/391 | 167/170 | 508/568 | 257/438 | 15/26 | 50/86 |

Class years in the table are the *content-verified* class of each capture, so they can differ slightly from the plan's calendar guess.

## Coverage by draft-year band

Denominator = identity-file players with a recorded draft pick in that band.

| feature | 2001-07 | 2008-18 | 2019-25 | all |
|---|---|---|---|---|
| `bb_nd_board_rank_final` | 0 (0%) | 533 (91%) | 392 (100%) | 925 (70%) |
| `bb_nd_mock_rank_final` | 240 (69%) | 419 (72%) | 310 (79%) | 969 (73%) |
| `bb_nd_crowd_mock_rank_final` | 0 (0%) | 433 (74%) | 284 (72%) | 717 (54%) |
| `bb_nd_fit_gap` | 0 (0%) | 390 (67%) | 310 (79%) | 700 (53%) |
| `bb_dx_board_rank_final` | 0 (0%) | 452 (77%) | 0 (0%) | 452 (34%) |
| `bb_dx_mock_pick_final` | 0 (0%) | 379 (65%) | 0 (0%) | 379 (29%) |
| `bb_dx_fit_gap` | 0 (0%) | 316 (54%) | 0 (0%) | 316 (24%) |
| `bb_dx_mock_volatility` | 0 (0%) | 413 (71%) | 0 (0%) | 413 (31%) |
| `bb_stepien_consensus_rank` | 0 (0%) | 30 (5%) | 55 (14%) | 85 (6%) |
| `bb_stepien_dispersion` | 0 (0%) | 51 (9%) | 49 (12%) | 100 (8%) |
| `bb_fit_gap_mean` | 0 (0%) | 450 (77%) | 310 (79%) | 760 (57%) |

| band | drafted players in identity file | rows in features.csv |
|---|---|---|
| 2001-07 | 347 | 240 (69%) |
| 2008-18 | 584 | 567 (97%) |
| 2019-25 | 392 | 392 (100%) |

## Feature definitions

All columns are numeric; empty means unknown (never 0).

| column | non-empty rows | definition |
|---|---|---|
| `bb_nd_board_rank_final` | 1222 | NBADraft.net big-board rank on the final accepted pre-draft board of the player's draft class (1-100; 101 = drafted player absent from that board, see bb_nd_unranked_board). |
| `bb_nd_board_rank_30d` | 1147 | Same board, nearest capture at or before 30 days before draft night (101 = absent; empty when no capture falls in the [30, 150]-day window). |
| `bb_nd_board_rank_60d` | 1104 | Same, at or before 60 days before draft night (window [60, 180] days). |
| `bb_nd_board_change_60d` | 1048 | Sum of the board's own Change column (+n = moved up n places since the previous board update) over the distinct board states published in the last 60 pre-draft days. Net board momentum. |
| `bb_nd_board_first_seen_days` | 1201 | Days before draft night that the player first appears on ANY accepted big board of his class. |
| `bb_nd_mock_rank_final` | 1075 | Pick number in the last NBADraft.net editorial mock draft of the class. |
| `bb_nd_crowd_mock_rank_final` | 812 | Pick number on the last capture of the NBADraft.net user-submitted consensus mock (/nba_mock_drafts/consensus). |
| `bb_nd_fit_gap` | 790 | bb_nd_mock_rank_final - bb_nd_board_rank_final. Positive = the same publisher's mock has him going LATER than his talent rank (team fit / need discount); negative = drafted-up relative to talent. |
| `bb_nd_unranked_board` | 1222 | 1 when the player was drafted in a class whose final big board exists but does not list him, 0 when he is listed. Companion flag for the 101 rank encoding. |
| `bb_dx_board_rank_final` | 566 | DraftExpress Top-100 Prospects rank on the last accepted pre-draft board of the class (empty when absent -- no 101 encoding on this source). |
| `bb_dx_board_rank_30d` | 548 | DraftExpress Top-100 rank, nearest board at or before 30 days before the draft. |
| `bb_dx_mock_pick_final` | 408 | Pick number in the last DraftExpress mock draft of the class. |
| `bb_dx_fit_gap` | 337 | bb_dx_mock_pick_final - bb_dx_board_rank_final (same sign convention as bb_nd_fit_gap). |
| `bb_dx_mock_volatility` | 482 | Sample standard deviation of the player's pick across all distinct DraftExpress mock states of that class (>=2 appearances required). |
| `bb_dx_board_momentum_30d` | 547 | bb_dx_board_rank_30d - bb_dx_board_rank_final. Positive = climbed the board over the last month. |
| `bb_dx_first_mock_lead_days` | 513 | Days before draft night of the earliest DraftExpress mock capture of the class that lists the player. |
| `bb_dx_age_listed` | 491 | Decimal age printed next to the player on his final DraftExpress board entry. |
| `bb_stepien_consensus_rank` | 87 | Rank on The Stepien's composite/consensus board for the class (last pre-draft capture). |
| `bb_stepien_dispersion` | 125 | Sample standard deviation of the player's rank across the individual Stepien analysts on the same grid (>=2 analysts). |
| `bb_stepien_tier` | 87 | Numeric tier from the tier header above the player on the composite board (Tier 1 -> 1). |
| `bb_stepien_preseason_to_final_delta` | 56 | Preseason composite rank minus final composite rank (positive = rose across the season). Needs a capture >=150 days before the draft. |
| `bb_fit_gap_mean` | 860 | Mean of the available publisher fit gaps (bb_nd_fit_gap, bb_dx_fit_gap). |
| `bb_n_board_sources` | 1572 | Number of publishers (NBADraft.net, DraftExpress, The Stepien) whose final board actually lists the player. |

### Sign conventions

* When the board rank is the 101 sentinel the fit gap inherits it and can reach roughly -90 (a player the mock has in the lottery but the board never listed). That is a real signal, not a parse error, but it is a censored measurement: gate or clip it with `bb_nd_unranked_board` rather than treating -86 as 86 places of disagreement.
* **fit gap** = mock pick - board rank. A player the publisher ranks 5th on talent but mocks at pick 14 has a fit gap of +9: the market is discounting him relative to the same publisher's own talent board. Negative = the market is reaching for him.
* **momentum / change** are positive when the player *rises* (rank number falls).
* **lead / first-seen days** are positive counts of days before draft night; larger = discovered earlier.

## Known limitations

* **No board coverage before the 2009 class.** The NBADraft.net big board first appears in the archive in December 2008 and the DraftExpress Top-100 in October 2008, so `bb_*_board_*` and both fit gaps are empty for the 2001-2008 bands. The 2001-2008 rows carry mock-side columns only (`bb_nd_mock_rank_final`, and `bb_nd_crowd_mock_rank_final` from 2009).
* **DraftExpress stops after the 2017 draft** (the site was folded into ESPN); later `dx_*` values come only from residual captures and are sparse or absent.
* **The Stepien** only published these boards for the 2018-2020 and 2022 classes; no 2021 rankings page exists in the archive, so `bb_stepien_*` is empty for 2021 and for everything before 2018.
* **Mock freshness is limited by the archive, not by choice, in a few classes.** A post-draft mock capture is allowed only when its URL names the class and it clears the results-leakage guard, so where the archive simply has no late crawl the final mock is older: the closest DraftExpress mock capture is 170 days out for 2009, and the closest NBADraft.net editorial mock is 137 days out for 2003 and 30 for 2019. Every other class lands within ~30 days of draft night and most within two days. The 2008 NBADraft.net mock is thin because its two draft-week captures are the results table, refused by the guard.
* **Time-series features never use a post-draft capture.** The frozen window feeds only the *final* value; `bb_dx_mock_volatility`, `bb_dx_first_mock_lead_days`, `bb_nd_board_first_seen_days` and `bb_nd_board_change_60d` are computed from strictly pre-draft captures, so every lead/first-seen value is positive by construction.
* **Change-column sums under-count** when the archive missed an intermediate board update: the site reports movement since the previous update, and only captured updates can be summed.
* **Second-round and undrafted players** are frequently absent from a 100-man board; that is encoded as 101 with `bb_nd_unranked_board=1` for drafted players, and left empty for identity rows with no draft pick (whose `draft_year` is an NBA-entry year, not necessarily a draft class).
* **Volatility is conditional on being mocked.** `bb_dx_mock_volatility` is the spread over the captures where the player appears; a player who enters the mock late has a low-n, low-variance reading rather than a missing one.
* Mock volatility for DraftExpress is computed over at most 40 captures per class (evenly spaced through the pre-draft window plus the last one) to keep the crawl inside a polite request budget.

## Terms of service / etiquette

* Only `web.archive.org` is contacted; the origin sites are never fetched, so no Cloudflare challenge, paywall or login is bypassed.
* >= 1.05 s between requests from this collector, keep-alive session, exponential backoff on 429/503, at most one CDX listing in flight, and a User-Agent naming the project and a contact address.
* Captures that the archive cannot serve (5xx after three tries) are recorded as `.miss` markers so re-runs never re-request them.
* Only factual ranking fields are stored. No scouting reports, no article text, no images.

## Reproducing / resuming

```bash
cd /Users/kennakao/nba/datarebuild/novel/boards
python3 bb_index.py            # snapshot discovery  -> raw/index.csv
python3 bb_index_stepien.py    # Stepien supplement
python3 bb_fetch.py --replan   # select + download    -> raw/<source>/
python3 bb_features.py --parse # parse + build        -> features.csv
python3 bb_readme.py           # regenerate this file
```

Both crawl stages are checkpointed (`raw/index_done.txt`, `raw/fetch_done.txt`) and every capture is cached, so re-running any stage resumes where it stopped and costs no extra requests for work already done. `bb_features.py` and `bb_readme.py` are fully offline. To resume an interrupted crawl:

```bash
cd /Users/kennakao/nba/datarebuild/novel/boards
nohup python3 -u bb_fetch.py >> run.log 2>&1 &
until grep -q 'fetch complete' run.log; do sleep 30; done
python3 bb_features.py --parse && python3 bb_readme.py
```

