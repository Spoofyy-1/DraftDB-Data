# wikitext collector — rule-based biographical features from Wikipedia wikitext

One row per `pid` for all 2,560 drafted players (2000–2026) in
`identity_KEEP_SEPARATE/tabular_names.csv`. **Numeric columns only, no names, no free text.**
Extraction is 100 % regex + dictionaries (`dicts.py`), no LLM judgement about any player.

```
features.csv          pid + 36 numeric wk_* columns (missing = empty cell, never 0)
provenance.csv        pid, draft_year, has_current_article, predraft_status, predraft_rev_ts,
                      predraft_revid, current_fetch_date, draft_cutoff
unmatched.csv         pids whose cached article is a different person (identity guard, see §5)
ambiguous_names.csv   pids where a relative's name matched >1 all-time NBA player
coverage.txt          coverage table (also printed by report.py)
raw/predraft/<pid>.json   cached pre-draft revision (offline, resumable)
fetch_predraft.py     fetcher (MediaWiki API, <=1 req/1.1 s, descriptive UA, resumable)
build_features.py     feature builder      wtutil.py  parsing helpers   dicts.py  all dictionaries
report.py             coverage report     spotcheck.py  15-player validation print (names to
                      the terminal only)
```

Re-run: `python3 fetch_predraft.py` (skips cached pids, safe to interrupt/resume) then
`python3 build_features.py && python3 report.py`. Everything after the first fetch is offline.

---

## 1. Sources and dating

| source | what it is | used for |
|---|---|---|
| `datarebuild/wiki_raw/current/<pid>.json` | current article wikitext, fetched **2026-09-08** (pre-existing project cache; 2,372 of 2,560 pids) | **time-invariant** facts only: relatives, HS sports, pathway, birthplace, handedness |
| `raw/predraft/<pid>.json` | the last revision **strictly before** the player's draft-night cutoff, fetched by `fetch_predraft.py` from `https://en.wikipedia.org/w/api.php` | **time-varying** facts only: injuries |
| `datarebuild/nba_all_players.json` | NBA all-time player list (`DISPLAY_FIRST_LAST`, `FROM_YEAR`, `TO_YEAR`) | deciding whether a named relative is an NBA player and when his career began |
| `datarebuild/age_verified_wiki.csv` | 947 verified birthdates | cohort offset (primary birthdate source) |

**Draft-night cutoffs** are the dates in `COLLECTOR_RULES.md` at 22:00 UTC
(2000-06-28 … 2025-06-25). 2026 is not in that table; `2026-06-24` is taken from the project's own
`wiki_raw/attn_*.json` cache, which agrees with the rules table for every year 2000–2025.

**Pre-draft revision selection** — one API call per player:
`action=query&prop=revisions&titles=<title>&rvprop=timestamp|content|ids&rvslots=main&rvlimit=1&rvdir=older&rvstart=<cutoff>&redirects=1`,
User-Agent `DraftDB-research/1.0 (NBA draft research; contact mike@alphax.inc)`, ≥1.1 s between
requests, exponential backoff on 429/503. A returned revision is used only if its timestamp is
strictly `< cutoff`. Page histories follow page moves, so a later rename does not lose the
pre-draft text. `status` is recorded per pid: `ok` / `no_predraft_rev` (article created after the
draft) / `missing_page` / `error:*`.

**Dating inside injury text.** A sentence contributes an injury only if it carries a date or season
expression that resolves **before the cutoff**:

| expression | resolved to |
|---|---|
| `March 11, 2014` / `11 March 2014` | that date |
| `March 2014` | first of the month |
| `2012–13`, `2012–2013` | 1 October 2012 (season start) |
| bare `2013` | 1 January 2013 (earliest reading) |

Dates more than 12 years before the draft are ignored (they describe someone else, e.g. a parent).
A sentence with **no** date inherits the most recent qualifying date already seen **in the same
section** (section-level date propagation; the section heading is parsed first, so
`===Freshman season (2018–19)===` seeds the context). Sentences with no date and no section
context are never counted.

---

## 2. Feature dictionary

Missing (empty cell) always means "not knowable from the source", never 0.
`wk_has_article` = 0 and `wk_article_identity_ok` = 0 rows have every article-derived column empty.

### identity / availability
| column | definition |
|---|---|
| `wk_has_article` | 1 if a current-article cache exists for the pid, else 0 (all 2,560 rows populated) |
| `wk_article_identity_ok` | 0 if the cached article's birth year implies an age at draft outside 17–32 → the cache holds a different person (§5); missing when there is no article |
| `wk_has_predraft_rev` | 1 if a usable pre-draft revision exists, 0 if the article did not exist before draft night, missing if the pid was never fetched |

### 1 — NBA relatives (current article, time-invariant)
| column | definition |
|---|---|
| `wk_nba_relative` | 1 if ≥1 linked relative matches the all-time NBA player list **and** that player's `FROM_YEAR` < prospect's draft year |
| `wk_nba_relative_seasons_pre_draft` | max over matched relatives of `min(TO_YEAR, draft_year-1) − FROM_YEAR + 1` (seasons completed before the draft), 0 when none |
| `wk_n_relatives_pro_any_sport` | number of distinct linked relatives named in a strictly adjacent kinship phrase whose sentence contains a professional-sport token (dictionary below) |
| `wk_relative_is_parent` | 1 if a matched NBA relative is a parent ("son/daughter of X", "his father, X") |
| `wk_relative_is_sibling` | 1 if a matched NBA relative is a sibling ("brother/sister/twin of X", "his brother, X") |

**Kinship patterns** (`dicts.KIN_PATTERNS`), class = the relation of the *linked* person to the prospect:

* PARENT — `(the)? (older|younger|half|step|adoptive…)? (son|daughter|child) of`, `his/her (half-|step-|late…)? (father|dad|mother|mom|parents)`
* SIBLING — `(older|younger|twin|half-|step-…)? (brother|sister|sibling|twin) of`, `his/her (older|younger|twin|half-…)* (brother|sister|twin|sibling)`
* EXTENDED — `(nephew|niece|cousin|grandson|granddaughter|godson) of`, `his/her (great-)? (uncle|aunt|cousin|grandfather|grandmother|godfather|nephew)`
* dropped — `(father|mother|uncle|aunt|grandfather|grandmother) of [[X]]`: there X is the *descendant*, never a pre-draft NBA relative of the prospect.

**Windows.** A wikilink is attributed to the nearest kinship phrase when it starts ≤ 100 chars after
an `… of` phrase, or ≤ 45 chars after a possessive phrase, with no `.` or `;` in between; or when a
possessive phrase starts ≤ 30 chars after the link with only whitespace/commas between
("[[Doc Rivers]], his father"). The *strict* window used for `wk_n_relatives_pro_any_sport`
additionally requires ≤ 45 chars and no comma and no " and " in the gap.

**Link filters.** A candidate link must look like a person (2–5 capitalised tokens, no digits, no
institution/team/event keyword from `wtutil.NON_PERSON`) and must **not** be preceded by "the "
("spent most of his NBA career with the [[Charlotte Hornets]]"). A candidate is also rejected when a
non-athlete occupation word sits between the kinship phrase and the name
(`dicts.NON_SPORT_OCCUPATION`: senator, judge, pastor, teacher, engineer, singer, police, …) — this
is what stops "the son of former Utah state senator Al Jackson" matching the 1960s NBA player of
that name.

**Sentence-level exclusions** (whole sentence dropped for relative extraction): relations by
marriage or naming — `in-law`, `god(father|mother|son|daughter)`, `named after/for`, `in honour of`,
`namesake`, `marri(ed|age)`, `wife`, `husband`, `girlfriend`, `fiancé` (an in-law relation is also
usually a *post*-draft fact), and `<Name>'s (teammate|coach|friend|agent|trainer|wife|husband|
mother|father|brother|sister|son|daughter)`, which marks a kinship phrase belonging to *another*
person ("Payton's teammate Klay Thompson and his father, Mychal").

**Name matching.** Both the link target and the display text are normalised (NFKD accent strip,
lower-case, punctuation removed, `(basketball)`-style disambiguators and interwiki prefixes removed,
`Jr/Sr/II/III/IV/V` suffixes removed) and looked up in the all-time NBA list; ≥2 tokens required.
The prospect's own `nba_id` is excluded (so "Tim Hardaway Jr." does not match himself, but his
father does). Where a normalised name matches several NBA players, the candidate with the most
pre-draft seasons is used and the pid is logged in `ambiguous_names.csv`.
A link must also look like a person (2–5 capitalised tokens, no digits, no institution keyword).

`wk_n_relatives_pro_any_sport` additionally drops a relative whose **NBA career started in or after
the prospect's draft year** (e.g. Kevon Looney, cousin of 2007 draftee Nick Young; Mychel Thompson,
brother of 2011 draftee Klay), because that fact was not knowable on draft night. The same test
cannot be applied to non-NBA relatives (NFL/WNBA/Olympic), so a small amount of "became a pro later"
leakage remains for them, and the pro-sport token is matched at *sentence* level, so a non-athlete
named in the same sentence as an athlete relative can be counted.

**Professional-sport tokens** (`dicts.PRO_SPORT_TOKENS`): NBA, National Basketball Association,
WNBA, ABA, NFL, National Football League, AFL, MLB, Major League Baseball, NHL, MLS, CFL, Olympic/
Olympian, EuroLeague, FIBA, "professional(ly) basketball/football/soccer/baseball/volleyball/
handball/rugby/hockey/tennis/athlete/player/career", "played professionally", "pro basketball",
Premier League, La Liga, Serie A, rugby league/union, Nippon Professional Baseball.

### 2 — High-school multisport (current article, time-invariant)
| column | definition |
|---|---|
| `wk_hs_multisport` | 1 if ≥1 non-basketball sport is found in the HS/early-life sections, else 0; **missing when the article has no such section** |
| `wk_hs_football` | 1 if American football is among them |
| `wk_hs_track` | 1 if track & field is among them |
| `wk_n_hs_sports` | number of distinct non-basketball sports found |

Sections searched: headings matching `early life | high school | highschool | youth | prep |
early years | amateur career | childhood | early career and | schooling | junior career | recruit`.
Sport dictionary (`dicts.HS_SPORTS`): football (also gridiron, quarterback, wide receiver, tight
end, linebacker, defensive end/back/lineman, running back, cornerback), track (track and field,
track team, ran track, bare "track" unless followed by record/to/for, high/long/triple jump, shot
put, discus, javelin, hurdles, sprinter, 100/200/400/800 meters, relay team), baseball (shortstop,
outfielder, pitcher), soccer (association football, futsal), volleyball, swimming (swim team, swam,
water polo), tennis, cross country.

A sport counts only when **all** of these hold — the "did the *player* play it" rule:
1. a participation verb (`played/plays/playing, ran, competed, participated, lettered, starred,
   excelled, threw, swam, wrestled, member of, part of, starter on/for, standout in, took up,
   picked up, three-/two-/multi-sport, all-state in, quarterbacked for, dabbled in`) ends ≤ 100
   chars before the sport token — or the token continues a list ≤ 60 chars after an accepted token
   ("played football, soccer and baseball");
2. the sentence contains no kinship word (`dicts.KIN_ANY`) — kills "his mother ran track";
3. the sentence contains the player's own first or last name, or `he/his/him/himself` — kills
   "Lateef Williamson was a football defensive lineman" in Zion Williamson's article.

Bare "football" is read as **soccer** when preceded by "association" or when the player was born
outside the US/Canada, otherwise as American football (documented ambiguity; `soccer` is a separate
sport in `wk_n_hs_sports`).

### 3 — Pathway (current article, time-invariant)
| column | definition |
|---|---|
| `wk_prep_year` | 1 if lead/HS/college text matches `prep(aratory) school`, `post-grad(uate) (year/season)`, `PG year`, `fifth year of high school`, or a case-sensitive `<Name> Prep` school name (Findlay Prep, Huntington Prep). Prep schools whose name carries neither token (Brewster Academy, Oak Hill Academy) are missed |
| `wk_reclassified` | 1 if the same text matches `reclassif` |
| `wk_reclass_direction` | +1 = moved to an **earlier** graduating class (accelerated), −1 = **later** class (extra year); from `reclassif… class of YYYY` compared with `from the class of YYYY to the class of YYYY` or with the other "class of" years in the article; missing when the direction is not stated |
| `wk_juco` | 1 if text matches `junior college`, `JUCO`, `community college`, `NJCAA` |
| `wk_n_colleges` | distinct college wikilinks in the infobox `college` field (fallback: bullet count); missing when the field is absent (typical for players who never attended a US college) |
| `wk_transferred` | 1 if `wk_n_colleges ≥ 2` **or** a transfer phrase appears in a *college* section (`transferred to/from`, `transfer portal`, `decided to/would transfer`, `after transferring`, `transferring to`) |
| `wk_hs_transferred` | same transfer phrases inside the HS/early-life sections (high-school transfers are a different pathway signal); missing when there is no HS section |
| `wk_hs_class_year` | HS graduating class year |
| `wk_hs_class_year_src` | 1 = explicit `class of YYYY`; 2 = explicit `graduated … YYYY` / `YYYY graduate` / `senior year … YYYY–YY` in the HS section; **3 = infobox college start year (proxy, not an explicit HS class)** |
| `wk_years_hs_to_draft` | `draft_year − wk_hs_class_year` (for src 3 this is years from college entry to the draft) |
| `wk_cohort_offset_days` | `birth_date − 1 January of (class_year − 18)`; **computed only for src 1/2** |
| `wk_reclass_up_flag` | 1 if `wk_cohort_offset_days < −120` |
| `wk_reclass_down_flag` | 1 if `wk_cohort_offset_days > 250` |
| `wk_birthdate_src` | 1 = `age_verified_wiki.csv`, 2 = infobox `birth_date` template of the current article |

**Cohort offset — reference date.** The task text said "Sept 1 of the year the class began 9th grade
(class_year − 4)"; taken literally that is ~5,300 days before any birthdate and cannot be compared
with ±120/250-day thresholds, because the ~18-year age offset is missing. The reference used here is
**1 January of (class_year − 18)**, the centre of the cohort's birth-year window: with a 1 September
school cut-off a normal cohort is born between 1 Sept (class_year−19) and 31 Aug (class_year−18),
i.e. offset −122 … +242 days — exactly the range the ±120/250 thresholds describe. Sanity check:
LeBron James (class of 2003, born 30 Dec 1984) → offset −2 days; the observed median across all
players is −4 days.

**Direction warning.** `wk_cohort_offset_days` is unambiguous: **negative = older than the class
cohort** (an extra/repeated year, prep year), **positive = younger** (skipped ahead). The two flag
names come from the task spec and follow the "reclassified up = took an extra year" convention:
`wk_reclass_up_flag` (offset < −120) marks players who are **old** for their class, and
`wk_reclass_down_flag` (offset > 250) marks players who are **young** for it. Note this is the
opposite sign convention to `wk_reclass_direction`, which uses the plain reading of the article text
(+1 = moved to an earlier class). Prefer the raw offset in models.

**Class-year plausibility guards.** Candidates are taken in order src 1 → 2 → 3 and the first one
passing both checks is used: (a) `1 ≤ draft_year − class_year ≤ 8`; (b) for src 1/2 with a known
birthdate, `|cohort offset| ≤ 700 days` (≈2 cohort years). This rejects college graduating classes
("Lehigh class of 2013" in a 2013 draftee's article) and other people's class years, falling back to
the college-start proxy.

### 4 — Injuries (**pre-draft revision only**, never the current article)
| column | definition |
|---|---|
| `wk_inj_sev3` | 1 if ≥1 dated severity-3 hit |
| `wk_inj_sev2` | 1 if ≥1 dated severity-2 hit |
| `wk_inj_sev1` | 1 if ≥1 dated severity-1 hit |
| `wk_n_surgeries` | number of non-negated dated surgery mentions (`surgery`, `surgeries`, `underwent an operation`, `arthroscopic procedure/surgery`) |
| `wk_inj_recency_seasons` | `draft_year − season_end_year(latest qualifying injury date)`, where a date in Jan–Jun belongs to the season ending that year; missing when no injury was found |
| `wk_inj_any` | 1 if any severity or surgery hit |

All six are **missing** when there is no usable pre-draft revision (`wk_has_predraft_rev` = 0 or
missing); they are 0 when a pre-draft revision exists and nothing was found.

*Severity 3* — torn/tore ACL or anterior cruciate ligament, ACL tear/injury/reconstruction/surgery/
repair, Achilles, microfracture, navicular, Lisfranc, stress fracture within 60 chars of back/
lumbar/spine/spinal/vertebra/tibia(l)/pars/femur/foot/navicular, herniated disc/disk, disc
herniation, spondylolysis, spondylolisthesis, patellar tendon tear/rupture, ruptured patellar/
Achilles/ACL, torn MCL/PCL.
*Severity 2* — surgery/surgeries/surgical, underwent an operation, arthroscopic, meniscus/meniscal,
fracture(d), broke/broken hand·wrist·foot·leg·arm·finger·thumb·jaw·nose·ankle·collarbone·clavicle,
out for the (rest/remainder of the) season, season-ending + an injury noun, injury/surgery/torn/
tear/fracture within 30 chars of "season-ending", missed the rest/remainder of the season, sidelined
for the season, redshirt within 40 chars of injur/surgery/medical, medical redshirt, ligament
injury/damage/tear/reconstruction, tore/torn ligament·labrum·meniscus·rotator cuff·hamstring·
quadriceps·groin·tendon·cartilage·ACL·MCL·PCL·UCL·plantar fascia·abdominal·pectoral·calf·hip.
*Severity 1* — sprain(ed), concussion, strain(ed), bone bruise, "missed … **games**" (plural, or with
an explicit count — "missed the game-winning shot" is not an injury), sidelined,
was placed in a cast, hyperextended, dislocated, tendinitis/tendonitis, plantar fasciitis, shin
splints, stitches, mononucleosis.

*Negation* — a hit is discarded if the 90 characters before it (same sentence) contain
`did/does/was/were/is/are/had/has/would/will/could + n't|not`, `not require/need/undergo/suffer/
sustain/miss/expected`, `never required/needed/underwent/suffered/missed/had`, `avoid(ed/ing)`,
`opted against`, `decided against`, `ruled out`, `without (the need for) surgery`, `no surgery/
structural damage/serious/significant/major`, `free of`, `in lieu of surgery`, `non-surgical`,
`should he require/need`, `if he requires/needs/had`.
*Other-person guards* — (a) sentences containing `teammate(s)`, `opponent`, `his coach`,
`his father/mother/brother/sister`, `replacing`, `in place of`, `filled in for`, `injury/injuries to`
are skipped ("following a season-ending injury to star point guard Aaron Brooks"); (b) a hit is
dropped when another person's full name stands in subject position in the 70 characters before it —
`<First Last> (was|is|had|suffered|underwent|tore|broke|missed|would|will|went|got|sustained|
required|exited|injured|returned)` and that name shares no token with the prospect's
("after starting center Zed Key was declared out for the season"). Team names ("against the Florida
Gators, Noel tore the ACL") are unaffected because they are not followed by such a verb.
Conditional/hypothetical surgery ("a hip problem that **may one day require** surgery") is treated as
negated.

### 5 — Birthplace (current article infobox `birth_place`, time-invariant)
| column | definition |
|---|---|
| `wk_birth_country_id` | ISO 3166-1 **numeric** country code (historical states use ISO 3166-3 numeric: Soviet Union 810, SFR/FR Yugoslavia + Serbia and Montenegro 891, Czechoslovakia 200, West Germany 280, East Germany 278; Zaire → DR Congo 180; England/Scotland/Wales → UK 826) |
| `wk_born_outside_usa` | 0 iff the country is the United States (840); US territories (Puerto Rico 630, USVI 850) count as 1 because their basketball pathway differs — use `wk_birth_country_id` to separate them |
| `wk_birth_state_id` | US **FIPS** state code (Alabama 1 … Wyoming 56, District of Columbia 11); missing for non-US births |

Parsing: the field is unlinked (`[[A|B]] → B`), parenthetical asides are dropped, then the
comma-separated components are read right-to-left against the country table (with a suffix match for
malformed values such as "SR Bosnia and Herzegovina SFR Yugoslavia"); if no country matches but a US
state name does, the country is set to 840 and the state to that state. The full country and state
tables are `dicts.COUNTRY_ID` / `dicts.STATE_ID`.

**City population band: skipped.** No free US city population table is present on this machine and
fetching one would add a second scrape target; the task allows skipping. `wk_birth_state_id` plus the
city string in the cache is enough to add it later.

### 6 — Handedness
`wk_left_handed` = 1 when the article says `left-handed / left-hander / lefty / leftie / naturally
left-hand*`, 0 when it explicitly says `right-handed / right-hander` and never says left, otherwise
**missing** (as specified: absence of a mention is not evidence of right-handedness). Sentences
containing a kinship word are excluded so a relative's handedness is not attributed to the player.

---

## 3. Fame bias — what was done about it

The known bias is that free-text features are easier to extract from long, heavily edited articles,
which belong to famous (i.e. better) players; a feature built that way partly encodes fame.

* **No article-size or edit-count feature is produced.** Article length, byte size, revision counts,
  editor counts and pageviews are all available in `wiki_raw/attn_*.json` and are deliberately
  **not** used here.
* **`wk_has_article` and `wk_has_predraft_rev` are exposed as explicit flags** and every derived
  column is empty (not 0) when the source is absent, so a model can condition on availability
  instead of silently reading "no article" as "no relatives / no injuries".
* **Time-varying facts use only pre-draft revisions**, so no post-draft edit (which is itself driven
  by NBA success) can leak in. Time-invariant facts (relatives, HS sports, birthplace, class year)
  use the current article, because the *fact* was knowable before the draft even if the sentence was
  written later — this is a deliberate recall/leakage trade-off and is the one place where article
  richness still matters.
* **Missingness is strongly draft-year dependent** — a usable pre-draft revision exists for only
  **17 %** of the 2000–07 band, against **72 %** (2008–18), **84 %** (2019–25) and **97 %** (2026).
  The injury block is therefore close to unusable before ~2008; interact it with
  `wk_has_predraft_rev` or restrict it to 2008+. Article coverage itself is high everywhere
  (93 % of all pids, 87–100 % by band), so the time-invariant features are far less affected.
* Residual bias that remains: among players who *do* have an article, a longer article is more
  likely to mention a relative, a high-school sport or a transfer. Treat all 0/1 "mention" features
  as **lower bounds**, and check any feature's usefulness against `wk_has_article` /
  `wk_has_predraft_rev` before trusting it.

## 4. Known limitations

1. Relatives must be **wikilinked**; "His father, George Sr., is an Army veteran" is invisible.
2. `wk_n_relatives_pro_any_sport` requires the pro-sport token in the same sentence, so a relative
   described as pro in a neighbouring sentence is missed.
3. Wikipedia's own claims are taken at face value (e.g. Devin Booker's article states he is the
   brother of Trevor Booker); the collector never adjudicates facts.
4. Explicit HS class years exist for only ~9 % of players, so `wk_cohort_offset_days` and both
   reclass flags are thin (~230 players). `wk_hs_class_year` itself is mostly the college-start
   proxy (src 3).
5. Injury recall depends on how much college/HS narrative the pre-draft article had; short stubs
   yield 0. Section-level date propagation can mis-date an injury by one season
   (`wk_inj_recency_seasons` is ±1).
6. Severity flags are not mutually exclusive — a torn ACL sets sev3 and usually sev2 as well.
7. `wk_transferred` uses the *current* article's college sections; a college transfer is always
   pre-draft for a drafted player, but the sentence may have been written afterwards.
8. 188 pids have no cached article at all and 33 more have the wrong person's article (§5).
9. The 2026 draft class (61 pids) is included for completeness; its cutoff came from the project's
   `attn_*` cache, not from `COLLECTOR_RULES.md`.

## 5. Identity guard

The pre-existing `wiki_raw` cache maps a few pids to the wrong article — common-name collisions such
as Gerald Henderson Jr. → *Gerald Henderson Sr.* (born 1956), Glen Rice Jr. → *Glen Rice*,
Dee Brown, Mike James, John Lucas, Bobby Jones. Rule: parse the article's birth year (infobox
`birth date` template, else `born … YYYY` in the lead) and require
`17 ≤ draft_year − birth_year ≤ 32`; 33 pids fail and are listed in `unmatched.csv` with
`wk_article_identity_ok = 0` and **all** article- and revision-derived features empty.
The infobox `draft_year` is *not* used for this check: it legitimately differs from the roster year
for undrafted players who entered the league later.
Known cost: exactly one correct article is suppressed by the upper bound — Pablo Prigioni, 35 years
old on 2012 draft night (the oldest drafted player). Widening the bound to 36 would let in three
genuinely wrong articles instead, so the bound stays at 32.

## 6. Terms of service / politeness

Only `en.wikipedia.org/w/api.php` is contacted (content is CC BY-SA; the API allows anonymous
read access). One request per player, ≥1.1 s apart, single-threaded, descriptive User-Agent with a
contact address, exponential backoff on 429/503, no login, no scraping of rendered HTML, results
cached under `raw/` so re-runs are offline. No off-limits site from `COLLECTOR_RULES.md` is touched.

## 7. Coverage

Final run (2026-09-08): 2,560 rows, 36 feature columns; 2,372 current articles (92.7 %), 2,339
usable after the identity guard (91.4 %), 1,664 usable pre-draft revisions (70.2 % of articles /
65 % of all pids; 707 articles did not exist before draft night, 1 revision had no content).
See `coverage.txt` (regenerate with `python3 report.py`) for non-missing rates and means by
draft-year band 2000-07 / 2008-18 / 2019-25 (plus 2026).
