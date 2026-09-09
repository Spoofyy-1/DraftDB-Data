# `asap` — dated language features from the ASAP Sports pre-draft interview archive

Rule-based (regex + hand-built word lists) LIWC-style language features for
drafted players, computed **only** from transcripts dated before each player's
draft night.  No LLM scoring, no proprietary dictionaries.

Motivation: MIT Sloan 2025, *"Beyond the Box Score: Using Psychological Metrics
to Forecast NBA Success"*
(https://www.sloansportsconference.com/research-papers/beyond-the-box-score-using-psychological-metrics-to-forecast-nba-success)
reports that LIWC word-category rates over ASAP Sports transcripts add roughly
five points of balanced accuracy on top of NCAA box-score models, with the
strongest signal in function words and tense: future focus (low is better),
conjunctions (high is worse), present focus, verbs, positive emotion and an
"authenticity" style score.  LIWC itself is licensed, so every dictionary here
is built from scratch and printed in full below.

---

## 1. Archive structure (as crawled)

`http://www.asapsports.com/` has no `robots.txt` (HTTP 404 on
`/robots.txt`, checked at crawl time) — i.e. no crawl restrictions are
published.  The archive is a set of PHP index pages:

| page | contents |
|---|---|
| `showcat.php?id=<sport>` | sport landing page. Basketball is **`id=11`** (men's college, women's college, NBA and WNBA all share this category) |
| `show_year.php?category=11&year=YYYY` | every basketball event in a calendar year, 1992 - present |
| `show_event.php` / `show_events.php?event_id=…` | the transcripts belonging to one event |
| `show_player.php?category=11&letter=<a-z>` | **A-Z index of every person who has ever spoken in a basketball transcript** (players, coaches, administrators), each linking to a numeric person id |
| `show_player.php?id=<asap_id>` | one person's page: a reverse-chronological list of `[ Month DD, YYYY ]` + event title + link to each transcript in which that person is a listed speaker |
| `show_interview.php?id=<interview_id>` | one transcript |

A transcript page is structured as
`<h1>` event title, `<h2>` date (`Month DD, YYYY`), one `<h3><a
href="show_player.php?id=…">Speaker Name</a></h3>` per listed speaker, then the
body.  Two body formats exist and both are handled:

* **pre-≈2015**: `SPEAKER NAME: text<br/><br/>` blocks, questions as
  `<b>Q. </b><b>…</b>`, terminated by `End of FastScripts...`
* **post-≈2015**: the same blocks wrapped in `<p>…</p>`, terminated by
  `FastScripts Transcript by ASAP Sports`

Basketball events that carry pre-draft player speech include the NCAA men's
tournament (all rounds, regionals, Final Four), conference tournaments, holiday
tournaments and season/awards media conferences.  NBA draft-combine transcripts
exist for a few years and are kept (see §3); everything else NBA/WNBA-tagged is
dropped.

**Crawl politeness.** Single-threaded, one request at a time, `>= 1.2 s`
between requests (`asaplib.MIN_INTERVAL`), exponential backoff on
429/500/502/503/504, descriptive User-Agent:
`DraftDB-Research/1.0 (academic NBA draft research, non-commercial; contact
mike@alphax.inc) Python-urllib`.  No logins, no JS challenges, no paywalls.
Only three page types are fetched: 26 letter-index pages, one page per
candidate person, one page per eligible transcript.

## 2. Matching rule (identity -> ASAP person id)

1. Normalise both sides with `asaplib.norm_name`: NFKD accent strip, lowercase,
   drop everything outside `[a-z ]` (so `.`, `'`, `-` and digits vanish), drop
   the suffix tokens `jr sr ii iii iv v`, collapse whitespace.  ASAP lists names
   as `Last, First`, so they are flipped first (`Achiuwa, Precious` ->
   `Precious Achiuwa` -> `precious achiuwa`).
2. A drafted player is linked to **every** ASAP person id whose normalised name
   is identical.  Suffixes are stripped because ASAP itself is inconsistent
   about them (the same person appears as both `Acuff, Darius` and
   `Acuff Jr., Darius`).
3. Date plausibility is then required (§3): a transcript only counts if it falls
   inside the player's pre-draft window.
4. **Ambiguity is never guessed.**  A pid is dropped entirely (all features left
   empty, including `li_has_transcript`) and written to `unmatched.csv` when
   either
   * `multiple_asap_persons_same_name` — two or more *distinct ASAP person ids*
     with that normalised name have in-window transcripts, so the text cannot be
     attributed to one person; or
   * `multiple_drafted_players_same_name` — two or more *drafted players in the
     identity file* share the normalised name and the same transcript falls in
     both of their windows (e.g. Marcus Williams 2006 / Marcus Williams 2007).

   No birthdate check is possible here: ASAP publishes no biographical data.

## 3. Dating and the pre-draft filter

Every transcript carries an explicit calendar date in its `<h2>`, and the
archive index repeats a date on the person page; nothing is dated by season
label.  The two disagree for ~0.8% of records (the index occasionally carries a
wrong year), so a transcript is kept only when **both** dates pass every test
below — leakage is then impossible whichever one is right.  The transcript
page's own `<h2>` date is what lands in `provenance.csv` and drives
`li_days_to_draft_*`.  A transcript is used only if **all** of the following hold for both dates:

* `date < draft-night cutoff` for the player's draft year.  Cutoffs are the
  ones in `../COLLECTOR_RULES.md` (2000-2025); 2026 uses `2026-06-23`, taken
  from the archive's own `NBA DRAFT` event date.  The comparison is on the
  calendar date, so a transcript dated *on* draft day is excluded — draft-night
  interviews happen after the pick.
* `date >= July 1 of (draft_year - 6)`.  Six years covers redshirt/JUCO/COVID
  sixth-year careers and the high-school events of the 2000-2005 prep-to-pro
  players, while keeping the window narrow enough to be a real disambiguation
  test.
* the event title does not match `\b(WOMEN|WOMEN'S|WNBA|LADY)\b` (women's
  basketball shares category 11, so a same-named women's player would otherwise
  contaminate).
* the event title does not match X
  LEAGUE)\b` **unless** it also matches `COMBINE|PRE-?DRAFT`.  A prospect cannot
  legitimately appear in a pro-league transcript before he is drafted, so these
  titles are both out of scope and a useful same-name collision detector; the
  NBA draft combine is the one genuinely pre-draft NBA-run event.  Bare
  `ALL-STAR GAME` titles were checked and are all NBA All-Star (Team LeBron
  etc.); high-school all-star games appear as `ALL AMERICAN`, which is kept.

## 4. Extracting only the player's own words

`parse_iv.extract_for(html, asap_id)` runs a state machine over the body blocks:

* a block starting `Q.` / `Q ` / `QUESTION:` is a **question** -> discarded, and
  the current speaker is cleared;
* a block starting with an ALL-CAPS label followed by `:` sets the current
  speaker.  The label is resolved **against the `<h3>` speaker list of that
  transcript** — exact normalised match, else a bare surname or
  `initial + surname` that is unique among the listed speakers, else
  `COACH <surname>`.  `THE MODERATOR` and anything that resolves ambiguously or
  not at all becomes "no current speaker";
* a block with no label continues the current speaker (multi-paragraph answers);
* text is kept only while the current speaker is the target person id.

In a transcript whose only listed speaker is the target, an unlabelled block
that directly follows a question is also credited to him (some single-player
transcripts omit labels).  The body is cut at `End of FastScripts` /
`FastScripts Transcript by ASAP`, with a footer-marker fallback, so site
navigation text can never be scored as speech.

An "answer" (`li_n_answers`) is a *turn*: one label-block or one
question-then-answer, not one paragraph.

The archive sends ISO-8859-1 headers over (sometimes doubly) UTF-8 encoded
bytes.  `s5_features.demojibake()` repairs this offline by re-encoding the
byte-lossless latin-1 text and decoding it as UTF-8 (18.7% of records were
affected, all of them in non-breaking spaces; the repair changed **zero**
feature cells, verified by diff).

Before counting, `s5_features.clean()` removes parenthesised stage directions
(`(Laughter.)`, `(Applause)`, `(indiscernible)`) and square-bracket
transcriptionist insertions (`Coach [Penny] Hardaway`) — neither is the player's
own speech.  The gzipped cache keeps the un-cleaned attributed text so this
choice can be revisited without re-crawling.

## 5. Dictionaries

All lists live in `lexicon.py` and are reproduced there verbatim; they are
hand-built from ordinary English, not derived from LIWC.  Tokenisation:
lowercase, curly quotes normalised, tokens `[a-z]+('[a-z]+)*`.  A contraction is
one word but matches on three keys (`i'll` -> `i'll`, `i`, `'ll`; `don't` ->
`don't`, `do`, `n't`), and each category is counted at most once per token.
Multi-word phrases are matched separately with word boundaries and added to the
same category; no phrase contains a word that is already a token of the same
category, so nothing is counted twice.

| category | column | contents (see `lexicon.py` for the full list) |
|---|---|---|
| future focus | `li_r_future` | `will, 'll, won't, shall, gonna, tomorrow, future, next, upcoming, soon, later, eventually, someday, plan/plans/planning/planned, ahead, …` + phrases `going to, about to, fixing to, hoping to, looking forward, down the road` |
| present focus | `li_r_present` | present-tense copulas/auxiliaries (`am, 'm, is, 's, are, 're, do, does, have, has, can, …`), high-frequency present-tense verbs (`want, need, know, think, feel, try, play, go, get, make, see, say, come, take, like, love, work, stay, keep` + 3rd-person `-s` forms) and `now, today, currently` |
| past focus | `li_r_past` | irregular/auxiliary past forms (`was, were, had, did, went, got, said, thought, came, took, …`) **plus** the regex rule `^[a-z]{3,}ed$` minus a stoplist (`need, indeed, speed, instead, ahead, head, hundred, …`) |
| conjunctions | `li_r_conj` | `and, but, or, so, because, although, though, while, whereas, however, plus, therefore, thus, yet, since, unless, whether, nor, also, then, besides, moreover, furthermore, anyway, otherwise` |
| positive emotion | `li_r_posemo` | 80 words: `good, great, awesome, happy, excited, fun, enjoy, love, proud, blessed, thankful, confident, win, success, opportunity, appreciate, …` |
| negative emotion | `li_r_negemo` | 71 words: `bad, terrible, sad, angry, frustrated, disappointed, tough, struggle, hurt, injury, nervous, hate, lose, fail, mistake, doubt, …` |
| 1st person singular | `li_r_i` | `i, me, my, mine, myself, i'm, i've, i'll, i'd` |
| 1st person plural | `li_r_we` | `we, us, our, ours, ourselves, we're, we've, we'll, we'd, let's` |
| 2nd person | `li_r_you` | `you, your, yours, yourself, yourselves, you're, you've, you'll, y'all` |
| 3rd person | `li_r_they` | `he, him, his, she, her, they, them, their, himself, herself, themselves, he's, she's, they're` |
| negations | `li_r_negate` | `no, not, never, none, nobody, nothing, nowhere, neither, nor, cannot, without, n't` and the spelled-out `can't, don't, didn't, won't, …` |
| certainty | `li_r_certain` | `always, never, definitely, absolutely, certain(ly), sure(ly), totally, completely, obviously, clearly, undoubtedly, guarantee(d), must, all, every, everything, everyone, forever, truly, exactly, 100` |
| tentative | `li_r_tentat` | `maybe, perhaps, probably, possibly, might, could, guess, hopefully, somewhat, seem(s/ed), kinda, sorta, apparently, suppose, chance, depends, unsure` + phrases `kind of, sort of, or something, or whatever, a little bit` (the bare words `kind`/`sort` are deliberately not tokens) |
| articles | `li_r_article` | `a, an, the` |
| prepositions | `li_r_prep` | 49 common prepositions |
| auxiliary verbs | `li_r_auxverb` | `am/is/are/was/were/be/been/being/have/has/had/do/does/did/will/would/shall/should/can/could/may/might/must` + contraction suffixes |
| quantifiers | `li_r_quant` | `all, any, both, each, every, few, little, lot(s), many, more, most, much, several, some, enough, less, least, plenty, couple, bunch` |
| verbs | `li_r_verb` | auxiliaries + the present/past lists + basketball-frequent verbs, **plus** the regexes `^[a-z]{3,}ed$` and `^[a-z]{4,}ing$` minus stoplists (`thing, king, ring, spring, morning, during, something, …`) |
| function words | `li_r_function` | pronouns + articles + prepositions + auxiliaries + conjunctions + negations + quantifiers + `it, its, this, that, these, those, there, here, what, which, who, whom, whose, when, where, why, how` (212 entries) |
| exclusive words | `li_r_exclusive` | `but, without, exclude, except, unless, however, although, though, rather, than, whereas, besides, else, other(s), otherwise` |
| motion words | `li_r_motion` | `go(es/ing), went, gone, come(s/ing), came, move(d/s/ing), walk, run, ran, arrive, carry, drive, drove, bring, brought, take, took, travel, leave, left, enter` |
| filler / hedge | `li_r_filler` | `um, uh, er, hmm, well, basically, literally, honestly, actually, really, just, yeah, yep, okay, ok, man` + phrases `you know, i mean, kind of, sort of, at the end of the day` |
| social | `li_r_social` | `team(s), teammate(s), coach(es), guys, family, brother(s), mom, dad, parents, friends, people, fans, program, staff, together, everybody, …` |
| achievement | `li_r_achieve` | `work(ing/ed), hard(er/est), win(ning), best, better, improve, goal(s), compete, prepare, earn, achieve, succeed, success, effort, focus, determined, discipline, grind, push, challenge, practice` |

`li_authenticity` is **our own reproduction**, not LIWC's proprietary
`Authentic` score.  It is the fixed-weight, un-standardised combination of the
Newman/Pennebaker (2003) linguistic-deception cues, in rates per 1,000 words:

```
li_authenticity = li_r_i + li_r_exclusive - li_r_negemo - li_r_motion
```

No z-scoring or any other sample-dependent scaling is applied anywhere, so no
feature can leak information from other draft classes or from the future.

## 6. Feature list (`features.csv`, one row per pid, 2,560 rows)

All columns numeric, `li_` prefixed, empty = unknown (never 0 for unknown).

| column | meaning |
|---|---|
| `li_has_transcript` | 1 if at least one usable pre-draft transcript, 0 if the player was searched and none exists, **empty if the name match was ambiguous** |
| `li_n_transcripts` | number of pooled pre-draft transcripts in which he actually spoke (0 is a known zero) |
| `li_n_listed` | eligible pre-draft transcripts in which he was a **listed speaker**, whether or not he was asked anything (empty if he is in no transcript at all) |
| `li_silent_share` | `1 - li_n_transcripts / li_n_listed` — share of podium appearances where he never got a question. A player can sit on a Final Four dais and say nothing; that is a real, dated observation and is kept separate from the language rates |
| `li_n_answers` | total answer turns |
| `li_total_words` | total words he spoke pre-draft |
| `li_words_per_answer` | `li_total_words / li_n_answers` |
| `li_words_per_sentence` | words per `[.!?]`-delimited sentence |
| `li_long_word_pct` | % of words with >= 7 letters |
| `li_ttr500` | mean type/token ratio over non-overlapping 500-word chunks (length-controlled; empty under 500 words) |
| `li_qmark_rate` | question marks per 1,000 words of his own speech |
| `li_solo_share` | share of his transcripts where he was the only listed speaker (solo press conference) |
| `li_days_to_draft_last` / `_first` | days from his last / first pre-draft transcript to draft night |
| `li_span_days` | days between first and last pre-draft transcript |
| `li_authenticity` | see §5 |
| `li_i_we_ratio` | `li_r_i / (li_r_i + li_r_we)` |
| `li_r_<category>` | rate per 1,000 words for each of the 24 dictionaries in §5 |

## 7. Coverage

<!--COVERAGE-->
| draft years | players | has transcript | none | ambiguous | median words (of those with text) | median transcripts |
|---|---|---|---|---|---|---|
| 2000-07 | 582 | 126 (21.6%) | 454 | 2 | 643.0 | 2.0 |
| 2008-18 | 1017 | 632 (62.1%) | 361 | 24 | 1091.0 | 5.0 |
| 2019-26 | 961 | 583 (60.7%) | 351 | 27 | 763 | 3 |

Bands follow `../COLLECTOR_RULES.md` (2019-26 also holds the 61 players with `draft_year = 2026`).  "Ambiguous" players are listed in `unmatched.csv` and carry an EMPTY `li_has_transcript`.
<!--/COVERAGE-->

## 8. Known limitations — read before modelling

* **Selection bias is the headline caveat.**  Only players who reached a
  televised press conference have transcripts at all: NCAA-tournament teams,
  power-conference schools, and star underclassmen are heavily over-represented,
  while international players, JUCO players, mid-major role players and most
  second-round picks have none.  `li_has_transcript` is therefore *itself an
  informative feature* (a crude proxy for "played on a nationally covered team")
  and is exposed as its own column precisely so a model can absorb that
  selection channel rather than confound it with the language rates.  Rates
  should always be used together with `li_has_transcript`, `li_n_transcripts`
  and `li_total_words`.
* Coverage also rises over time with the archive's own growth, so
  `li_has_transcript` is not comparable across draft-year bands without a
  year control.
* **Short samples are noisy.**  A freshman who answered two questions
  contributes ~40 words; rates on that are almost pure noise.  Of the 1,341
  players with text, 95% have >= 100 words, 83% >= 250, 68% >= 500 and 46%
  >= 1,000 (median 872, 1.95M words in total).  `li_total_words` is provided so the model can shrink the rates
  toward the pooled mean.
* **Press-conference speech is not free speech**: it is media-trained,
  situational (the losing-locker-room transcripts are systematically more
  negative), and transcribed by a human who normalises some disfluencies.  Event
  mix differs between players.
* **Name matching has no birthdate check** — ASAP publishes no biography.  The
  guards are the pre-draft window, the women's/pro title filters, and the
  ambiguity rules in §2.  A residual risk remains that ASAP has merged two
  same-named people under one person id; that is undetectable from the site.
* The past-tense `-ed` and verb `-ing` regexes over-count adjectives
  (`excited`, `tired`) and gerund nouns; this is a known approximation and the
  stoplists only cover the frequent cases.
* Dictionaries are ours, so the absolute rates are **not** comparable to
  published LIWC numbers; only relative comparisons within this file are valid.

## 9. Files, reproduction and resume

```
asaplib.py    polite fetcher (UA, 1.2 s spacing, backoff) + name normalisation
lexicon.py    every word list, verbatim
parse_iv.py   transcript parser + speaker attribution state machine
s1_index.py   -> raw/players_index.csv.gz      (26 requests)
s2_match.py   -> candidates.csv                (offline)
s3_playerpages.py -> raw/person_transcripts.csv  (1 request per candidate person)
s4_answers.py -> raw/answers.jsonl.gz + raw/fetched_iv.txt + unmatched.csv
                 (1 request per eligible transcript; extracted answer text only)
s5_features.py -> features.csv + provenance.csv (offline, run any time)
```

Every stage is **resumable**: `s3` skips person ids already in
`raw/person_transcripts.csv`, `s4` skips interview ids already in
`raw/fetched_iv.txt`.  To resume an interrupted crawl:

```
cd /Users/kennakao/nba/datarebuild/novel/asap
nohup python3 s4_answers.py >> s4.log 2>&1 &     # continues where it stopped
python3 s5_features.py                           # rebuild features from cache
```

`s5_features.py` can be re-run at any point and will simply build features from
whatever is cached, so partial crawls give partial (but correct) coverage.
Only extracted answer text is cached, gzipped, under `raw/` (git-ignored); no
full transcript HTML is stored.
