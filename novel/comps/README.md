# comps — NBA-comparison prominence (pre-draft)

What the scouting-service comparison *itself* says about a prospect. NBADraft.net prints an
"NBA Comparison" on every profile ("Dirk Nowitzki/Tracy McGrady", "Nicolas Batum"). The name is
the publisher's opinion, but the **career the comparison player had built by draft night** is a
hard number: being likened to a 25-ppg All-Star is a different signal from being likened to a
career backup, and the difference is measurable without any judgement from this collector.

Input comparison strings come from the sibling collector `novel/nbadraftnet/comps.csv`
(`pid, comp_name, capture_ts`), which took them from Wayback captures made **before** each
player's draft-night cutoff. This collector adds no new text source: it parses those strings,
resolves them to NBA player ids, and measures each comparison player's career **as of the
prospect's draft night**.

```
build_comps.py resolve|fetch|build|all      # resume-safe, cache under raw/
report.py                                   # coverage + leakage assertions + spot check
```

---

## 1. Parsing rules (rule 4: regex + dictionaries only)

Applied in this order to the raw string:

1. **Trailing scout byline** `\s*[-–—]\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$` is removed **first**, because
   the date contains slashes that would otherwise be read as name separators
   (`"Rajon Rondo Nico Van den Bogaerd - 4/25/2008"`).
2. **Parenthetical / bracketed qualifiers** are removed: `\([^)]*\)`, `\[[^\]]*\]`
   (`"Kevin Garnett (gulp!)"`, `"Ben Wallace (more offense, less nastiness)"`,
   `"Fred Jones (more height, less skills)"`). Removing them before splitting is what keeps the
   commas *inside* a qualifier from being treated as separators.
3. **Split into one or more names** on `/`, `,`, `;`, `|`, `&`, and the word-boundary tokens
   `or`, `and`, `vs`, `meets` (case-insensitive). In this corpus only `/` (347 strings) and `,`
   (4 strings, all inside qualifiers except one) actually occur; the rest are supported for
   robustness. Curly apostrophes are folded to `'`; leading/trailing punctuation is trimmed.
4. **Descriptor stripping** produces a *second, fallback* form of each piece: leading tokens that
   are lower-case or in the descriptor dictionary and trailing descriptor tokens are dropped
   (`"A taller version of his brother Brevin Knight"` → `Brevin Knight`; a hypothetical
   `"poor man's Dirk Nowitzki"` → `Dirk Nowitzki`). The descriptor dictionary is the constant
   `DESCRIPTORS` in `build_comps.py` (poor, man's, athletic, taller, version, of, his, brother,
   young, less, more, …).
   **The stripped form is only used if the verbatim piece fails to resolve**, so real surnames that
   collide with descriptors are never eaten — `"Joseph Young/Malcolm Lee"` keeps *Young*, and
   `"Kendall Gill/James Young"` keeps *Young*, because both resolve verbatim.

1,136 comparison strings → **1,483 comparison names** (789 prospects with one comp, 347 with two).

## 2. Resolution rules (rule 5)

Every name is matched against `nba_all_players.json` (`commonallplayers`, `resultSets[0]`:
`PERSON_ID, DISPLAY_FIRST_LAST, FROM_YEAR, TO_YEAR`, 5,213 players). Normalisation: NFKD accent
strip (`Schröder`→`Schroder`), lower-case, drop `.` `'` `` ` ``, other punctuation → space
(so `O'Bryant`→`obryant`, `Carter-Williams`→`carter williams`), collapse spaces.

Tiers are tried in order; the first tier that yields a date-plausible candidate wins:

| tier | rule | example |
|---|---|---|
| 1 | exact normalised name | `Tim Duncan` |
| 1 | **alias dictionary** (below) | `Ron Artest` → `Metta World Peace` |
| 1 | space-insensitive | `Wang Zhizhi` → `Wang Zhi-zhi`; `Michael Carter Williams` → `Michael Carter-Williams` |
| 2 | generational-suffix tolerant (`Jr/Sr/II/III/IV`) | `Otto Porter` → `Otto Porter Jr.`; `Kevin Knox` → `Kevin Knox II` |
| 3 | **token drop** — a ≥3-token name with exactly one token removed matches exactly | `Luc Richard Mbah a Moute` → `Luc Mbah a Moute` |
| 3 | **roster middle-name key** — roster names of ≥3 tokens also indexed as first+last (only when that key is not itself a real full name) | `Cliff Robinson` → `Cliff T. Robinson` / `Clifford Robinson` |
| 3 | **nickname prefix** — same surname, one given name a prefix of the other (≥2 chars) | `Mo Bamba`↔`Mohamed Bamba`, `Lou Williams`↔`Louis Williams`, `Cameron Johnson`↔`Cam Johnson` |
| 3 | **typo tolerance** — Damerau-Levenshtein ≤1 (names <12 chars) or ≤2 (≥12 chars) on the full normalised string, restricted to candidates sharing the exact given **or** family name, unique minimum | `Aaron Baynes`→`Aron Baynes`, `Mookie Blalock`→`Mookie Blaylock`, `Byron Russell`→`Bryon Russell`, `Zarko Carbakapa`→`Zarko Cabarkapa` |
| 4 | greedy longest resolvable prefix, for pieces of >3 tokens | `Rajon Rondo Nico Van den Bogaerd` → `Rajon Rondo` |

**Date-aware disambiguation (the core of rule 5).** `ref_year` = the latest NBA season-start year
already under way at the capture timestamp (capture year if captured in October or later, else
capture year − 1). Among the candidates of a tier:

1. exactly one **active** at `ref_year` (`FROM_YEAR ≤ ref_year ≤ TO_YEAR`) → that player;
2. more than one active → **ambiguous, logged, not used** (`Marcus Williams`, two active in 2009 —
   the profile disambiguated with "(AZ)", which step 2 of the parser had already removed);
3. otherwise, among candidates already retired at `ref_year`:
   * if all candidates carry the *same* normalised name (true homonyms — the string cannot
     distinguish them) the writer means the more prominent one → **longest career**, then most
     recent (`Steve Smith` → Steven Smith 1991-2004, not the 2006 Steven Smith);
   * if the candidates came from *different* spellings joined by an approximate rule, a
     contemporary player is the likelier referent → **most recent**, then longest career
     (`Roy Devyn Marble` → Devyn Marble 2014-15, not Roy Marble 1989-93);
   * an exact tie on that key → ambiguous, logged, not used (`Tony Mitchell`, two players who
     both played only 2013-14);
4. every candidate debuts **after** the capture → not used (`Zabian Dowdell`, whose only NBA
   season began after the June-2010 capture that named him).

Two further guards:

* An **ambiguous** tier stops resolution — it never falls through to a fuzzier tier (without this
  the two Tony Mitchells fell through to `Todd Mitchell` at edit distance 2).
* An **explicit suffix** in the source (`Kenyon Martin Jr.`) may only be dropped by the suffix tier
  for a candidate who was *active* at the capture date, so a "Jr." comparison can never silently
  become the father. Father/son pairs listed under one name still resolve by the active rule
  (`Mike Dunleavy Jr` → the son, 2002-2016).

**Alias dictionary** (the complete list; nickname and listed-name changes no general rule reaches):
`fat lever`→Lafayette Lever, `jr rider`→Isaiah Rider, `penny hardaway`→Anfernee Hardaway,
`nene hilario`→Nene, `mo harkless`→Maurice Harkless, `rip hamilton`→Richard Hamilton,
`ron artest`→Metta World Peace, `saer sene`→Mouhamed Sene, `joseph young`→Joe Young,
`clarence witherspoon`→Clar. Weatherspoon, `luc richard mbah moute`→Luc Mbah a Moute,
`kenyon martin jr`→KJ Martin.

Unresolved names are written to `unmatched.csv` (`pid, draft_year, raw_comp, parsed_name,
match_rule, reason`); every resolved link is written to `provenance.csv` with the matched
`PERSON_ID`, the rule that matched it and the rule that disambiguated it.

## 3. Career source and endpoint

```
https://stats.gleague.nba.com/stats/playercareerstats?PlayerID=<PERSON_ID>&PerMode=Totals&LeagueID=00
```
browser-like headers (`User-Agent`, `Referer: https://www.nba.com/`, `Accept: application/json`,
`x-nba-stats-origin: stats`, `x-nba-stats-token: true`). `stats.nba.com` is **never** called — it
hangs from this network; the G League host serves the identical `stats` API. Response shape was
verified on PlayerID 1717 first: `resultSets` → `SeasonTotalsRegularSeason` with
`SEASON_ID` ("1998-99"), `LEAGUE_ID`, `GP, MIN, PTS, REB, AST, STL, BLK, FG3M/A, FTM/A, FG_PCT,
FG3_PCT, FT_PCT`.

One request per **unique** comparison player (841), ≈1 s apart (aggregate) with exponential
backoff, cached verbatim as `raw/<PERSON_ID>.json`. Re-runs are offline; delete a file to refetch
it. Resume with `python3 build_comps.py fetch`, or `fetch i/n` to run n polite workers that share
the id list (each sleeps `n × 1.1 s`, so the aggregate stays near 1 request/s); already-cached ids
are skipped, so any worker can be stopped and restarted.

Two practical notes for whoever re-runs this:

* the host resolves to IPv6 first on this network and the v6 connect stalls ~20 s before falling
  back, so `socket.getaddrinfo` is pinned to IPv4, and one keep-alive connection is reused per
  worker (a fresh TLS handshake per request is what gets throttled). Without both, the same job
  took 5-20 s per player instead of ~1.5 s;
* four ids answer `200 {}` with no result sets — `2752` Sergei Monia, `2762` Peter John Ramos,
  `101238` Boniface Ndong, `203510` Pierre Jackson, all fringe careers. That is recorded as
  `raw/<id>.empty` so re-runs never ask again, and the comparison is logged in `unmatched.csv`
  with reason `career_endpoint_empty`.

## 4. Dating rule (rule 2)

For a prospect drafted in year *Y*, only comparison seasons whose **`SEASON_ID` ends before draft
night** are used: season *S*/(*S*+1) qualifies iff *S* + 1 ≤ *Y*, i.e. **`S ≤ Y − 1`**.
The season "Y−1 to Y" counts because it ends in April–June of *Y*, before a late-June draft.
This holds for every cutoff in `COLLECTOR_RULES.md`, including the two displaced drafts:
the 2019-20 regular season ended 11 Aug 2020, before the **18 Nov 2020** draft, and the 2020-21
regular season ended 16 May 2021, before the **29 Jul 2021** draft. Only regular-season rows are
used (playoffs are a separate result set and are ignored), and the regular season always ends
months before the draft, so no season is ever partially included. `LEAGUE_ID != "00"` rows (ABA)
are dropped.

`report.py` re-asserts the rule over `provenance.csv`: no comparison player contributes seasons if
he had not debuted by *Y*−1, and no capture timestamp is later than the draft year.

## 5. Features (`features.csv`, one row per drafted pid, numeric only)

All averages are **over the resolved comparison players of that prospect** (1 or 2).
Empty = not knowable, never 0 for unknown. Three distinct states:

* prospect has **no captured pre-draft comparison** → the whole row is empty (unknown);
* prospect has a comparison string but **no name resolved** to an NBA player → `cp_n_comps` and
  `cp_resolved = 0` are filled, every measured feature is empty (this is itself informative: the
  comparison named a Euroleague or college player with no NBA career);
* resolved → all features filled, except a rate whose denominator is zero (a comp with no NBA
  minutes yet, no 3-point attempts, …), which stays empty.

| feature | definition |
|---|---|
| `cp_n_comps` | comparison names parsed from the string (1 or 2) |
| `cp_resolved` | 1 if ≥1 name resolved to an NBA player with career data, else 0 |
| `cp_n_resolved` | how many of them resolved |
| `cp_seasons_to_date` | mean number of qualifying NBA seasons the comp had played by draft night |
| `cp_min_to_date` | mean career minutes to date |
| `cp_pts36_to_date` | points per 36 minutes, **minutes-weighted** (pooled ΣPTS / ΣMIN × 36) |
| `cp_reb36`, `cp_ast36` | rebounds / assists per 36, same pooling |
| `cp_stk36` | (steals + blocks) per 36, pooled over **only** the seasons in which steals and blocks were recorded (the NBA did not track them before 1973-74), empty if none |
| `cp_fg3_pct_to_date` | pooled ΣFG3M / ΣFG3A to date (empty if no 3PA) |
| `cp_ft_pct_to_date` | pooled ΣFTM / ΣFTA to date |
| `cp_peak_mpg_to_date` | mean over comps of each comp's best single season MIN/GP to date |
| `cp_peak_pts_pg_to_date` | mean over comps of each comp's best single season PTS/GP to date |
| `cp_active_at_draft` | 1 if **any** comp played the season ending in *Y* (GP > 0), else 0 |
| `cp_years_since_comp_debut` | mean of *Y* − comp `FROM_YEAR` (how dated the comparison is) |
| `cp_comp_is_hall_tier` | 1 if **any** comp had ≥500 GP and ≥20.0 career PPG through the date |
| `cp_max_pts36_to_date` | max over comps of that comp's own points per 36 |
| `cp_max_peak_pts_pg_to_date` | max over comps of that comp's best season PTS/GP |

Design notes: pooled (minutes/attempt weighted) rates mean a two-name comparison is dominated by
the comp with the longer career, which is the conservative reading; the `max_` variants keep the
"one of the two names is a star" signal that averaging destroys. `cp_comp_is_hall_tier` is a
mechanical threshold (≥500 GP, ≥20 PPG **through the draft date**), not a Hall-of-Fame lookup —
so it stays pre-draft and needs no judgement about a player's legacy.

## 6. Coverage

`features.csv` has one row per drafted player (2560 pids, 2000-2026); 1136 carry a comparison string and 1108 resolved to at least one NBA comparison player (1448 prospect x comp links over 837 unique comparison players; 4 further ids were requested but the career endpoint returned no rows).

| draft-year band | drafted | with comparison | % | ≥1 comp resolved | % | mean comps/prospect |
|---|---|---|---|---|---|---|
| 2000-07 | 582 | 218 | 37.5% | 215 | 36.9% | 1.03 |
| 2008-18 | 1017 | 579 | 56.9% | 557 | 54.8% | 1.37 |
| 2019-25 | 900 | 320 | 35.6% | 317 | 35.2% | 1.38 |
| 2026 | 61 | 19 | 31.1% | 19 | 31.1% | 1.42 |
| all | 2560 | 1136 | 44.4% | 1108 | 43.3% | 1.31 |

Resolution of the comparison **names** themselves: 1483 parsed, 1448 resolved (97.6%), 35 unresolved. Reasons:

| reason | names |
|---|---|
| `no_name_match` | 28 |
| `career_endpoint_empty` | 4 |
| `ambiguous_multiple_active_at_capture` | 1 |
| `only_candidate_debuts_after_capture` | 1 |
| `ambiguous_retired_tie` | 1 |

Match rules that produced the 1448 links:

| rule | links |
|---|---|
| `exact` | 1360 |
| `editdist1` | 25 |
| `suffix` | 20 |
| `alias` | 18 |
| `nickname_prefix` | 11 |
| `editdist1+nickname_prefix` | 3 |
| `tokendrop` | 3 |
| `editdist2` | 3 |
| `midkey+nickname_prefix` | 2 |
| `exact+desc` | 1 |
| `tokendrop+prefix` | 1 |
| `nospace` | 1 |

## 7. Known limitations

* Comparison strings exist only for prospects whose NBADraft.net profile was captured before
  draft night, so coverage tracks the sibling collector's coverage, which is thin for 2000-2005
  (few Wayback captures of the old site) and richest after 2006.
* Comparisons to players who never appeared in an NBA game cannot be measured and are the bulk of
  what stays in `unmatched.csv` — Euroleague names (Bodiroga, Diamantidis, Ante Tomic, Felipe
  Reyes, Florent Pietrus, Ademola Okulaja, Jayson Granger) and college players who were never
  drafted or never played (Adam Haluska, Rick Rickert, Chris Lofton, Kris Jenkins, Patric Young…).
  These are *informative* absences — a comparison to a non-NBA player is a different kind of
  comparison — but this collector marks them `cp_resolved = 0` rather than inventing a value.
* A comparison to a player who had barely played yet (Fred Jones, 19 games and 115 minutes at
  the 2003 draft) produces a per-36 rate from a tiny sample. `cp_min_to_date` and
  `cp_seasons_to_date` are in the feature set precisely so a model can down-weight those.
* The comparison is a scout's opinion recorded once; `cp_years_since_comp_debut` is the only
  handle on how stale the comparison player is. It is deliberately not corrected for era
  (a 20-ppg scorer in 2004 and in 2018 are not the same player), so any downstream model should
  keep draft year in the feature set.
* `FROM_YEAR`/`TO_YEAR` come from `commonallplayers` and are season-start years; they are used
  only for disambiguation and for `cp_years_since_comp_debut`, never for the season totals.
* Two-name comparisons are treated as an unordered set; the site's ordering (usually
  ceiling-first) is not used.

## 8. ToS / rate

No new site is scraped. The comparison text was already collected by `novel/nbadraftnet`
(Wayback captures, never the live Cloudflare-protected site). The NBA `stats` API is queried
through the G League host at ≈1 request/s, once per unique comparison player, with a browser
User-Agent and exponential backoff, and every response is cached under `raw/` so re-runs make no
requests at all. No login, no paywall, no challenge bypass.

**Identity discipline**: nothing written here contains a prospect name. `features.csv` is numeric
and pid-keyed; `provenance.csv` / `unmatched.csv` carry only the publisher's comparison text and
the *comparison* player's NBA name. The spot check that prints prospect names joins
`identity_KEEP_SEPARATE/tabular_names.csv` in memory at report time.
