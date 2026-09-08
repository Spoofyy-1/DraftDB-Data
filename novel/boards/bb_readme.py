"""Stage 4: generate README.md (prose + tables computed from the actual run)."""
import csv
import gzip
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bb_common import BASE, RAW, norm_name  # noqa: E402

IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
BANDS = [("2001-07", 2001, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025)]
SRC_LABEL = {"nd_board": "NBADraft.net big board",
             "nd_mock": "NBADraft.net editorial mock",
             "nd_crowd": "NBADraft.net crowd consensus",
             "dx_board": "DraftExpress Top-100",
             "dx_mock": "DraftExpress mock draft",
             "dx_mockx": "DraftExpress extended mock",
             "stepien": "The Stepien"}

FEATURE_DOC = [
    ("bb_nd_board_rank_final", "NBADraft.net big-board rank on the final accepted pre-draft board of the player's draft class (1-100; 101 = drafted player absent from that board, see bb_nd_unranked_board)."),
    ("bb_nd_board_rank_30d", "Same board, nearest capture at or before 30 days before draft night (101 = absent; empty when no capture falls in the [30, 150]-day window)."),
    ("bb_nd_board_rank_60d", "Same, at or before 60 days before draft night (window [60, 180] days)."),
    ("bb_nd_board_change_60d", "Sum of the board's own Change column (+n = moved up n places since the previous board update) over the distinct board states published in the last 60 pre-draft days. Net board momentum."),
    ("bb_nd_board_first_seen_days", "Days before draft night that the player first appears on ANY accepted big board of his class."),
    ("bb_nd_mock_rank_final", "Pick number in the last NBADraft.net editorial mock draft of the class."),
    ("bb_nd_crowd_mock_rank_final", "Pick number on the last capture of the NBADraft.net user-submitted consensus mock (/nba_mock_drafts/consensus)."),
    ("bb_nd_fit_gap", "bb_nd_mock_rank_final - bb_nd_board_rank_final. Positive = the same publisher's mock has him going LATER than his talent rank (team fit / need discount); negative = drafted-up relative to talent."),
    ("bb_nd_unranked_board", "1 when the player was drafted in a class whose final big board exists but does not list him, 0 when he is listed. Companion flag for the 101 rank encoding."),
    ("bb_dx_board_rank_final", "DraftExpress Top-100 Prospects rank on the last accepted pre-draft board of the class (empty when absent -- no 101 encoding on this source)."),
    ("bb_dx_board_rank_30d", "DraftExpress Top-100 rank, nearest board at or before 30 days before the draft."),
    ("bb_dx_mock_pick_final", "Pick number in the last DraftExpress mock draft of the class."),
    ("bb_dx_fit_gap", "bb_dx_mock_pick_final - bb_dx_board_rank_final (same sign convention as bb_nd_fit_gap)."),
    ("bb_dx_mock_volatility", "Sample standard deviation of the player's pick across all distinct DraftExpress mock states of that class (>=2 appearances required)."),
    ("bb_dx_board_momentum_30d", "bb_dx_board_rank_30d - bb_dx_board_rank_final. Positive = climbed the board over the last month."),
    ("bb_dx_first_mock_lead_days", "Days before draft night of the earliest DraftExpress mock capture of the class that lists the player."),
    ("bb_dx_age_listed", "Decimal age printed next to the player on his final DraftExpress board entry."),
    ("bb_stepien_consensus_rank", "Rank on The Stepien's composite/consensus board for the class (last pre-draft capture)."),
    ("bb_stepien_dispersion", "Sample standard deviation of the player's rank across the individual Stepien analysts on the same grid (>=2 analysts)."),
    ("bb_stepien_tier", "Numeric tier from the tier header above the player on the composite board (Tier 1 -> 1)."),
    ("bb_stepien_preseason_to_final_delta", "Preseason composite rank minus final composite rank (positive = rose across the season). Needs a capture >=150 days before the draft."),
    ("bb_fit_gap_mean", "Mean of the available publisher fit gaps (bb_nd_fit_gap, bb_dx_fit_gap)."),
    ("bb_n_board_sources", "Number of publishers (NBADraft.net, DraftExpress, The Stepien) whose final board actually lists the player."),
]


def main():
    plan = list(csv.DictReader(open(os.path.join(RAW, "fetch_plan.csv"))))
    parsed = []
    with gzip.open(os.path.join(RAW, "parsed.jsonl.gz"), "rt") as f:
        for line in f:
            parsed.append(json.loads(line))
    ident = list(csv.DictReader(open(IDENT)))
    feats = list(csv.DictReader(open(os.path.join(BASE, "features.csv"))))
    cols = [c for c in feats[0].keys() if c != "pid"] if feats else []

    used = Counter()
    up = os.path.join(RAW, "capture_usage.csv")
    if os.path.exists(up):
        for r in csv.DictReader(open(up)):
            used[(r["source"], int(r["class_year"]))] += 1
    else:
        for r in parsed:
            used[(r["source"], r["year_cal"])] += 1
    planned = Counter((r["source"], int(r["year"])) for r in plan)

    fby = {r["pid"]: r for r in feats}
    idby = {r["pid"]: r for r in ident}

    lines = []
    A = lines.append
    A("# boards -- big board vs mock draft (NBADraft.net, DraftExpress, The Stepien)")
    A("")
    A("Talent-versus-fit features built from Wayback Machine captures of public "
      "big boards and mock drafts. The board side is the new information: the "
      "model already carries a dated multi-publisher MOCK consensus, so nothing "
      "here rebuilds mock consensus -- what is new is each publisher's *board* "
      "(pure talent ranking) and the **board-minus-mock gap within the same "
      "publisher**, plus board momentum and analyst dispersion.")
    A("")
    A("Everything is derived from `web.archive.org` only. The live sites are "
      "never contacted (nbadraft.net is Cloudflare-gated; draftexpress.com no "
      "longer serves these pages). Requests are serialised at >= 1.05 s apart "
      "with a keep-alive session, exponential backoff on 429/503, at most one "
      "CDX listing in flight, and a descriptive User-Agent identifying the "
      "project and a contact address. All captures are cached under `raw/`, so "
      "re-runs are offline.")
    A("")
    A("## Files")
    A("")
    A("| file | contents |")
    A("|---|---|")
    A("| `features.csv` | pid + numeric `bb_*` columns, one row per player |")
    A("| `provenance.csv` | pid, source, capture timestamp and URL behind each *final* value |")
    A("| `unmatched.csv` | listed names that could not be tied to a pid, with the reason |")
    A("| `raw/index.csv` | every snapshot the discovery pass found (source, url, timestamp) |")
    A("| `raw/fetch_plan.csv` | the captures actually selected for download |")
    A("| `raw/<source>/<ts>_<hash>.html.gz` | raw mementos (`id_` flag, unrewritten) |")
    A("| `raw/parsed.jsonl.gz` | one JSON record per parsed capture (rank, name, pos, school, class, age, ht, wt, change) |")
    A("| `raw/year_reassignments.csv` | captures the content check moved to another class (`<year>`), dropped as belonging to no adjacent class (`DROPPED`, mostly stale pages), or refused as a results table (`RESULTS_LEAK`) |")
    A("| `raw/capture_usage.csv` | every capture that survived all checks, with its final class year, entry count and days-before-draft |")
    A("| `run.log` | crawl log |")
    A("")
    A("## URL patterns collected")
    A("")
    A("**NBADraft.net big board** (`nd_board`)")
    A("```")
    A("https://www.nbadraft.net/ranking/bigboard/          (single rolling URL, 2008-2025)")
    A("```")
    A("100 entries; columns Rank, Change, Player, Height, Weight, Pos, School/Team, Class.")
    A("")
    A("**NBADraft.net editorial mocks** (`nd_mock`) and crowd consensus (`nd_crowd`)")
    A("```")
    A("/mocks/{YYYY}_nba_mock_draft.html      2001-2009")
    A("/mock{YYYY}.htm                        2001-2002")
    A("/{YYYY}mock_draft                      2010-2016")
    A("/{YYYY}-nba-mock-draft-{v}/            2017-2025  (v = revision number)")
    A("/extended-nba-mock-draft-{N}-0/        two-round editions")
    A("/nba_mock_drafts/consensus             crowd aggregate, 2009-2018 (underscore path)")
    A("/nba-mock-drafts/consensus/            crowd aggregate, 2019-2025 (hyphen path)")
    A("```")
    A("Discovery was a single CDX domain listing "
      "(`url=nbadraft.net&matchType=domain&filter=original:.*[Mm]ock.*`), which "
      "returns every mock URL the site has ever used, rather than guessing "
      "per-year URLs.")
    A("")
    A("**DraftExpress** (`dx_board`, `dx_mock`, `dx_mockx`)")
    A("```")
    A("/rankings/Top-100-Prospects/           one page of 100   (2008-2014)")
    A("/rankings/Top-100-Prospects/{2,3,4}/   25 per page       (2015-2017)")
    A("/rankings/Top-100-Prospects/printable  (2017)")
    A("/nba-mock-draft/{YYYY}/                2007-2017")
    A("/nba-mock-draft-extended/{YYYY}        two rounds")
    A("```")
    A("")
    A("**The Stepien** (`stepien`)")
    A("```")
    A("/{YYYY}-draft-rankings/                composite board (tier headers)")
    A("/{YYYY}-individual-rankings/           analyst grid (one column per analyst)")
    A("/YYYY/MM/DD/<analyst>s-...-big-board/  dated single-analyst posts")
    A("```")
    A("")
    A("## Capture acceptance rule (dating)")
    A("")
    A("Draft-night cutoffs are the project list (22:00 UTC on draft day). A "
      "capture is used for draft class Y only if it satisfies one of:")
    A("")
    A("1. **Pre-draft.** Capture timestamp < cutoff(Y), and the calendar rule "
      "below assigns it to class Y.")
    A("2. **Frozen final board.** Timestamp is after cutoff(Y) but before "
      "15 Aug of Y. NBADraft.net and DraftExpress freeze the board after the "
      "draft and only reset to the next class in late August, so such a capture "
      "still shows the *final pre-draft* board. It is accepted only if the "
      "content check below agrees the top entries are class-Y players.")
    A("3. **DraftExpress on-page stamp.** From ~2012 the Top-100 page prints "
      "\"This Ranking was last updated on <date>\". A capture is accepted when "
      "either the capture timestamp or the parsed last-updated date is before "
      "the draft; the last-updated stamp is also the key used to stitch the "
      "paginated 25-per-page era back into one 100-man board.")
    A("4. **Mocks with the year in the URL** are accepted up to 40 days after "
      "the draft (the page is frozen and self-labelled), because the URL, not "
      "the timestamp, identifies the class.")
    A("")
    A("**Calendar rule.** For a rolling board URL, a capture at time t belongs "
      "to class Y where Y = t.year if t < cutoff(t.year); the window "
      "(cutoff(Y), 15 Aug of Y] is the frozen class-Y board; and t after "
      "15 Aug of Y belongs to class Y+1. This handles the shifted 2020 "
      "(18 Nov) and 2021 (29 Jul) drafts automatically.")
    A("")
    A("5. **Stepien dated posts are dated by publication, not capture.** A post "
      "at `/2018/06/19/...` was knowable on 19 June 2018 even if the archive "
      "only captured it in July, so the publication date in the path drives "
      "both the class year and the days-before-draft.")
    A("")
    A("**Content check.** For every board capture, the fraction of its top 30 "
      "names that are drafted players of class Y-1 / Y / Y+1 is computed "
      "against the identity file. The calendar year is kept unless another year "
      "beats it by >= 0.10 in that fraction, in which case the board is "
      "reassigned and logged to `raw/year_reassignments.csv`. This both "
      "verifies the frozen-board case and catches sites that reset early or "
      "late.")
    A("")
    A("This check is what keeps *stale* pages out. nbadraft.net leaves old "
      "\"extended mock draft\" URLs (`/extended-nba-mock-draft-81`, "
      "`/nba-mock-draft-73`) live and heavily crawled for years, still frozen "
      "on the 2013 class; DraftExpress likewise served a 2017 board long after "
      "it stopped updating. Such a capture agrees with no adjacent class and is "
      "dropped rather than mistaken for a later board. The planner also prefers "
      "capture URLs that name the class (`/2016mock_draft`, "
      "`/2019-nba-mock-draft-3/`) over undated ones so the request budget is "
      "not spent on those pages in the first place.")
    A("")
    A("**Results-leakage guard.** A post-draft mock capture is additionally "
      "refused when too many of its picks land exactly on the real draft slot. "
      "Across 464 strictly pre-draft mock captures the exact-agreement rate "
      "never exceeded 0.27 (median 0.09); nbadraft.net's "
      "`/mocks/2008_nba_draft.html`, a results table sitting on a mock-shaped "
      "path, scores 1.00. The cutoff is 0.35, which clears every genuine mock "
      "observed and refuses the results pages; refusals are logged as "
      "`RESULTS_LEAK` in `raw/year_reassignments.csv`.")
    A("")
    A("**State de-duplication.** The archive often captures the same published "
      "board many times. Captures are collapsed to distinct *board states* "
      "(signature = the full list of (rank, normalised name) pairs), keeping "
      "the earliest capture of each state. Momentum sums and mock-volatility "
      "standard deviations therefore count each published update once, not "
      "once per crawl. The signature must be the whole board: hashing only the "
      "top 25 collapses a complete 100-man board into an earlier state that "
      "happens to share its top 25, which once left a single 25-entry page "
      "standing as the \"final\" 2016 DraftExpress board. For the same reason "
      "the final board is chosen from states with at least 50 entries whenever "
      "any exist.")
    A("")
    A("**Horizon readings.** `*_30d` / `*_60d` take the latest state at or "
      "before that horizon, but never one more than 120 days older than the "
      "horizon, so a preseason board can never stand in for a one-month-out "
      "reading.")
    A("")
    A("## Parsing notes by layout era")
    A("")
    A("Rule-based extraction only (regular expressions and a fixed NBA-franchise "
      "dictionary). No scouting prose is stored anywhere -- only rank, name, "
      "position, school/team, class, listed age, height, weight and the board's "
      "own movement arrow.")
    A("")
    A("| source / era | markup | extraction |")
    A("|---|---|---|")
    A("| nd_board 2008-2018 | `<table class=\"nba_ranking bigboard\">` | 8 `<td>` per row: rank, change (arrow gif + `+n`/`-n`), player link, ht, wt, pos, school, class |")
    A("| nd_board 2019-2025 | `<table class=\"big-board-table\">` | same column order; the player cell wraps first/last name in separate `<span>`s |")
    A("| nd_mock 2001-2008 | two-column `<table>` | one `<tr>` holds BOTH pick N and pick N+30; a cell is a player when its text is `Name 6-10 240 POS School Class`; team cells are rejected with a franchise dictionary |")
    A("| nd_mock 2009-2025 | one pick per `<tr>` | rank cell + a `/players/<slug>` link |")
    A("| nd_crowd all | same `<tr>` shape as the mock | pick + player |")
    A("| dx 2008-2009 | `<table class=lotto>`, **unquoted** attributes | `/profile/Name-<id>/` link preceded by a `<td>rank</td>`; meta line `19 years old, 6' 10\" 239lbs.` |")
    A("| dx 2010-2014 | `<table class=\"bluecells\">`, 4 sub-tables of 25 | same, plus `<font size=1>age, class<br>ht wt<br><a /clubhouse/>school</a>` |")
    A("| dx 2015-2017 | `<div class=\"ranking-item\">` + `<div class=\"numero\">` | rank in `<font size=\"5\">N.</font>`; `18.7 years old  |  6'9\"  |  196 lbs` |")
    A("| dx mock all years | `<font size=\"5\">N.</font>` + team logo + profile link | pick number, player, school, class, decimal age |")
    A("| stepien composite 2020 | `<div class=\"rank-card\"><h3>Name</h3>` (no number) | the 2020 board dropped explicit numbering (\"order within tiers is fluid\"); rank is the card's ordinal position, which is the order the site presents |")
    A("| stepien composite | `<div class=\"rank-card\"><h3>N. Name</h3>` with `<div class=\"rank-tier\"><span>Tier N</span>` | rank, name, school, tier |")
    A("| stepien analyst grid | `<table class=\"tablepress rankings-table\">` | header row = analyst names; each cell is `Tier.OverallRank` (e.g. `3.06`) or `NR` |")
    A("| stepien dated posts | WordPress `entry-content` | `N. Player Name` at the start of a heading/paragraph/list item, with `Tier N` headers |")
    A("")
    A("A DraftExpress rank token is bound to the *nearest preceding* rank marker "
      "before each `/profile/` link, and only the first occurrence of each rank "
      "is kept, so sidebar and 'related' links cannot inject phantom entries.")
    A("")
    A("## Name matching")
    A("")
    A("Names are normalised (NFKD accent strip, lower-case, punctuation and "
      "`Jr/Sr/II/III/IV/V` suffixes removed, parenthetical text dropped) and "
      "matched **only within the same draft class** as the identity file "
      "records for that pid. Three rules are tried in order and each must be "
      "unique inside the class:")
    A("")
    A("1. exact normalised full name;")
    A("2. first initial + last name (handles `C.J.` / `CJ`, `Nikola` / `Niko`);")
    A("3. last name alone, when the class contains exactly one such surname and "
      "the first initials agree.")
    A("")
    A("Anything ambiguous or unresolved is written to `unmatched.csv` with the "
      "reason (`ambiguous_exact`, `ambiguous_initial`, `ambiguous_last`, "
      "`no_candidate`) and never guessed. Most `no_candidate` rows are board "
      "entries for players who were never drafted or never reached the NBA and "
      "so are absent from the identity file by construction.")
    A("")

    # ---------------- capture counts ----------------
    A("## Captures used, by source and draft class")
    A("")
    srcs = ["nd_board", "nd_mock", "nd_crowd", "dx_board", "dx_mock", "dx_mockx", "stepien"]
    A("`used / planned` per class. **planned** counts captures the planner "
      "assigned to that class from the URL or the calendar rule and selected "
      "for download; **used** counts captures that parsed into at least one "
      "ranked entry AND survived the dating, content and leakage checks, "
      "counted under their *final content-verified* class. The two are indexed "
      "differently, so `used` can exceed `planned` in a row that absorbed "
      "captures the content check moved in from the neighbouring class (and "
      "the neighbour's row is correspondingly short). Compare the totals, not "
      "the individual ratios.")
    A("")
    A("| class | " + " | ".join(srcs) + " |")
    A("|---" * (len(srcs) + 1) + "|")
    for y in range(2001, 2026):
        cells = []
        for s in srcs:
            p, u = planned.get((s, y), 0), used.get((s, y), 0)
            cells.append("-" if not p and not u else "%d/%d" % (u, p))
        A("| %d | %s |" % (y, " | ".join(cells)))
    A("| **total** | " + " | ".join(
        "%d/%d" % (sum(v for (s2, _), v in used.items() if s2 == s),
                   sum(v for (s2, _), v in planned.items() if s2 == s)) for s in srcs) + " |")
    A("")
    A("Class years in the table are the *content-verified* class of each "
      "capture, so they can differ slightly from the plan's calendar guess.")
    A("")

    # ---------------- coverage ----------------
    A("## Coverage by draft-year band")
    A("")
    A("Denominator = identity-file players with a recorded draft pick in that band.")
    A("")
    key_feats = ["bb_nd_board_rank_final", "bb_nd_mock_rank_final",
                 "bb_nd_crowd_mock_rank_final", "bb_nd_fit_gap",
                 "bb_dx_board_rank_final", "bb_dx_mock_pick_final", "bb_dx_fit_gap",
                 "bb_dx_mock_volatility", "bb_stepien_consensus_rank",
                 "bb_stepien_dispersion", "bb_fit_gap_mean"]
    A("| feature | " + " | ".join(b[0] for b in BANDS) + " | all |")
    A("|---" * (len(BANDS) + 2) + "|")
    denom = {}
    for label, lo, hi in BANDS:
        denom[label] = sum(1 for r in ident if r["actual_pick"]
                           and lo <= int(r["draft_year"]) <= hi)
    denom["all"] = sum(denom[b[0]] for b in BANDS)
    for c in key_feats:
        cells = []
        tot = 0
        for label, lo, hi in BANDS:
            n = 0
            for pid, fr in fby.items():
                ir = idby.get(pid)
                if not ir or not ir["actual_pick"]:
                    continue
                if not (lo <= int(ir["draft_year"]) <= hi):
                    continue
                if fr.get(c, "") != "":
                    n += 1
            tot += n
            cells.append("%d (%.0f%%)" % (n, 100.0 * n / max(1, denom[label])))
        cells.append("%d (%.0f%%)" % (tot, 100.0 * tot / max(1, denom["all"])))
        A("| `%s` | %s |" % (c, " | ".join(cells)))
    A("")
    A("| band | drafted players in identity file | rows in features.csv |")
    A("|---|---|---|")
    for label, lo, hi in BANDS:
        rows = sum(1 for pid in fby if idby.get(pid) and idby[pid]["actual_pick"]
                   and lo <= int(idby[pid]["draft_year"]) <= hi)
        A("| %s | %d | %d (%.0f%%) |" % (label, denom[label], rows,
                                         100.0 * rows / max(1, denom[label])))
    A("")

    # ---------------- feature dictionary ----------------
    A("## Feature definitions")
    A("")
    A("All columns are numeric; empty means unknown (never 0).")
    A("")
    A("| column | non-empty rows | definition |")
    A("|---|---|---|")
    nn = {c: sum(1 for r in feats if r.get(c, "") != "") for c in cols}
    for c, doc in FEATURE_DOC:
        if c in nn:
            A("| `%s` | %d | %s |" % (c, nn[c], doc))
    A("")
    A("### Sign conventions")
    A("")
    A("* When the board rank is the 101 sentinel the fit gap inherits it and "
      "can reach roughly -90 (a player the mock has in the lottery but the "
      "board never listed). That is a real signal, not a parse error, but it "
      "is a censored measurement: gate or clip it with "
      "`bb_nd_unranked_board` rather than treating -86 as 86 places of "
      "disagreement.")
    A("* **fit gap** = mock pick - board rank. A player the publisher ranks 5th "
      "on talent but mocks at pick 14 has a fit gap of +9: the market is "
      "discounting him relative to the same publisher's own talent board. "
      "Negative = the market is reaching for him.")
    A("* **momentum / change** are positive when the player *rises* (rank number "
      "falls).")
    A("* **lead / first-seen days** are positive counts of days before draft "
      "night; larger = discovered earlier.")
    A("")
    A("## Known limitations")
    A("")
    A("* **No board coverage before the 2009 class.** The NBADraft.net big board "
      "first appears in the archive in December 2008 and the DraftExpress "
      "Top-100 in October 2008, so `bb_*_board_*` and both fit gaps are empty "
      "for the 2001-2008 bands. The 2001-2008 rows carry mock-side columns only "
      "(`bb_nd_mock_rank_final`, and `bb_nd_crowd_mock_rank_final` from 2009).")
    A("* **DraftExpress stops after the 2017 draft** (the site was folded into "
      "ESPN); later `dx_*` values come only from residual captures and are "
      "sparse or absent.")
    A("* **The Stepien** only published these boards for the 2018-2020 and 2022 "
      "classes; no 2021 rankings page exists in the archive, so "
      "`bb_stepien_*` is empty for 2021 and for everything before 2018.")
    A("* **Mock freshness is limited by the archive, not by choice, in a few "
      "classes.** A post-draft mock capture is allowed only when its URL names "
      "the class and it clears the results-leakage guard, so where the archive "
      "simply has no late crawl the final mock is older: the closest "
      "DraftExpress mock capture is 170 days out for 2009, and the closest "
      "NBADraft.net editorial mock is 137 days out for 2003 and 30 for 2019. "
      "Every other class lands within ~30 days of draft night and most within "
      "two days. The 2008 NBADraft.net mock is thin because its two draft-week "
      "captures are the results table, refused by the guard.")
    A("* **Time-series features never use a post-draft capture.** The frozen "
      "window feeds only the *final* value; `bb_dx_mock_volatility`, "
      "`bb_dx_first_mock_lead_days`, `bb_nd_board_first_seen_days` and "
      "`bb_nd_board_change_60d` are computed from strictly pre-draft captures, "
      "so every lead/first-seen value is positive by construction.")
    A("* **Change-column sums under-count** when the archive missed an "
      "intermediate board update: the site reports movement since the previous "
      "update, and only captured updates can be summed.")
    A("* **Second-round and undrafted players** are frequently absent from a "
      "100-man board; that is encoded as 101 with `bb_nd_unranked_board=1` for "
      "drafted players, and left empty for identity rows with no draft pick "
      "(whose `draft_year` is an NBA-entry year, not necessarily a draft class).")
    A("* **Volatility is conditional on being mocked.** "
      "`bb_dx_mock_volatility` is the spread over the captures where the player "
      "appears; a player who enters the mock late has a low-n, low-variance "
      "reading rather than a missing one.")
    A("* Mock volatility for DraftExpress is computed over at most 40 captures "
      "per class (evenly spaced through the pre-draft window plus the last one) "
      "to keep the crawl inside a polite request budget.")
    A("")
    A("## Terms of service / etiquette")
    A("")
    A("* Only `web.archive.org` is contacted; the origin sites are never "
      "fetched, so no Cloudflare challenge, paywall or login is bypassed.")
    A("* >= 1.05 s between requests from this collector, keep-alive session, "
      "exponential backoff on 429/503, at most one CDX listing in flight, and a "
      "User-Agent naming the project and a contact address.")
    A("* Captures that the archive cannot serve (5xx after three tries) are "
      "recorded as `.miss` markers so re-runs never re-request them.")
    A("* Only factual ranking fields are stored. No scouting reports, no article "
      "text, no images.")
    A("")
    A("## Reproducing / resuming")
    A("")
    A("```bash")
    A("cd /Users/kennakao/nba/datarebuild/novel/boards")
    A("python3 bb_index.py            # snapshot discovery  -> raw/index.csv")
    A("python3 bb_index_stepien.py    # Stepien supplement")
    A("python3 bb_fetch.py --replan   # select + download    -> raw/<source>/")
    A("python3 bb_features.py --parse # parse + build        -> features.csv")
    A("python3 bb_readme.py           # regenerate this file")
    A("```")
    A("")
    A("Both crawl stages are checkpointed (`raw/index_done.txt`, "
      "`raw/fetch_done.txt`) and every capture is cached, so re-running any "
      "stage resumes where it stopped and costs no extra requests for work "
      "already done. `bb_features.py` and `bb_readme.py` are fully offline. "
      "To resume an interrupted crawl:")
    A("")
    A("```bash")
    A("cd /Users/kennakao/nba/datarebuild/novel/boards")
    A("nohup python3 -u bb_fetch.py >> run.log 2>&1 &")
    A("until grep -q 'fetch complete' run.log; do sleep 30; done")
    A("python3 bb_features.py --parse && python3 bb_readme.py")
    A("```")
    A("")

    with open(os.path.join(BASE, "README.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("README.md written (%d lines)" % len(lines))


if __name__ == "__main__":
    main()
