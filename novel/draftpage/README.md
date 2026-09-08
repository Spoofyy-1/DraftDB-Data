# draftpage — pre-draft features from the "YYYY NBA draft" Wikipedia article

Pid-keyed numeric features taken from the **last revision of the English Wikipedia
article `YYYY NBA draft` that predates draft night**. The article carries three
pre-draft signals that no other collector in this project has:

* the NBA's own **green-room invitation list** ("Invited attendees") — the league's
  public statement, days before the draft, about who it expects to go early;
* the **early-entrant declaration lists** (college underclassmen / seniors,
  international declarants, "other") as they stood at the withdrawal deadline;
* the **automatically-eligible** oddities (pro contract abroad, G League, no college).

Everything here is knowable before the player's draft night (COLLECTOR_RULES rule 2):
each record is a single MediaWiki revision with a timestamp strictly before the
draft-night cutoff, and the cut is verified by an assertion (below), not assumed.

```
draftpage/
  fetch_pages.py           26+1 API calls -> raw/YYYY.json  (resumable, offline re-runs)
  refetch_until_clean.py   walks back a revision when the emptiness assertion fires
  parse_pages.py           rule-based extraction + name matching -> the CSVs below
  raw/YYYY.json            cached revision (year,title,cutoff,status,rev_ts,revid,wikitext)
  raw/rejected/            revisions rejected by the assertion, kept for audit
  features.csv             pid + 8 numeric columns, one row per pid (2,560 rows)
  provenance.csv           per year: revid, rev_ts, oldid URL, cutoff, assertion result, list sizes
  counts_by_year.csv       per year: items found per list and how many matched an identity pid
  match_tiers.csv          every successful match with the tier that produced it (audit trail)
  unmatched.csv            every page name that did not resolve, with the reason
  run_fetch.log            fetch log
```

Re-run end to end (offline after the first fetch):

```
python3 fetch_pages.py          # skips years already in raw/
python3 refetch_until_clean.py  # no-op unless a cached revision fails the assertion
python3 parse_pages.py
```

## Source and API call

No API key is needed. One request per year, >= 1.2 s apart, descriptive User-Agent
`DraftDB-research/1.0 (NBA draft research; contact mike@alphax.inc) python-urllib/3`,
exponential backoff on 429/503. Wikipedia content is CC BY-SA; the API is the
sanctioned access path, so no ToS issue.

```
https://en.wikipedia.org/w/api.php?action=query&prop=revisions
    &titles=YYYY%20NBA%20draft
    &rvstart=<cutoff>&rvdir=older&rvlimit=1
    &rvprop=timestamp|content|ids&rvslots=main
    &format=json&formatversion=2&redirects=1
```

`<cutoff>` is `22:00:00Z` on the draft date from `COLLECTOR_RULES.md` (2000-2025).
2026 is not in that table; its date (`2026-06-24`) comes from this project's own
`wiki_raw/attn_*.json` cache, whose `draft_date` matches the rules table exactly for
every year 2000-2025. `rvdir=older` + `rvstart` returns the newest revision at or
before the cutoff; the fetcher additionally rejects any revision whose timestamp is
not strictly `< cutoff`.

## Dating assertion (proof the cut is clean)

The pre-draft revisions have an **empty player column** in the draft-results table —
the picks have not happened yet. `parse_pages.selection_table_check()` re-derives
this rather than trusting it:

1. find every wikitable with a header cell starting with `Player` and >= 10 data rows
   whose first cell is a bare pick number (this is a pick-by-pick results table);
2. read the player-column cell of every data row;
3. a cell counts as empty when it is blank, `&nbsp;`, or a `-` / `–` / `N/A` / `TBD`
   placeholder (2007 fills unused cells with `-`). Rows using `colspan` (2022/2023/2025
   "Forfeited pick" rows) cannot be column-aligned and are skipped.
4. if **any** player cell holds content, the year is aborted — no features are emitted
   for it and `dp_page_year_covered` is 0.

Result: 2005-2026 all pass, `player_cells_empty=1` in `provenance.csv` for every year,
27 results tables / 1,313 data rows checked in total, none naming a player.

**One year needed a walk-back.** For 2017 the last pre-cutoff revision
(21:49:44Z, 71 minutes before the draft began) had `[[Markelle Fultz]]` pre-filled at
pick 1 by an editor. Rather than dropping a rich year, `refetch_until_clean.py` steps
to the immediately preceding revision — still strictly pre-draft — until the assertion
passes, up to 40 steps. 2017 came clean after 2 steps at revision
`787004022` (2017-06-22T21:11:16Z); the two rejected revisions are kept under
`raw/rejected/`. Every other year passed on the first revision. If no revision within
the budget passes, the year is aborted exactly as specified.

## Coverage

| years | status |
|---|---|
| 2000-2004 | **missing** — `no_predraft_rev`: the articles were created after the fact, so there is no revision before the cutoff. `dp_page_year_covered=0`, all other columns empty. |
| 2005 | stub (7 KB): lottery prose + a "speculated picks" list. Only `dp_wiki_projected`. |
| 2006 | 12 KB: eligibility rules + "Projected draftees". Only `dp_wiki_projected`. |
| 2007-2008 | early-entrant and international declaration lists (plus withdrawal lists). No green room. |
| 2009 | prose only — the entrant *names* were added after the draft. Only `dp_page_year_covered`. |
| 2010 | early entrants + automatically eligible. No green room. |
| 2011-2019 | green room + early entrants + automatically eligible (the richest years). |
| 2020-2023 | early entrants + automatically eligible; **no green-room list** in the pre-draft revision (2020 was a virtual draft; 2021-2023 editors added the invitee list only after the draft). |
| 2024-2026 | green room (announced in dated waves) + early entrants. |

Per-year item counts and how many matched an identity pid are in `counts_by_year.csv`.
Green-room invitees found per year:

| year | invitees | matched | waves | days before draft |
|---|---|---|---|---|
| 2011 | 17 | 17 | annotated | — |
| 2012 | 14 | 14 | not distinguished | — |
| 2013 | 13 | 13 | annotated | — |
| 2014 | 21 | 21 | not distinguished | — |
| 2015 | 23 | 23 | not distinguished | — |
| 2016 | 19 | 19 | annotated | 5 |
| 2017 | 20 | 20 | annotated | 14 |
| 2018 | 20 | 20 | annotated | 6 |
| 2019 | 23 | 23 | annotated | 12 |
| 2024 | 24 | 24 | 3 dated blocks | 15 / 11 / 7 |
| 2025 | 24 | 24 | 3 dated blocks | 15 / 9 / 6 |
| 2026 | 24 | 24 | 3 dated blocks | 15 / 9 / 7 |

2005-2010 and 2020-2023 have no invitee list, so `dp_green_room` is **empty** (not 0)
for those years.

## Features (`features.csv`)

One row per pid for all 2,560 pids in the identity file. Missing is always empty,
never 0.

| column | definition |
|---|---|
| `dp_page_year_covered` | 1 if a pre-draft revision exists for the player's draft year; 0 for 2000-2004. |
| `dp_green_room` | 1 if the NBA invited the player to the green room; 0 for other players of a year that has an invitee list; empty for years without one. |
| `dp_green_room_days_before_draft` | days from the announcement of **that player's invite wave** to draft night; empty when the page does not date the wave, and for non-invitees. |
| `dp_green_room_wave` | 1 = named in the initial announcement, 2/3 = later addition; empty when the page draws no wave distinction, and for non-invitees. |
| `dp_early_entrant` | 1 if listed as an early entrant still in the draft at the cutoff (college underclassman, college senior, international, or "other"); 0 for other players of a year with such a list; empty for 2005, 2006, 2009 and 2000-2004. |
| `dp_intl_early_entrant` | 1 if that early-entrant listing was the international one. |
| `dp_auto_eligible` | 1 if named in the "automatically eligible entrants" **player table** — the unusual cases only. 0 means "not listed", **not** "not automatically eligible". |
| `dp_wiki_projected` | 1 if named in the editor-written "projected draftees" / "speculated picks" list (2005, 2006 only). A Wikipedia mock-draft consensus, not an NBA signal — treat separately from the others. |

**`dp_combine_invite` is not emitted.** No year's article contains a combine invitee
roster: every `Combine` section (2014-2026) is prose with zero list items and zero
table rows (verified programmatically). The 2019 section names ~8 players in narrative
asides, which is not a list and would require judgement to read as one, so nothing is
extracted from it.

**No pick-ownership features.** A player's slot is unknown pre-draft, and the results
table is empty by construction, so nothing about picks is derived.

Signal check (drafted players only): green-room invitees have mean pick 12.1 vs 38.0
for non-invitees of the same years; 235/242 (97%) went in round 1 and 159/242 (66%) in
the lottery. `dp_wiki_projected=1` averages pick 11.3 vs 34.0. `dp_early_entrant=1`
averages 24.0 vs 39.1.

## Parsing rules (all regex / dictionary, no judgement)

Applied to the raw wikitext after HTML comments are stripped (this removes the
commented-out decoy `==Invited attendees==` heading in 2018, and the commented-out
legend in 2015).

**Sections.** Split on `^(={2,6})\s*(.*?)\s*\1$`; each section carries the full
heading path, so a subsection is classified by its ancestors as well as its own title.

* green room — a section whose own heading matches `invit` **and** `attend`
  ("Invited attendees", and the 2018 typo "Invited attendents"). If no such heading
  exists, fall back to the part of any section from its first `green room` mention to
  the section end (this is how 2015 and 2016 carry the list, inside "Draft ceremony").
* early entrant — heading path matches `early entrant|early entry|underclassmen
  declaring|international players declaring`; the international variant additionally
  matches `international`.
* automatically eligible — heading path matches `automatic(ally)? eligib`.
* projected — own heading matches `projected draftees|speculated|other lottery picks`.
* withdrawn — heading path matches `withdraw|withdrew` and **not** `previous draft`
  (so 2007's "Have declared for and withdrawn from a *previous draft*" stays an
  early-entrant list, while "Did not sign with an agent and withdrew prior to draft"
  and 2008's "Withdrawn entrants" are withdrawal lists).
* 2015 has no international sub-heading — the split is carried by table captions, so a
  table caption matching `international` re-tags that table's rows, and
  `college|underclassmen|senior` un-tags them.

**Names.** From a `*` list item (`**` sub-bullets are notes and are skipped;
continuation lines are joined) or from the first cell of a table data row:
expand `{{sortname|First|Last}}` (2015) to `First Last`, drop `<ref>`s and HTML tags,
drop leading `{{flagicon}}`/`{{flag}}` templates and any leading `/`, `-`, `–` or `,`
separators (2013 writes `* {{flag|Spain}}, [[Álex Abrines]] – ...`); if what remains
starts with a wikilink, take its display text and its target; otherwise take the text
up to the first comma, dash or parenthesis.

An entry is kept only if the name passes a shape test: 2-5 tokens, every token
capitalised (or a name particle: de, van, der, dos, …), no digits, no institution
keyword (university, college, league, team, …). This is what separates the *rule*
bullets from the *player* bullets in the "automatically eligible" sections, whose
lists mix criteria ("They have completed four years of their college eligibility.")
with names. Verified: no rule text reaches `unmatched.csv`.

**Table rows.** Cells are split on `||` / `!!` honouring `[[ ]]` and `{{ }}` nesting,
and a `style="…"|` attribute prefix is dropped. A row counts as a header row only if
*every* cell came from a `!` line, so `plainrowheaders` tables — whose first cell is
`!scope="row"|{{flagicon|USA}} [[Player]]` — are read as data rows.

**Green-room waves and dates.**

* The invitee block is cut into list blocks (runs of `*` lines). Consecutive runs
  separated only by layout templates (`{{col-2}}`, `{{col-begin}}`, `{{div col}}`) and
  blank lines are merged, so a two-column wave is one block, not two.
* If there are >= 2 blocks (2024, 2025, 2026), `dp_green_room_wave` is the block index.
* If there is one block, the wave comes from the per-line annotation
  `not on the original list` / `added later` / `later invited` → 2, else 1. If **no**
  line in the block carries such an annotation (2012, 2014, 2015), the page draws no
  distinction and `dp_green_room_wave` is left **empty** rather than asserting 1.
* The announcement date for a block is the first `Month D[, YYYY]` in that block's
  preamble prose, accepted only if it falls in the draft's calendar year and in the
  120 days strictly before draft night. Dates inside `<ref>` citations are **not**
  used: the boilerplate green-room paragraph is copy-pasted between years and carries
  a 2011 ESPN citation, which would have dated 2015-2018 to June 2011.
* If a later block has no explicit date, a relative phrase in its preamble resolves
  against the previous block's date: "the following/next day" (+1), "N days later"
  (word or digit), "the following week" (+7). This is what dates the third 2025 wave
  ("announced three days later" → June 19).
* `dp_green_room_days_before_draft` = draft date − block date, assigned to that block's
  players. In single-block years the date is withheld from players annotated as later
  additions, because the prose gives several later dates (2017 lists three separate
  additions, 2019 four) and none can be attributed to an individual by rule.
* 2015 has no bullet list at all: the invitees are named inline. A prose sentence is
  read as an invitee list only if it matches `invit` and contains >= 3 person-shaped
  wikilinks. That captures both "The 20 players who are invited … are [[…]], …" and
  "Three other players, [[R.J. Hunter]], [[Tyus Jones]], and [[Delon Wright]] all had
  invitations as well, but they each declined". **Those three are coded
  `dp_green_room=1`**: the feature records the NBA's invitation, which is the pre-draft
  signal, not attendance. Sentence splitting never cuts inside a `[[wikilink]]`, so
  names with initials survive.

**Withdrawn entrants** are excluded from `dp_early_entrant` (a player listed only as
withdrawn is coded 0 — as of the last pre-draft revision the page says he is not in
the draft). In practice no identity-file player appears in a withdrawal list, so this
rule never fires; it is kept for correctness.

## Name matching

Normalisation: strip disambiguators `(basketball)`, decompose and drop accents,
lowercase, drop `.`/`'`/`` ` ``, collapse to `[a-z0-9 ]`, strip Jr/Sr/II/III/IV/V
suffixes, then merge runs of single letters so `R. J. Barrett` → `rj barrett` and
`J.J. Redick` → `jj redick`.

Every candidate must be in the **same draft year** as the page. Tiers are tried in
order, on the link display text and then on the link target; each must yield exactly
**one** candidate inside that year or the entry goes to `unmatched.csv` as ambiguous
rather than being guessed (COLLECTOR_RULES rule 5):

| tier | rule | n |
|---|---|---|
| `exact` | normalised strings equal | 1,488 |
| `prefix` | one token list is a leading sub-sequence of the other (`Timothé Luwawu` ≈ `Timothe Luwawu-Cabarrot`) | 3 |
| `firstpfx` | same surname and one given name is a prefix of the other (`Alexandre Sarr` ≈ `Alex Sarr`, `Mohamed Bamba` ≈ `Mo Bamba`) | 13 |
| `surname` | same surname (>= 5 chars), **green-room list only** — a short curated list where a nickname can replace the given name (`Edrice Adebayo` ≈ `Bam Adebayo`) | 1 |
| `alias` | a (page name → pid) mapping established on one list of that year, reused on the other lists of the same year | 1 |

Where the page annotates a birth year (`born 1988`, the 2007/2008 international lists,
and `(basketball, born 1997)` disambiguators) and `age_verified_wiki.csv` has a
verified birth date, the years must agree or the match is rejected.

All 17 non-exact matches were audited by hand and are correct; `match_tiers.csv` lists
every one so the audit is repeatable.

The `surname` tier is deliberately **not** allowed on the long entrant lists. Those
lists contain 30-200 names a year, most of whom never reached the NBA, and a
surname-only rule mismatches them onto same-surname drafted players
(`Jontay Porter` → `Kevin Porter Jr.`, `Manny Bates` → `Emoni Bates`,
`JaMichael Morgan` → `Juwan Morgan`). Requiring the same first initial does not fix it
(`Justin Jackson` → `Jaren Jackson Jr.`), so those entries are logged, not guessed.

## Unmatched

563 page names did not resolve to a pid (`unmatched.csv`, all with reason `no_match`
after the tier restrictions above; there are no remaining ambiguous or birth-year
conflicts). The overwhelming majority are players who never reached the NBA and are
therefore absent from the identity file — 326 come from the early-entrant lists, 102
from the international lists, 73 from the withdrawal lists, 61 from the automatically
eligible tables, 1 from the 2006 projected list. Every green-room name in every year resolved.

Known genuine misses, all nickname or name-order cases the rules refuse to guess:

* `Iggy Brazdeikis` (2019) vs identity `Ignas Brazdeikis`;
* `Marcos Louzada Silva` (2019) vs `Didi Louzada`;
* `Saer Sene` (2006, projected list) vs `Mouhamed Sene`;
* `Guillermo Hernangómez` (2015) vs `Willy Hernangomez`;
* `Nah'Shon Hyland` (2021) vs `Bones Hyland`;
* `Moe Harkless` (2012) vs `Maurice Harkless`.

Each of these makes one `dp_early_entrant` a false 0. A curated alias table would fix
them, but that is a hand-built dictionary of individual players, so it is left out and
recorded here instead.

## Known limitations

* 2000-2004 are unavailable at source — no pre-draft revision exists.
* 2009's entrant names, and 2020-2023's green-room lists, were added to the articles
  only after the respective drafts, so they are correctly missing here.
* `dp_auto_eligible=0` means "not listed among the unusual automatic-eligibility
  cases", not "not automatically eligible". The pages never list the ordinary
  (four-year college) automatic entrants.
* `dp_green_room_days_before_draft` is a *wave* date, not a per-player date; 2011-2015
  give no in-prose date at all, so it is empty there even though the invitee list is
  present.
* `dp_wiki_projected` is editor opinion (a "most reputable mock drafts" consensus
  written on the article), not a league or media source; it exists for 2 years only and
  should be modelled separately from the NBA-sourced columns, if at all.
* The article is a wiki: a revision minutes before the draft can contain an editor's
  speculative pre-fill (this is exactly the 2017 case the assertion caught). The
  assertion covers the results table; other prose is pre-draft by timestamp but is
  still editor-written.
* The identity file contains 2,560 players including a 2026 class and some undrafted
  players who reached the NBA, so per-year rosters run from 61 to 233 and "matched"
  counts in `counts_by_year.csv` are against that roster, not against 60 picks.
