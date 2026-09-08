# DraftExpress archived pre-draft measurements -> growth-trajectory features

`/Users/kennakao/nba/datarebuild/novel/draftexpress/`

draftexpress.com has been dead since late 2017 (its staff moved to ESPN). Its *Measurements History* database is the only public source that measured the same prospects repeatedly from age ~15 through the pre-draft process, so it is the only way to build real growth trajectories. Everything here comes from the Wayback Machine.

## 1. What was collected

* **6,329 player-events** over **3,801 distinct DraftExpress player ids**, event years **1987-2017** (`measurements_all.csv`, names allowed - local only).
* **1,242 of the 2,560 drafted players** in `tabular_names.csv` matched (`features.csv`, pid + numeric only); 21 rows logged to `unmatched.csv`.
* **876 listing captures** and **3053 profile captures** cached under `raw/` (gzipped), so every re-run is offline.

## 2. URL patterns used

Two generations of the same database are archived. Only URLs that were actually captured can be replayed, so the crawl list is **derived from the CDX index**, never generated.

```
CDX enumeration (single requests, cached as raw/cdx_full.json / raw/cdx_profiles.json):
  http://web.archive.org/cdx/search/cdx?url=draftexpress.com/nba-pre-draft-measurements*
      &output=json&fl=timestamp,original,statuscode,digest,length
  http://web.archive.org/cdx/search/cdx?url=draftexpress.com/profile*
      &output=json&fl=timestamp,original,length&filter=statuscode:200&collapse=urlkey

A. legacy listing (UNPAGINATED - one capture returns every row matching the filter)
     /nba-pre-draft-measurements.php
     /nba-pre-draft-measurements/?year=YYYY|All&source=NAME|All&pos=0..5&draft=0|15|30|100|999
                                 &sort=1..18&sort2=ASC|DESC
     /nba-pre-draft-measurements/measurements.php?...   (same parameters)
B. 2016/17 listing (100 rows per page)
     /nba-pre-draft-measurements/{year|all}/{source|all}/{pos|all}/{draft|all}/{page}/{sort}/{dir}
C. player profile (the only place a Source label appears per player)
     /profile/{Slug}-{dx_id}/          e.g. /profile/Andrew-Wiggins-6191/

Replay form (raw archived bytes, no Wayback toolbar injection):
     https://web.archive.org/web/{timestamp}id_/http://www.draftexpress.com{path}
Profiles are requested at https://web.archive.org/web/20170601000000id_/...  and the
Wayback Machine redirects to the nearest capture; the timestamp it actually served is
recorded per profile in raw/profiles_manifest.jsonl (capture_ts).
```

### Capture timestamps used

* Listing captures: **782** distinct timestamps, **20071223 - 20251227**. For each distinct URL shape the crawler keeps the **largest** capture recorded while the site was still live (timestamp < 2017-12-15); after that date every capture is a ~5.5 kB dead-site shell.
* Profile captures: **3018** distinct timestamps, **20090418 - 20240920** (median 20170703).
* The single most productive capture is `web/20170128164518id_/http://www.draftexpress.com/nba-pre-draft-measurements.php` - the legacy grid with no filter, which returns the whole database (11.1 MB, 5,688 data rows) in one request.
* 387 profiles came back from a **post-shutdown** capture (2018-2024 dead-site shells). `dx_profiles_retry.py` re-asked for each of them at an earlier target (2016-12-01) and **0 of 387** returned a live-era capture: those players simply have no pre-2018 profile snapshot, and nothing more can be recovered for them.
* Full per-page provenance: `raw/manifest.jsonl` and `raw/profiles_manifest.jsonl` (one JSON line per fetch: url path, capture timestamp, HTTP code, bytes, cache file). Per-pid provenance: `provenance.csv`.

### A note on database size

The April-2017 captures paginate to page 155, which suggests ~15,500 rows at 100 rows/page. That is wrong: those deep April captures contain **no data rows** (page size was smaller then and the deep pages archived empty), while the July-2017 captures - 100 rows/page - end at **page 42**, and the unfiltered legacy dump holds **5,688** rows. The real database is ~5.7k player-events, which is what we have.

## 3. Parsing rules (rule-based only - no judgement, no LLM scoring)

Three table shapes, all extracted by header text where a header row exists and by the verified canonical column order where the capture rendered the header detached:

```
A legacy  <table class="inputbox">, 18 cells
  Name | Ht w/o Shoes | Ht w/shoes | Weight | Wingspan | Reach | Body Fat | Hand Length |
  Hand Width | No Step Vert | No Step Vert Reach | Max Vert | Max Vert Reach | Bench |
  Agility | Sprint | Rank | Drafted
  - cell 0 is "Player Name - YYYY" (a leading "* " is stripped); YYYY is the EVENT year
  - Hand Length / Hand Width are literally "0" when missing -> null
  - no Source column
B 2016/17  <table class="sorttable">, two header rows, 18 cells
  Player | Year | Draft pick | Ht no-shoes | Ht w/shoes | Wingspan | Standing reach |
  Max vert | Max vert reach | No-step vert | No-step vert reach | Weight | Body fat |
  Hand length | Hand width | Bench | Agility | Sprint            - no Source column
C profile  <table class="alt">, 9 cells
  Year | Source | Ht w/o Shoes | Ht w/ Shoes | Weight | Wingspan | Standing Reach |
  No Step Vert | Max Vert                                        - the Source source
```

* **Values.** `7' 5.5"`, `6'11 1/4"` (unicode vulgar fractions), `6'8"`, `34"`, `19.5`, `247` are all reduced to inches / lb / seconds by two regexes; `NA`, `-`, `--`, `N/A`, empty are null. Fraction glyphs handled: 1/8 1/4 3/8 1/2 5/8 3/4 7/8 1/3 2/3.
* **DX player id** comes from the row's `/profile/{Slug}-{id}/` link, so rows are keyed on the site's own id rather than on the printed name.
* **Plausibility gates.** DraftExpress writes `0` / `0'0"` for "not measured", and a few rows carry obvious typos, so a parsed value outside height 48-96 in, wingspan 48-105 in, standing reach 70-130 in, max vert 10-60 in, no-step vert 5-55 in, weight 100-400 lb is treated as **missing** (never as 0). 1 values were gated on this build.
* **Source** is taken from (i) the profile table's Source column, (ii) the `source=` filter of the captured listing URL when the capture was source-filtered, or (iii) a join of an unlabelled listing row onto the same player-year profile event when their shared measurements agree. `source_from` in `measurements_all.csv` records which.
* **De-duplication** is by (player, source, year). Because the listing tables carry no Source, two same-year events are separated by their measurements: a candidate row merges into an existing event only when no shared measure disagrees by more than 0.3 in (heights/wingspan), 0.5 in (standing reach) or 3 lb; otherwise it opens a new event. Profile rows are processed first so they seed the events with their Source.
* **Column-mapping validation.** The two listing generations were parsed independently and compared on the 3,922 player-years both cover: median absolute difference **0.000** on all twelve measurement columns (height no-shoes, height with shoes, wingspan, standing reach, max vert, no-step vert, weight, body fat, hand length, bench, agility, sprint). Residual >0.5 mismatches (~1-3%) are players with two different events in the same year.

## 4. Dating

* DraftExpress records only a **year** per event, plus a **source**. The **(source, year)** pair is the event identity and the dating unit.
* The database is pre-draft **by construction** - every source is a youth camp, an all-star game, a college team listing or a pre-draft camp/combine, all of which run before draft night. On top of that the builder **drops any event with `event_year > draft_year`**, so nothing after a player's draft can leak in.
* Two further event filters guard against DraftExpress hanging a same-name player's row on the wrong profile: an event whose **estimated age is under 13** is dropped, and (when no age is available) so is any event more than 9 years before the draft. Any event after the draft year is dropped outright.
* **Leakage discipline.** The listing tables carry a `Drafted` / `Draft pick` column and the legacy grid carries a `Rank` column. Both are post-hoc with respect to the player's own draft night, so they are kept in `measurements_all.csv` for provenance and identity checking only and are **never** read by `dx_features.py` - no feature in `features.csv` derives from either (verified: the strings `draft_pick` and `rank` do not appear in the feature builder).
* For age arithmetic each event is dated **1 June of its event year**. Essentially every source runs April-July (Portsmouth April, Hoop Summit April, the combine and the old pre-draft camp May-June, Eurocamp June, the summer camps June-July), so ages carry roughly +-3 months of slack; the age >= / <= thresholds in `dx_height_at_16_in` and the youth flag inherit that.
* Birthdates, in priority order: (1) `age_verified_wiki.csv`; (2) the DX profile's own `Age: A.B` read together with the capture timestamp of that profile (birthdate ~ capture_date - A.B x 365.25); (3) class-year proxy, `age = (event_year - hs_class_year) + 18`, where hs_class_year is the profile's `RCSI: r (YYYY)` year or `draft_year - rsci_years_to_draft` from `rsci_features.csv`. `dx_age_src` records which, `dx_age_is_proxy` flags 2 and 3.

### Birthdate check

The DX-profile birthdate (age source 2) was compared with the verified `age_verified_wiki.csv` date on the **470** players who have both: median absolute error **9 days**, p90 **17 days**, **98.5%** within 60 days. Source 2 is therefore treated as a real birthdate rather than a proxy in practice, though `dx_age_is_proxy` still flags it as non-verified.

## 5. Identity matching

Names are normalised on both sides (NFKD accent strip, punctuation and apostrophes removed, Jr/Sr/II/III/IV/V dropped, lower-cased, hyphens -> spaces) and compared against the DX **profile slug**. Every DX id sharing the normalised name is a candidate, then:

1. if the DX profile states `Drafted #N in the YYYY NBA Draft`, **YYYY must equal our `draft_year`**; otherwise the candidate is rejected;
2. if the profile is not archived, the DX id must hold at least one event inside the player's own pre-draft window (`draft_year - 9 <= event_year <= draft_year`); a same-name collision with a younger player has none;
3. the pid is used **only** when exactly one candidate survives.

21 pids ended ambiguous or contradicted and are in `unmatched.csv` with the candidate ids and the rejection reason for each. No fuzzy or per-player judgement is applied anywhere.

## 6. Late-grower regression (documented, as required)

OLS fitted on **all archived players** (not just our draftees) who have both a height at estimated age <= 16 and a later height:

```
final_height_in = 1.7483 + 0.9878 x height_at_age<=16_in
n = 141   R^2 = 0.912
```
`dx_late_grower_resid` = observed final height minus that prediction. The fit population is limited to archived players for whom an age could be established at all (source 1/2/3 above); archived players with no birthdate and no class year cannot be placed on the age axis and are excluded.

## 6b. Feature definitions (features.csv, pid + numeric only, missing = empty)

Top 10 - the growth-trajectory core:

1. **`dx_n_events`** - count of distinct archived measurement events for the player (event = one (player, source, year) row after de-duplication), restricted to event_year <= draft_year.
2. **`dx_years_spanned`** - last event year minus first event year.
3. **`dx_earliest_age`** - age in years at the earliest archived event, event dated 1 June of its year; blank when no birthdate or class-year proxy is available.
4. **`dx_first_height_in`** - height in inches at the earliest archived event. height_in = height with shoes when reported, else height without shoes + 1.25 in (the median with-shoes minus no-shoes gap measured on the archive itself).
5. **`dx_d_height_in`** - height_in at the latest archived event minus height_in at the earliest archived event (blank unless the two events are in different years). When dx_has_youth_measurement = 1 this is the youth -> pre-draft growth delta.
6. **`dx_height_growth_per_yr`** - dx_d_height_in divided by the number of years between those two events (annualised height growth, in/yr).
7. **`dx_late_grower_resid`** - final archived height minus the height predicted from the player's height at age <= 16 by the OLS line fitted on all archived players with both (see 'Late-grower regression'). Positive = grew more than his 16-and-under height predicted. Blank without an age <= 16 measurement.
8. **`dx_still_growing`** - 1 when height_in gained >= 0.5 in between the earliest and the latest event inside the final 24 months before the last archived event; 0 when it did not; blank when fewer than two events fall in that window.
9. **`dx_first_ws_ht_ratio`** - wingspan_in / height_in at the earliest archived event (dx_last_ws_ht_ratio is the same at the latest event).
10. **`dx_weight_gain_per_yr`** - (weight at latest event - weight at earliest event) / years between them, lb/yr.

The rest:

* **`dx_n_sources_known`** - how many of the player's events carry a Source label (only profile pages and source-filtered listing captures do).
* **`dx_n_youth_events`** - events whose Source is in the youth dictionary, or (Source unknown) whose estimated age is <= 17.5.
* **`dx_first_event_year / dx_last_event_year`** - year of the earliest / latest archived event.
* **`dx_has_youth_measurement`** - 1 when at least one event is a youth event, else 0.
* **`dx_first_is_youth`** - 1/0 whether the earliest event is a youth event; blank when the Source is unknown and no age is available.
* **`dx_last_age`** - age at the latest archived event, same dating rule as dx_earliest_age.
* **`dx_age_src`** - 1 = birthdate from age_verified_wiki.csv, 2 = birthdate implied by the DX profile's 'Age: A.B' at its capture date, 3 = class-year proxy age = (event_year - hs_class_year) + 18.
* **`dx_age_is_proxy`** - 0 when dx_age_src = 1, else 1. Every age-derived feature on a proxy row inherits its error.
* **`dx_first_wingspan_in / dx_first_weight_lb / dx_first_reach_in`** - wingspan, weight and standing reach at the earliest event that reports each (each measure is taken from its own earliest reporting event).
* **`dx_last_wingspan_in / dx_last_weight_lb / dx_last_reach_in / dx_last_height_in`** - same at the latest reporting event.
* **`dx_d_wingspan_in / dx_d_weight_lb / dx_d_reach_in / dx_d_max_vert_in`** - latest minus earliest for wingspan, weight, standing reach and max vertical.
* **`dx_height_at_16_in`** - height_in at the earliest event with estimated age <= 16.

## 7. Coverage

| draft-year band | drafted players | with DX features | coverage | >=2 events | with a youth event |
|---|---:|---:|---:|---:|---:|
| 2000-07 | 582 | 330 | 56.7% | 24 | 4 |
| 2008-18 | 1017 | 731 | 71.9% | 447 | 395 |
| 2019-25 | 961 | 181 | 18.8% | 86 | 160 |

Per draft year:

| year | drafted | matched | % |
|---|---:|---:|---:|
| 2000 | 70 | 27 | 38.6% |
| 2001 | 64 | 41 | 64.1% |
| 2002 | 68 | 39 | 57.4% |
| 2003 | 74 | 38 | 51.4% |
| 2004 | 66 | 39 | 59.1% |
| 2005 | 95 | 57 | 60.0% |
| 2006 | 80 | 44 | 55.0% |
| 2007 | 65 | 45 | 69.2% |
| 2008 | 70 | 46 | 65.7% |
| 2009 | 71 | 51 | 71.8% |
| 2010 | 79 | 58 | 73.4% |
| 2011 | 88 | 62 | 70.5% |
| 2012 | 86 | 68 | 79.1% |
| 2013 | 91 | 70 | 76.9% |
| 2014 | 90 | 75 | 83.3% |
| 2015 | 81 | 59 | 72.8% |
| 2016 | 104 | 82 | 78.8% |
| 2017 | 132 | 94 | 71.2% |
| 2018 | 125 | 66 | 52.8% |
| 2019 | 137 | 59 | 43.1% |
| 2020 | 112 | 42 | 37.5% |
| 2021 | 233 | 61 | 26.2% |
| 2022 | 97 | 6 | 6.2% |
| 2023 | 101 | 7 | 6.9% |
| 2024 | 114 | 3 | 2.6% |
| 2025 | 106 | 3 | 2.8% |
| 2026 | 61 | 0 | 0.0% |

Top sources present in `measurements_all.csv`: NBA Draft Combine (527), NBA Pre-Draft Camp (427), USA Basketball (412), LeBron James Camp (375), Portsmouth (247), Eurocamp (212), Nike Elite 100 (190), Nike Skills Academy (189), Kevin Durant Camp (133), Hoop Summit (129), Deron Williams Camp (98), Amare Stoudemire Camp (95), Nike Basketball Academy (78), Nets Workout (75), D-League Elite Camp (58).

### The 2018-2025 gap

DraftExpress stopped publishing in 2017 and the site went dark; the last event year in the archive is 2017. Players drafted 2018+ appear **only** through youth events measured in 2013-2017 (a Hoop Summit or a Nike/USA camp they attended in high school), so coverage falls away by construction and is ~0 for anyone whose first measured event would have been 2018 or later. Nothing in this collector can fix that; the gap has to be filled from live sources.

**Candidate supplements (listed only - deliberately NOT collected here):**

| source | what it adds | URL pattern |
|---|---|---|
| Nike Hoop Summit annual measurement release | measured height/wingspan/reach/weight for the World and USA teams, ages 16-18, the single closest substitute for the DX youth rows | `https://www.nbadraft.net/2024-nike-hoop-summit-world-team/`, `https://www.nbadraft.net/2023-nike-hoop-summit-world-team/` (the historical DX article series lives at `http://www.draftexpress.com/article/Nike-Hoop-Summit-Official-Measurements/`) |
| USA Basketball junior national team minicamp rosters | listed height/weight for U16-U18 invitees, twice a year | `https://www.usab.com/teams/5x5-mens-junior-national-team-minicamps/roster/{YYYY}-{april,october}-minicamp-roster` |
| FIBA U16/U17/U18/U19 event rosters | listed height with an exact tournament date, for international prospects | `https://www.fiba.basketball/en/events/fiba-u17-basketball-world-cup-{YYYY}/...` (plus the per-tournament Wikipedia squad pages) |
| NBA Draft Combine anthropometrics | the pre-draft end of the trajectory, 2000-2025, **already collected by this project** (`datarebuild/cmb_anthro.csv`) | `https://stats.gleague.nba.com/stats/draftcombinestats?LeagueID=00&SeasonYear={YYYY}-{YY}` |
| NBPA Top 100 Camp / Under Armour Elite 24 / adidas Nations releases | scattered youth measurement releases, generally via event press pages | event press releases; no stable machine-readable pattern |

Off-limits under COLLECTOR_RULES.md rule 3 and therefore **not** candidates: sports-reference.com, realgm, kenpom, synergy, proballers, nikeeyb / EYBL data.

## 8. Terms of service / politeness

* Everything is fetched from **web.archive.org**, which serves no `robots.txt` (HTTP 404 on `https://web.archive.org/robots.txt`, checked at build time), i.e. no crawl restriction is declared. draftexpress.com itself is never contacted - it no longer resolves to a site.
* One request at a time, **1.2-1.6 s apart**, single process; exponential backoff (5 s doubling, 6 attempts) on 429/500/502/503/504 and on transport errors; descriptive User-Agent naming the project and a contact address. The profile crawler waits for the listing crawler to exit rather than running in parallel.
* No login, no paywall, no Cloudflare/JS challenge is touched; the Internet Archive's own CDX API is used for enumeration instead of spidering.
* Archived DraftExpress content is third-party copyrighted material. It is used here only to derive numeric features; **player names never leave this Mac** - `measurements_all.csv` and `raw/` stay local, and the shipped `features.csv` is pid + numeric columns only.

> **Publication warning.** `/Users/kennakao/nba/datarebuild` is a git repo whose `origin` is the **public** GitHub repo `Spoofyy-1/DraftDB-Data`. Its `.gitignore` covers `novel/*/raw*/`, `*.html`, `*.gz` - so the HTML cache and the CDX indexes are safely excluded - but it does **not** cover `measurements_all.csv` (player names) or `provenance.csv` (DraftExpress player ids, which re-identify a pid). A blanket `git add -A` in that repo would publish both. Nothing here was committed, and `.gitignore` was deliberately left untouched; decide explicitly before committing.

## 9. Files

```
dx_crawl.py             listing crawler   (CDX -> one best capture per URL shape)
dx_profiles.py          profile crawler   (one capture per candidate DX id, +375
                        archived non-draftees with >=2 height years, for the regression)
dx_profiles_retry.py    re-asks Wayback at an earlier target for profiles whose nearest
                        capture was post-shutdown (dead-site shells)
dx_parse.py             all cached HTML  -> measurements_all.csv
dx_features.py          measurements_all -> features.csv / unmatched.csv / provenance.csv
dx_readme.py            regenerates this file from the artefacts
measurements_all.csv    one row per player-event  (LOCAL ONLY - contains names)
features.csv            pid + dx_* numeric features
unmatched.csv           pids whose DX identity stayed ambiguous, with reasons
provenance.csv          per pid: DX id, event years, sources, age source, captures
build_stats.json        shoe gap, regression coefficients, row/coverage counts
run.log                 crawl log
raw/cdx_full.json       CDX index of the measurement listing
raw/cdx_profiles.json   CDX index of /profile* (192,327 urls, 55,786 player ids)
raw/manifest.jsonl      one line per listing fetch (checkpoint + provenance)
raw/profiles_manifest.jsonl  one line per profile fetch
raw/pages/*.html.gz     cached listing captures
raw/profiles/*.html.gz  cached profile captures
raw/profile_meta.csv    per DX id: drafted year/pick, RCSI rank + class year, age at capture
raw/candidate_index.csv pid <-> candidate DX id map before the draft-year gate
```

### Re-running / resuming

```bash
cd /Users/kennakao/nba/datarebuild/novel/draftexpress
nohup python3 dx_crawl.py    >> run.log 2>&1 &   # skips anything already in raw/manifest.jsonl
nohup python3 dx_profiles.py >> run.log 2>&1 &   # waits for dx_crawl.py, then resumes
python3 dx_profiles_retry.py                     # optional 2nd pass, also resumable
python3 dx_parse.py && python3 dx_features.py && python3 dx_readme.py
```
Both crawlers are checkpointed per page and idempotent: killing and restarting them loses at most the in-flight request. To stop them, kill only their own script names (`pkill -f dx_crawl.py` / `pkill -f dx_profiles.py`), never a broad pattern.

## 10. Known limitations

* Year-only dating: a 24-month window is measured in event years, not months.
* The archive is incomplete by construction - only URL shapes the Wayback Machine actually captured can be replayed, so a player's event set is a subset of what the live site held.
* Where a listing row could not be joined to a profile row, its Source is blank; such an event is still counted and still contributes to the height/weight series, but its youth/pre-draft classification then falls back to the estimated age.
* Heights mix with-shoes and without-shoes reporting; the series uses with-shoes and adds 1.25 in to no-shoes-only events. Youth camps almost always report with shoes, the combine reports both, so most trajectories are with-shoes throughout.
* `dx_age_src = 3` (class-year proxy) is accurate only to about +-1 year and is flagged; ages for players with neither a wiki birthdate nor an archived profile are left blank rather than guessed.
* DraftExpress itself sometimes carried a measurement forward or reported a listed rather than measured height for camp rosters; no attempt is made to tell the two apart beyond keeping the (source, year) label.
