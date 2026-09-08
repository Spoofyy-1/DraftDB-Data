# nbadraftnet — NBADraft.net pre-draft scouting grades

Publisher-assigned 1-10 scouting grades, an Overall total, an NBA comparison and Strengths / Weaknesses
paragraphs for drafted players 2000-2026, taken **only** from Wayback Machine captures made **before the
player's draft-night cutoff**.

Motivation: Andrew Johnson's published regression on these grades
(<https://fansided.com/2016/03/09/breaking-down-scouting-factors-in-the-nba-draft/>) found the
Intangibles + Leadership pair explains ~11% of NBA performance variance and Quickness 3-10%, while the
Defense grade has no independent effect. The grades are integers assigned by the publisher, so extracting
them is pure transcription (rule 4: rule-based extraction only).

Source: NBADraft.net player profiles, via `https://web.archive.org` (CDX API + capture download).
The **live site is never requested** — it is behind a Cloudflare challenge (rule 3) and, more importantly,
NBADraft.net keeps editing profiles for years after a draft, so the live page is leakage.

---

## 1. Dating rule (rule 2)

A capture is usable only if its Wayback timestamp is **strictly before `DRAFT_NIGHT[year] 22:00 UTC`**
(18:00 ET on the first night of the draft, before the first pick). The cutoff dates are the ones in
`novel/COLLECTOR_RULES.md`. Per player the **latest** such capture that parses and verifies as that player
is used, so the grades are the site's final pre-draft opinion.

* Captures at or after the cutoff are counted per player in `status.csv` (`n_rejected_postdraft`) and never
  downloaded for features.
* `build()` re-asserts `capture_ts < cutoff` for every row it writes, so a post-draft capture cannot leak in
  through the cache.
* 2026 is not listed in `COLLECTOR_RULES.md`; `20260623` is used (the date in the colleague's builders).
  Any error there is in the conservative direction (an earlier cutoff only discards captures).
* No lower bound on capture age is imposed: a profile first written when the player was a high-school
  recruit is still pre-draft information. `sc_capture_days_before_draft` records the staleness so it can be
  controlled for (or used to filter) downstream.

## 2. Page layouts

Four distinct layouts, all parsed by `parse_profile()`:

| layout | URL | era | grid? |
|---|---|---|---|
| `old` | `nbadraft.net/profiles/<slug>.htm`, later `.asp` | 2000-2008 | no |
| `asp` | `nbadraft.net/admincp/profiles/<slug>.html` | 2007-2009 | yes |
| `drupal` | `nbadraft.net/players/<slug>` | 2008-2019 | yes |
| `wordpress` | `nbadraft.net/players/<slug>/` | late 2019 onward | yes |

* **`old`** (the original Sports Phenoms site, not in the colleague's implementation; found by enumerating
  `nbadraft.net/profiles/*` in CDX) is a plain bio table plus a
  `NBA Comparison: … Strengths: … Weaknesses: …` paragraph. **It carries no 1-10 grid**, so the 2000-2007
  classes get the text features, the comparison and `sc_has_profile` but no grades. From mid-2007 these URLs
  became JavaScript redirect stubs to the `admincp` page; a stub has no heading, so it fails name
  verification and the next-older capture is used instead.
* **`asp` / `drupal`**: the grid's row labels are a position-dependent *image*
  (`attribute_banner_<POS>.gif` / `parameters<N>.gif`), so the twelve numbers are unlabelled in the HTML and
  are mapped positionally. The banner image name (falling back to the page's NBA-position text) decides
  which of the two grids applies:
  * guards/wings: Athleticism, Size, Defense, Strength, Quickness, Leadership, Jump Shot, NBA Ready,
    **Ball Handling**, Potential, **Passing**, Intangibles
  * bigs (C / PF / SF-PF / F-C): the same, with **Rebounding** and **Post Skills** in place of Ball Handling
    and Passing
  A page whose banner cannot be resolved, or whose number of parsed cells does not equal 12, yields no grid
  (all grade columns empty) rather than a guessed mapping.
* **`wordpress`**: the grid is labelled in the HTML (`attribute-name` / `attribute-value`), so labels are
  read directly.
* A grade of `0` on the page means "not graded yet" and is stored as **missing**, never as 0.

## 3. Player → profile matching (rule 5)

1. Names are normalised: NFKD → ASCII (accents dropped), lower-cased, punctuation removed, trailing
   `Jr/Sr/II/III/IV/V` dropped; a transliteration variant (`ı→i`, `ł→l`, `đ→d`, `ø→o`, `ß→ss`, …) is tried as
   well. Slugs are normalised the same way (`karl-anthony-towns` → `karlanthonytowns`).
2. A hand-checked alias list (`ALIAS_PAIRS`, ported from the colleague's builders) covers name changes and
   nicknames the site used (`Enes Kanter/Freedom`, `Patty/Patrick Mills`, `Bones/Nahshon Hyland`, …). Pairs
   are applied symmetrically.
3. Candidate slugs are every indexed slug whose normalised form equals one of the player's keys.
4. **Ambiguity**: when one slug is claimed by two pids with the same normalised name, the slug is kept only
   for a pid whose draft cycle the capture timestamps fall in (`year-3 Sept 1` → cutoff). If claimants from
   **two different draft years** survive that filter they are two different people (the two Marcus
   Williamses, the two Chris Wrights, …): the slug is dropped for **both** and logged to `unmatched.csv` —
   never guessed. Claimants from the **same** draft year are one player entered twice under two spellings —
   the identity file carries `Cam Thomas` (2021, pick 27) and `Cameron Thomas` (2021, no pick), `Bub` /
   `Carlton Carrington` (2024) and `Mo` / `Maurice Williams` (2003) — so they share the profile and the same
   cutoff. Those three pairs are the only same-year collisions in the file, and all three were checked by
   hand; a genuine pair of same-named players in one class would have to be added to `unmatched.csv`
   manually. (`Tony L. Mitchell` and `Tony Mitchell`, both 2013 and genuinely different people, do not
   collide because the middle initial is kept.)
5. **Verification**: the downloaded page's own player name must match the roster name (exact after
   normalisation / alias, or `SequenceMatcher` ratio ≥ 0.85). A page naming somebody else marks that slug
   dead for the player (`name_mismatch`); a page with no readable name is skipped and an older capture tried.

## 4. Keyword dictionaries (rule 4)

Each `sc_kw_*` feature is the **number of regex matches** of a fixed dictionary over a fixed scope of the
profile text — no judgement, no LLM. Scope `both` = Strengths + Weaknesses; scope `weaknesses` = the
Weaknesses paragraph only (a "great motor" in Strengths is not a concern). Matching is case-insensitive.

| feature | scope | pattern (alternation) |
|---|---|---|
| `sc_kw_injury` | both | `injur`, `surger`, `knee`, `ankle`, `stress fracture`, `torn`, `tear`, `concussion`, `achilles`, `meniscus`, `acl`, `back (injur/issue/problem/surger/spasm)`, `bad back`, `foot (injur/issue/problem/surger)`, `out for the season`, `missed (the/most of the/the entire) season` |
| `sc_kw_upside` | both | `upside`, `ceiling`, `raw`, `project`, `long-term` |
| `sc_kw_motor` | weaknesses | `motor`, `effort`, `lazy`, `coast(s/ed/ing)`, `takes plays off`, `passive` |
| `sc_kw_character` | weaknesses | `character`, `matur`, `attitude`, `off-court`, `disciplin`, `red flag`, `coachab`, `ego`, `selfish`, `work ethic` |
| `sc_kw_shooting_concern` | weaknesses | `mechanic`, `inconsistent`, `poor shoot`, `free-throw`, `ft`, `streaky`, `shooting (form/stroke)`, `jump shot`, `jumper`, `three-point`, `3pt`, `perimeter shot`, `shooting range` |
| `sc_kw_nba_ready` | both | `polished`, `nba-ready`, `ready (to contribute/now/made)`, `day one`, `plug-and-play`, `contribute (immediately/right away)`, `immediate(ly) (impact/contribut)` |

The exact regexes are the single source of truth in `KEYWORDS` in `collect_nbadraftnet.py`.
`\b` word boundaries are used on the short tokens (`raw`, `ft`, `ego`, `acl`, `motor`, …).
A player whose profile has neither paragraph gets **missing**, not 0, for every `sc_kw_*`.

## 5. Deliverables

`features.csv` — one row per pid in the identity file, numeric only (rule 1):

| column | definition |
|---|---|
| `pid` | player id from the identity file |
| `sc_athleticism`, `sc_size`, `sc_defense`, `sc_strength`, `sc_quickness`, `sc_leadership`, `sc_jumpshot`, `sc_nbaready`, `sc_potential`, `sc_intangibles` | publisher's 1-10 grade, all positions |
| `sc_ballhandling`, `sc_passing` | 1-10, guard/wing grid only (empty for bigs) |
| `sc_rebounding`, `sc_postskills` | 1-10, big-man grid only (empty for guards/wings) |
| `sc_overall` | the site's published **Overall**: the sum of the twelve category grades (range ~12-120, e.g. Derrick Rose 104). It is exactly collinear with the grid when the grid parses; it is kept because it is the number the site headlines and because a handful of pages show Overall with an unresolvable grid |
| `sc_intang_lead` | mean of `sc_intangibles` and `sc_leadership` (the Johnson regression's factor); empty unless both are present |
| `sc_kw_injury`, `sc_kw_upside`, `sc_kw_motor`, `sc_kw_character`, `sc_kw_shooting_concern`, `sc_kw_nba_ready` | keyword hit counts, section 4 |
| `sc_words_strengths`, `sc_words_weaknesses` | word counts (`[A-Za-z][A-Za-z']*`) of the two paragraphs |
| `sc_capture_days_before_draft` | days between the capture's date and the draft-night date (always ≥ 0) |
| `sc_has_profile` | 1 if a verified pre-draft profile was parsed for this pid, else 0 |

`status.csv` — per pid: `draft_year`, `status`, `slug`, `capture_ts`, `n_captures` (all indexed captures of
the candidate slugs), `n_rejected_postdraft` (of those, how many are at/after the cutoff), `layout`.
Statuses: `ok`, `no_capture_before_draft` (profile exists, only post-draft captures), `no_profile` (no slug
matched the name), `name_mismatch`, `no_content`, `unverified_name`, `parse_failed`, `download_failed`,
`not_attempted`.

`comps.csv` — `pid`, `comp_name`, `capture_ts`. **Contains player names, so it stays on this Mac** (same rule
as the identity file); it is deliberately not merged into `features.csv`.

`provenance.csv` — `pid`, `draft_year`, `source`, `url`, `capture_ts`, `layout`, `days_before_draft`,
`fields_parsed`.

`unmatched.csv` — slugs dropped as ambiguous (section 3.4).

`cdx_index.csv` — every 200-OK capture of every NBADraft.net profile URL (ts, url, slug, layout).

`raw/<draft_year>/<slug>.html` + `.json` — the exact capture used, so re-runs and re-parses are offline.

## 6. Coverage

<!-- COVERAGE -->

Built 2026-09-08 from 173893 captures indexed over 8166 profile slugs.

| draft-year band | players | with pre-draft profile | with 1-10 grid | with Strengths/Weaknesses | median days before draft |
|---|---|---|---|---|---|
| 2000-07 | 582 | 303 (52%) | 44 (8%) | 293 (50%) | 14 |
| 2008-18 | 1017 | 913 (90%) | 616 (61%) | 619 (61%) | 8 |
| 2019-25 | 900 | 549 (61%) | 332 (37%) | 336 (37%) | 62 |
| 2026 | 61 | 19 (31%) | 19 (31%) | 19 (31%) | 212 |
| **all 2000-2026** | 2560 | 1784 (70%) | 1011 (39%) | 1267 (49%) | 17 |

Restricted to players with an actual draft pick (the identity file also carries undrafted players):

| draft-year band | drafted | with pre-draft profile | with 1-10 grid | with Strengths/Weaknesses |
|---|---|---|---|---|
| 2000-07 | 397 | 264 (66%) | 42 (11%) | 256 (64%) |
| 2008-18 | 584 | 575 (98%) | 501 (86%) | 501 (86%) |
| 2019-25 | 392 | 302 (77%) | 265 (68%) | 267 (68%) |
| 2026 | 60 | 18 (30%) | 18 (30%) | 18 (30%) |
| all | 1433 | 1159 (81%) | 826 (58%) | 1042 (73%) |

Per-year detail is in `status.csv`. Why the misses (all pids):

```
status
ok                         1784
no_profile                  380
no_content                  273
no_capture_before_draft     122
name_mismatch                 1
```

* `no_content` = the profile page existed pre-draft but the site had not written it yet: every grade
  shows `NA`/0 and there is no Strengths/Weaknesses text. Common on the WordPress site, where a page is
  created for every prospect.
* Of the 1784 profiles that were used, 1011 carry real grades; the other 773 have a grid of zeros
  (page graded after the capture, or never) or are the grid-less `old` layout, and contribute only the
  text features.
* Post-draft captures seen for these players and rejected: 66102.
* NBA comparisons captured in `comps.csv`: 1136.
* Layout of the captures actually used: drupal 1105, wordpress 312, old 255, asp 112.

Capture staleness (`sc_capture_days_before_draft`), share within N days of draft night:

| | <= 90d | <= 180d | <= 365d | <= 730d | median | max |
|---|---|---|---|---|---|---|
| all profiles | 78% | 83% | 89% | 94% | 17 | 3202 |
| graded profiles | 89% | 96% | 99% | 100% | 10 | 1150 |

## 7. Wayback etiquette (rule 3)

* One shared token bucket: **≥ 1.05 s between any two requests** to `web.archive.org`, across all threads
  (≈ 1 req/s), whether CDX or capture download.
* At most **2 requests in flight** (`--workers 2`; the CDX listing stage is single-threaded, so at most 2
  CDX queries could ever overlap and in practice only one does).
* Exponential backoff (10 s → 20 s → 40 s …, capped at 300 s) on 429 / 500 / 502 / 503 / 504 / 403 and on
  transport errors; the CDX API's "Temporarily Offline" HTML (served with status 200) is retried with a
  15 s → 30 s → … backoff.
* Descriptive User-Agent identifying the project as non-commercial research.
* Captures are fetched with the `id_` raw flag (no Wayback rewriting), falling back to the rewritten page
  only when the stored capture is zstd/brotli-encoded.
* Only `web.archive.org` is contacted. `nbadraft.net` itself is never requested (Cloudflare-gated), no
  logins or paywalls are touched, and nothing from the off-limits list in `COLLECTOR_RULES.md` is used.
* Everything is cached under `raw/` + `cdx_index.csv`, so re-parsing and rebuilding cost zero requests.

## 8. Known limitations

* **No grid before ~2007.** The 2000-2007 classes are covered by the `old` layout, which has no 1-10 grid;
  those pids have text/keyword features only. Grades effectively start with the 2007-2008 classes.
* **Many profile pages were never graded pre-draft.** ~500 pre-draft captures show the whole grid as `NA`/0
  (the site created the page but had not scored the player yet). Those become missing grades — never 0 — and
  contribute only text features; another ~270 pids (`no_content`) have a page with neither grades nor text.
  This is what caps the 2019-2025 grid coverage, not the crawler.
* **The 2026 class is thin.** The Archive holds very few 2026 captures of the site (96 profile captures in
  all of 2026), so most of that class is `no_profile` / `no_content`. Its cutoff is also the assumed
  `20260623` (see section 1).
* **Grid labels are positional** on the `asp` / `drupal` layouts. The mapping is driven by the position
  banner image; a page whose banner is missing *and* whose NBA-position text is empty gets no grid.
* **Recency varies.** `sc_capture_days_before_draft` ranges from ~0 to several hundred days: the Archive did
  not crawl every profile in June of every year. Some players' latest pre-draft capture is a HS-era profile.
  Treat it as a control variable.
* **Overall is a sum, not a 1-10 grade** (see above).
* **The site's own grid changed shape over time** (early `asp` pages occasionally show a different number of
  blocks); those pages are stored but yield no grid.
* Players whose profile the Archive only holds after their draft night are `no_capture_before_draft` and
  intentionally have **no** features — using the post-draft page would be leakage.
* Same-name pairs from different draft years (e.g. the two Marcus Williamses) are dropped rather than
  guessed; see `unmatched.csv`.
* A handful of late second-round picks simply have no profile page in the Archive under any spelling
  (Jalen Slawson 2023, Brooks Barnhizer / Max Shulga / Jahmai Mashack 2025, …): no slug with that surname
  exists in `cdx_index.csv` at all.
* One page is the site's own error: the 2000 capture of `/profiles/mamadoundiaye.htm` contains Chris
  Porter's profile. It is rejected by name verification (`name_mismatch`) rather than used.

## 9. Re-running / resuming

```bash
cd /Users/kennakao/nba/datarebuild/novel/nbadraftnet

# resume an interrupted crawl (status.jsonl is the checkpoint; finished pids are skipped)
nohup python3 -u collect_nbadraftnet.py download --workers 2 >> run.log 2>&1 &

# re-try players recorded as failures; --statuses narrows the re-try to the ones worth repeating
nohup python3 -u collect_nbadraftnet.py download --retry --workers 2 >> run.log 2>&1 &
python3 collect_nbadraftnet.py download --retry --statuses no_profile,download_failed --workers 2

# one draft class only
python3 collect_nbadraftnet.py download --years 2024,2025 --workers 2

# rebuild the csvs from the cache (offline, seconds)
python3 collect_nbadraftnet.py build

# rebuild the capture index from scratch (~10 min, 24 CDX queries)
rm cdx_index.csv && python3 collect_nbadraftnet.py index
```

`status.jsonl` is append-only and fsynced per player, so the crawl is safe to interrupt at any point; the
last record per pid wins. To stop the crawl, kill **only** the pid recorded in `crawl.pid`
(`kill $(cat crawl.pid)`) — never a broad pattern (rule 6).
