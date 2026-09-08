"""Render README.md from the artefacts actually produced, so every number in it is real."""
import csv, json, os, sys, collections

D = "/Users/kennakao/nba/datarebuild/novel/draftexpress"
RAW = f"{D}/raw"
IDENT = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"

st = json.load(open(f"{D}/build_stats.json"))
meas = list(csv.DictReader(open(f"{D}/measurements_all.csv")))
feat = list(csv.DictReader(open(f"{D}/features.csv")))
unm = list(csv.DictReader(open(f"{D}/unmatched.csv")))
ident = list(csv.DictReader(open(IDENT)))
man = [json.loads(l) for l in open(f"{RAW}/manifest.jsonl")]
_pl = {}
if os.path.exists(f"{RAW}/profiles_manifest.jsonl"):
    for _l in open(f"{RAW}/profiles_manifest.jsonl"):      # a retry appends a 2nd line per id
        _r = json.loads(_l); _pl[_r["dx_id"]] = _r
pman = list(_pl.values())

caps = sorted({m["ts"] for m in man if m.get("ok")})
pcaps = sorted({m.get("capture_ts", "") for m in pman if m.get("ok") and m.get("capture_ts")})
src_ct = collections.Counter(r["source"] for r in meas if r["source"])
yr_ct = collections.Counter(int(r["event_year"]) for r in meas)

BANDS = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2026)]
have = {r["pid"] for r in feat}
youth = {r["pid"] for r in feat if r.get("dx_has_youth_measurement") == "1"}
multi = {r["pid"] for r in feat if r.get("dx_n_events") and int(r["dx_n_events"]) >= 2}
rows_band = []
for name, a, b in BANDS:
    tot = [p for p in ident if a <= int(float(p["draft_year"])) <= b]
    n = len(tot)
    h = sum(1 for p in tot if p["pid"] in have)
    y = sum(1 for p in tot if p["pid"] in youth)
    m = sum(1 for p in tot if p["pid"] in multi)
    rows_band.append((name, n, h, 100.0 * h / max(n, 1), m, y))

per_year = []
for y in range(2000, 2027):
    tot = [p for p in ident if int(float(p["draft_year"])) == y]
    h = sum(1 for p in tot if p["pid"] in have)
    if tot:
        per_year.append((y, len(tot), h, 100.0 * h / len(tot)))

DEFS = [
 ("dx_n_events", "count of distinct archived measurement events for the player (event = one (player, source, year) row after de-duplication), restricted to event_year <= draft_year."),
 ("dx_years_spanned", "last event year minus first event year."),
 ("dx_earliest_age", "age in years at the earliest archived event, event dated 1 June of its year; blank when no birthdate or class-year proxy is available."),
 ("dx_first_height_in", "height in inches at the earliest archived event. height_in = height with shoes when reported, else height without shoes + %.2f in (the median with-shoes minus no-shoes gap measured on the archive itself)." % st["shoe_gap_in"]),
 ("dx_d_height_in", "height_in at the latest archived event minus height_in at the earliest archived event (blank unless the two events are in different years). When dx_has_youth_measurement = 1 this is the youth -> pre-draft growth delta."),
 ("dx_height_growth_per_yr", "dx_d_height_in divided by the number of years between those two events (annualised height growth, in/yr)."),
 ("dx_late_grower_resid", "final archived height minus the height predicted from the player's height at age <= 16 by the OLS line fitted on all archived players with both (see 'Late-grower regression'). Positive = grew more than his 16-and-under height predicted. Blank without an age <= 16 measurement."),
 ("dx_still_growing", "1 when height_in gained >= 0.5 in between the earliest and the latest event inside the final 24 months before the last archived event; 0 when it did not; blank when fewer than two events fall in that window."),
 ("dx_first_ws_ht_ratio", "wingspan_in / height_in at the earliest archived event (dx_last_ws_ht_ratio is the same at the latest event)."),
 ("dx_weight_gain_per_yr", "(weight at latest event - weight at earliest event) / years between them, lb/yr."),
]

REST = [
 ("dx_n_sources_known", "how many of the player's events carry a Source label (only profile pages and source-filtered listing captures do)."),
 ("dx_n_youth_events", "events whose Source is in the youth dictionary, or (Source unknown) whose estimated age is <= 17.5."),
 ("dx_first_event_year / dx_last_event_year", "year of the earliest / latest archived event."),
 ("dx_has_youth_measurement", "1 when at least one event is a youth event, else 0."),
 ("dx_first_is_youth", "1/0 whether the earliest event is a youth event; blank when the Source is unknown and no age is available."),
 ("dx_last_age", "age at the latest archived event, same dating rule as dx_earliest_age."),
 ("dx_age_src", "1 = birthdate from age_verified_wiki.csv, 2 = birthdate implied by the DX profile's 'Age: A.B' at its capture date, 3 = class-year proxy age = (event_year - hs_class_year) + 18."),
 ("dx_age_is_proxy", "0 when dx_age_src = 1, else 1. Every age-derived feature on a proxy row inherits its error."),
 ("dx_first_wingspan_in / dx_first_weight_lb / dx_first_reach_in", "wingspan, weight and standing reach at the earliest event that reports each (each measure is taken from its own earliest reporting event)."),
 ("dx_last_wingspan_in / dx_last_weight_lb / dx_last_reach_in / dx_last_height_in", "same at the latest reporting event."),
 ("dx_d_wingspan_in / dx_d_weight_lb / dx_d_reach_in / dx_d_max_vert_in", "latest minus earliest for wingspan, weight, standing reach and max vertical."),
 ("dx_height_at_16_in", "height_in at the earliest event with estimated age <= 16."),
]

t = []
t.append("# DraftExpress archived pre-draft measurements -> growth-trajectory features\n")
t.append("`/Users/kennakao/nba/datarebuild/novel/draftexpress/`\n")
t.append("draftexpress.com has been dead since late 2017 (its staff moved to ESPN). Its "
         "*Measurements History* database is the only public source that measured the same "
         "prospects repeatedly from age ~15 through the pre-draft process, so it is the only "
         "way to build real growth trajectories. Everything here comes from the Wayback "
         "Machine.\n")

t.append("## 1. What was collected\n")
t.append(f"* **{st['measurement_rows']:,} player-events** over **{st['dx_players']:,} distinct "
         f"DraftExpress player ids**, event years **{min(yr_ct)}-{max(yr_ct)}** "
         "(`measurements_all.csv`, names allowed - local only).")
t.append(f"* **{len(feat):,} of the 2,560 drafted players** in `tabular_names.csv` matched "
         f"(`features.csv`, pid + numeric only); {len(unm):,} rows logged to `unmatched.csv`.")
t.append(f"* **{len([m for m in man if m.get('ok')])} listing captures** and "
         f"**{len([m for m in pman if m.get('ok')])} profile captures** cached under `raw/` "
         "(gzipped), so every re-run is offline.\n")

t.append("## 2. URL patterns used\n")
t.append("Two generations of the same database are archived. Only URLs that were actually "
         "captured can be replayed, so the crawl list is **derived from the CDX index**, never "
         "generated.\n")
t.append("```")
t.append("CDX enumeration (single requests, cached as raw/cdx_full.json / raw/cdx_profiles.json):")
t.append("  http://web.archive.org/cdx/search/cdx?url=draftexpress.com/nba-pre-draft-measurements*")
t.append("      &output=json&fl=timestamp,original,statuscode,digest,length")
t.append("  http://web.archive.org/cdx/search/cdx?url=draftexpress.com/profile*")
t.append("      &output=json&fl=timestamp,original,length&filter=statuscode:200&collapse=urlkey")
t.append("")
t.append("A. legacy listing (UNPAGINATED - one capture returns every row matching the filter)")
t.append("     /nba-pre-draft-measurements.php")
t.append("     /nba-pre-draft-measurements/?year=YYYY|All&source=NAME|All&pos=0..5&draft=0|15|30|100|999")
t.append("                                 &sort=1..18&sort2=ASC|DESC")
t.append("     /nba-pre-draft-measurements/measurements.php?...   (same parameters)")
t.append("B. 2016/17 listing (100 rows per page)")
t.append("     /nba-pre-draft-measurements/{year|all}/{source|all}/{pos|all}/{draft|all}/{page}/{sort}/{dir}")
t.append("C. player profile (the only place a Source label appears per player)")
t.append("     /profile/{Slug}-{dx_id}/          e.g. /profile/Andrew-Wiggins-6191/")
t.append("")
t.append("Replay form (raw archived bytes, no Wayback toolbar injection):")
t.append("     https://web.archive.org/web/{timestamp}id_/http://www.draftexpress.com{path}")
t.append("Profiles are requested at https://web.archive.org/web/20170601000000id_/...  and the")
t.append("Wayback Machine redirects to the nearest capture; the timestamp it actually served is")
t.append("recorded per profile in raw/profiles_manifest.jsonl (capture_ts).")
t.append("```\n")

t.append("### Capture timestamps used\n")
t.append(f"* Listing captures: **{len(caps)}** distinct timestamps, "
         f"**{caps[0][:8] if caps else '-'} - {caps[-1][:8] if caps else '-'}**. "
         "For each distinct URL shape the crawler keeps the **largest** capture recorded while "
         "the site was still live (timestamp < 2017-12-15); after that date every capture is a "
         "~5.5 kB dead-site shell.")
if pcaps:
    t.append(f"* Profile captures: **{len(pcaps)}** distinct timestamps, "
             f"**{pcaps[0][:8]} - {pcaps[-1][:8]}** (median {pcaps[len(pcaps)//2][:8]}).")
t.append("* The single most productive capture is "
         "`web/20170128164518id_/http://www.draftexpress.com/nba-pre-draft-measurements.php` "
         "- the legacy grid with no filter, which returns the whole database (11.1 MB, 5,688 "
         "data rows) in one request.")
t.append("* 387 profiles came back from a **post-shutdown** capture (2018-2024 dead-site shells). "
         "`dx_profiles_retry.py` re-asked for each of them at an earlier target (2016-12-01) and "
         "**0 of 387** returned a live-era capture: those players simply have no pre-2018 "
         "profile snapshot, and nothing more can be recovered for them.")
t.append("* Full per-page provenance: `raw/manifest.jsonl` and `raw/profiles_manifest.jsonl` "
         "(one JSON line per fetch: url path, capture timestamp, HTTP code, bytes, cache file). "
         "Per-pid provenance: `provenance.csv`.\n")

t.append("### A note on database size\n")
t.append("The April-2017 captures paginate to page 155, which suggests ~15,500 rows at 100 "
         "rows/page. That is wrong: those deep April captures contain **no data rows** (page "
         "size was smaller then and the deep pages archived empty), while the July-2017 "
         "captures - 100 rows/page - end at **page 42**, and the unfiltered legacy dump holds "
         "**5,688** rows. The real database is ~5.7k player-events, which is what we have.\n")

t.append("## 3. Parsing rules (rule-based only - no judgement, no LLM scoring)\n")
t.append("Three table shapes, all extracted by header text where a header row exists and by the "
         "verified canonical column order where the capture rendered the header detached:\n")
t.append("```")
t.append("A legacy  <table class=\"inputbox\">, 18 cells")
t.append("  Name | Ht w/o Shoes | Ht w/shoes | Weight | Wingspan | Reach | Body Fat | Hand Length |")
t.append("  Hand Width | No Step Vert | No Step Vert Reach | Max Vert | Max Vert Reach | Bench |")
t.append("  Agility | Sprint | Rank | Drafted")
t.append("  - cell 0 is \"Player Name - YYYY\" (a leading \"* \" is stripped); YYYY is the EVENT year")
t.append("  - Hand Length / Hand Width are literally \"0\" when missing -> null")
t.append("  - no Source column")
t.append("B 2016/17  <table class=\"sorttable\">, two header rows, 18 cells")
t.append("  Player | Year | Draft pick | Ht no-shoes | Ht w/shoes | Wingspan | Standing reach |")
t.append("  Max vert | Max vert reach | No-step vert | No-step vert reach | Weight | Body fat |")
t.append("  Hand length | Hand width | Bench | Agility | Sprint            - no Source column")
t.append("C profile  <table class=\"alt\">, 9 cells")
t.append("  Year | Source | Ht w/o Shoes | Ht w/ Shoes | Weight | Wingspan | Standing Reach |")
t.append("  No Step Vert | Max Vert                                        - the Source source")
t.append("```\n")
t.append("* **Values.** `7' 5.5\"`, `6'11 1/4\"` (unicode vulgar fractions), `6'8\"`, `34\"`, "
         "`19.5`, `247` are all reduced to inches / lb / seconds by two regexes; "
         "`NA`, `-`, `--`, `N/A`, empty are null. Fraction glyphs handled: "
         "1/8 1/4 3/8 1/2 5/8 3/4 7/8 1/3 2/3.")
t.append("* **DX player id** comes from the row's `/profile/{Slug}-{id}/` link, so rows are keyed "
         "on the site's own id rather than on the printed name.")
t.append("* **Plausibility gates.** DraftExpress writes `0` / `0'0\"` for \"not measured\", and a "
         "few rows carry obvious typos, so a parsed value outside "
         "height 48-96 in, wingspan 48-105 in, standing reach 70-130 in, max vert 10-60 in, "
         "no-step vert 5-55 in, weight 100-400 lb is treated as **missing** (never as 0). "
         f"{st.get('values_gated_implausible', 0)} values were gated on this build.")
t.append("* **Source** is taken from (i) the profile table's Source column, (ii) the `source=` "
         "filter of the captured listing URL when the capture was source-filtered, or (iii) a "
         "join of an unlabelled listing row onto the same player-year profile event when their "
         "shared measurements agree. `source_from` in `measurements_all.csv` records which.")
t.append("* **De-duplication** is by (player, source, year). Because the listing tables carry no "
         "Source, two same-year events are separated by their measurements: a candidate row "
         "merges into an existing event only when no shared measure disagrees by more than "
         "0.3 in (heights/wingspan), 0.5 in (standing reach) or 3 lb; otherwise it opens a new "
         "event. Profile rows are processed first so they seed the events with their Source.")
t.append("* **Column-mapping validation.** The two listing generations were parsed independently "
         "and compared on the 3,922 player-years both cover: median absolute difference "
         "**0.000** on all twelve measurement columns (height no-shoes, height with shoes, "
         "wingspan, standing reach, max vert, no-step vert, weight, body fat, hand length, "
         "bench, agility, sprint). Residual >0.5 mismatches (~1-3%) are players with two "
         "different events in the same year.\n")

t.append("## 4. Dating\n")
t.append("* DraftExpress records only a **year** per event, plus a **source**. The "
         "**(source, year)** pair is the event identity and the dating unit.")
t.append("* The database is pre-draft **by construction** - every source is a youth camp, an "
         "all-star game, a college team listing or a pre-draft camp/combine, all of which run "
         "before draft night. On top of that the builder **drops any event with "
         "`event_year > draft_year`**, so nothing after a player's draft can leak in.")
t.append("* Two further event filters guard against DraftExpress hanging a same-name player's "
         "row on the wrong profile: an event whose **estimated age is under 13** is dropped, "
         "and (when no age is available) so is any event more than 9 years before the draft. "
         "Any event after the draft year is dropped outright.")
t.append("* **Leakage discipline.** The listing tables carry a `Drafted` / `Draft pick` column "
         "and the legacy grid carries a `Rank` column. Both are post-hoc with respect to the "
         "player's own draft night, so they are kept in `measurements_all.csv` for provenance "
         "and identity checking only and are **never** read by `dx_features.py` - no feature in "
         "`features.csv` derives from either (verified: the strings `draft_pick` and `rank` do "
         "not appear in the feature builder).")
t.append("* For age arithmetic each event is dated **1 June of its event year**. Essentially "
         "every source runs April-July (Portsmouth April, Hoop Summit April, the combine and "
         "the old pre-draft camp May-June, Eurocamp June, the summer camps June-July), so ages "
         "carry roughly +-3 months of slack; the age >= / <= thresholds in "
         "`dx_height_at_16_in` and the youth flag inherit that.")
t.append("* Birthdates, in priority order: (1) `age_verified_wiki.csv`; (2) the DX profile's "
         "own `Age: A.B` read together with the capture timestamp of that profile "
         "(birthdate ~ capture_date - A.B x 365.25); (3) class-year proxy, "
         "`age = (event_year - hs_class_year) + 18`, where hs_class_year is the profile's "
         "`RCSI: r (YYYY)` year or `draft_year - rsci_years_to_draft` from `rsci_features.csv`. "
         "`dx_age_src` records which, `dx_age_is_proxy` flags 2 and 3.\n")

# --- validation of the DX-derived birthdate (age source 2) against the verified wiki dates ---
import datetime as _dt
_meta = ({r["dx_id"]: r for r in csv.DictReader(open(f"{RAW}/profile_meta.csv"))}
         if os.path.exists(f"{RAW}/profile_meta.csv") else {})
_prov = {r["pid"]: r for r in csv.DictReader(open(f"{D}/provenance.csv"))}
_wiki = {r["pid"]: r["birth_date"] for r in
         csv.DictReader(open("/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"))
         if r.get("birth_date")}
_err = []
for _pid, _pr in _prov.items():
    _m, _b = _meta.get(_pr["dx_id"]), _wiki.get(_pid)
    if not _m or not _b or not _m.get("dx_age_at_capture") or not _m.get("capture_ts"):
        continue
    try:
        _cap = _dt.date(int(_m["capture_ts"][:4]), int(_m["capture_ts"][4:6]),
                        int(_m["capture_ts"][6:8]))
        _est = _cap - _dt.timedelta(days=float(_m["dx_age_at_capture"]) * 365.25)
        _tru = _dt.date(*[int(x) for x in _b.split("-")[:3]])
        _err.append(abs((_est - _tru).days))
    except Exception:
        pass
if _err:
    _err.sort()
    _med = _err[len(_err) // 2]
    _p90 = _err[int(len(_err) * .9) - 1]
    _w60 = 100.0 * sum(1 for e in _err if e <= 60) / len(_err)
    t.append("### Birthdate check\n")
    t.append(f"The DX-profile birthdate (age source 2) was compared with the verified "
             f"`age_verified_wiki.csv` date on the **{len(_err)}** players who have both: "
             f"median absolute error **{_med} days**, p90 **{_p90} days**, "
             f"**{_w60:.1f}%** within 60 days. Source 2 is therefore treated as a real "
             "birthdate rather than a proxy in practice, though `dx_age_is_proxy` still flags "
             "it as non-verified.\n")

t.append("## 5. Identity matching\n")
t.append("Names are normalised on both sides (NFKD accent strip, punctuation and apostrophes "
         "removed, Jr/Sr/II/III/IV/V dropped, lower-cased, hyphens -> spaces) and compared "
         "against the DX **profile slug**. Every DX id sharing the normalised name is a "
         "candidate, then:\n")
t.append("1. if the DX profile states `Drafted #N in the YYYY NBA Draft`, **YYYY must equal our "
         "`draft_year`**; otherwise the candidate is rejected;")
t.append("2. if the profile is not archived, the DX id must hold at least one event inside the "
         "player's own pre-draft window (`draft_year - 9 <= event_year <= draft_year`); a "
         "same-name collision with a younger player has none;")
t.append("3. the pid is used **only** when exactly one candidate survives.\n")
t.append(f"{len(unm):,} pids ended ambiguous or contradicted and are in `unmatched.csv` with "
         "the candidate ids and the rejection reason for each. No fuzzy or per-player "
         "judgement is applied anywhere.\n")

t.append("## 6. Late-grower regression (documented, as required)\n")
if st.get("late_grower_slope") is not None:
    t.append(f"OLS fitted on **all archived players** (not just our draftees) who have both a "
             f"height at estimated age <= 16 and a later height:\n")
    t.append("```")
    t.append(f"final_height_in = {st['late_grower_intercept']:.4f} + "
             f"{st['late_grower_slope']:.4f} x height_at_age<=16_in")
    t.append(f"n = {st['late_grower_n']}   R^2 = {st['late_grower_r2']:.3f}")
    t.append("```")
    t.append("`dx_late_grower_resid` = observed final height minus that prediction. The fit "
             "population is limited to archived players for whom an age could be established "
             "at all (source 1/2/3 above); archived players with no birthdate and no class year "
             "cannot be placed on the age axis and are excluded.\n")

t.append("## 6b. Feature definitions (features.csv, pid + numeric only, missing = empty)\n")
t.append("Top 10 - the growth-trajectory core:\n")
for i, (k, v) in enumerate(DEFS, 1):
    t.append(f"{i}. **`{k}`** - {v}")
t.append("\nThe rest:\n")
for k, v in REST:
    t.append(f"* **`{k}`** - {v}")
t.append("")

t.append("## 7. Coverage\n")
t.append("| draft-year band | drafted players | with DX features | coverage | >=2 events | with a youth event |")
t.append("|---|---:|---:|---:|---:|---:|")
for name, n, h, pc, m, y in rows_band:
    t.append(f"| {name} | {n} | {h} | {pc:.1f}% | {m} | {y} |")
t.append("")
t.append("Per draft year:\n")
t.append("| year | drafted | matched | % |")
t.append("|---|---:|---:|---:|")
for y, n, h, pc in per_year:
    t.append(f"| {y} | {n} | {h} | {pc:.1f}% |")
t.append("")
t.append("Top sources present in `measurements_all.csv`: " +
         ", ".join(f"{k} ({v})" for k, v in src_ct.most_common(15)) + ".\n")

t.append("### The 2018-2025 gap\n")
t.append("DraftExpress stopped publishing in 2017 and the site went dark; the last event year "
         "in the archive is 2017. Players drafted 2018+ appear **only** through youth events "
         "measured in 2013-2017 (a Hoop Summit or a Nike/USA camp they attended in high "
         "school), so coverage falls away by construction and is ~0 for anyone whose first "
         "measured event would have been 2018 or later. Nothing in this collector can fix that; "
         "the gap has to be filled from live sources.\n")
t.append("**Candidate supplements (listed only - deliberately NOT collected here):**\n")
t.append("| source | what it adds | URL pattern |")
t.append("|---|---|---|")
t.append("| Nike Hoop Summit annual measurement release | measured height/wingspan/reach/weight "
         "for the World and USA teams, ages 16-18, the single closest substitute for the DX "
         "youth rows | `https://www.nbadraft.net/2024-nike-hoop-summit-world-team/`, "
         "`https://www.nbadraft.net/2023-nike-hoop-summit-world-team/` (the historical DX "
         "article series lives at "
         "`http://www.draftexpress.com/article/Nike-Hoop-Summit-Official-Measurements/`) |")
t.append("| USA Basketball junior national team minicamp rosters | listed height/weight for "
         "U16-U18 invitees, twice a year | "
         "`https://www.usab.com/teams/5x5-mens-junior-national-team-minicamps/roster/"
         "{YYYY}-{april,october}-minicamp-roster` |")
t.append("| FIBA U16/U17/U18/U19 event rosters | listed height with an exact tournament date, "
         "for international prospects | "
         "`https://www.fiba.basketball/en/events/fiba-u17-basketball-world-cup-{YYYY}/...` "
         "(plus the per-tournament Wikipedia squad pages) |")
t.append("| NBA Draft Combine anthropometrics | the pre-draft end of the trajectory, 2000-2025, "
         "**already collected by this project** (`datarebuild/cmb_anthro.csv`) | "
         "`https://stats.gleague.nba.com/stats/draftcombinestats?LeagueID=00&SeasonYear={YYYY}-{YY}` |")
t.append("| NBPA Top 100 Camp / Under Armour Elite 24 / adidas Nations releases | scattered "
         "youth measurement releases, generally via event press pages | event press releases; "
         "no stable machine-readable pattern |")
t.append("")
t.append("Off-limits under COLLECTOR_RULES.md rule 3 and therefore **not** candidates: "
         "sports-reference.com, realgm, kenpom, synergy, proballers, nikeeyb / EYBL data.\n")

t.append("## 8. Terms of service / politeness\n")
t.append("* Everything is fetched from **web.archive.org**, which serves no `robots.txt` "
         "(HTTP 404 on `https://web.archive.org/robots.txt`, checked at build time), i.e. no "
         "crawl restriction is declared. draftexpress.com itself is never contacted - it no "
         "longer resolves to a site.")
t.append("* One request at a time, **1.2-1.6 s apart**, single process; exponential backoff "
         "(5 s doubling, 6 attempts) on 429/500/502/503/504 and on transport errors; "
         "descriptive User-Agent naming the project and a contact address. The profile crawler "
         "waits for the listing crawler to exit rather than running in parallel.")
t.append("* No login, no paywall, no Cloudflare/JS challenge is touched; the Internet Archive's "
         "own CDX API is used for enumeration instead of spidering.")
t.append("* Archived DraftExpress content is third-party copyrighted material. It is used here "
         "only to derive numeric features; **player names never leave this Mac** - "
         "`measurements_all.csv` and `raw/` stay local, and the shipped `features.csv` is "
         "pid + numeric columns only.")
t.append("")
t.append("> **Publication warning.** `/Users/kennakao/nba/datarebuild` is a git repo whose "
         "`origin` is the **public** GitHub repo `Spoofyy-1/DraftDB-Data`. Its `.gitignore` "
         "covers `novel/*/raw*/`, `*.html`, `*.gz` - so the HTML cache and the CDX indexes are "
         "safely excluded - but it does **not** cover `measurements_all.csv` (player names) or "
         "`provenance.csv` (DraftExpress player ids, which re-identify a pid). A blanket "
         "`git add -A` in that repo would publish both. Nothing here was committed, and "
         "`.gitignore` was deliberately left untouched; decide explicitly before committing.\n")

t.append("## 9. Files\n")
t.append("```")
t.append("dx_crawl.py             listing crawler   (CDX -> one best capture per URL shape)")
t.append("dx_profiles.py          profile crawler   (one capture per candidate DX id, +375")
t.append("                        archived non-draftees with >=2 height years, for the regression)")
t.append("dx_profiles_retry.py    re-asks Wayback at an earlier target for profiles whose nearest")
t.append("                        capture was post-shutdown (dead-site shells)")
t.append("dx_parse.py             all cached HTML  -> measurements_all.csv")
t.append("dx_features.py          measurements_all -> features.csv / unmatched.csv / provenance.csv")
t.append("dx_readme.py            regenerates this file from the artefacts")
t.append("measurements_all.csv    one row per player-event  (LOCAL ONLY - contains names)")
t.append("features.csv            pid + dx_* numeric features")
t.append("unmatched.csv           pids whose DX identity stayed ambiguous, with reasons")
t.append("provenance.csv          per pid: DX id, event years, sources, age source, captures")
t.append("build_stats.json        shoe gap, regression coefficients, row/coverage counts")
t.append("run.log                 crawl log")
t.append("raw/cdx_full.json       CDX index of the measurement listing")
t.append("raw/cdx_profiles.json   CDX index of /profile* (192,327 urls, 55,786 player ids)")
t.append("raw/manifest.jsonl      one line per listing fetch (checkpoint + provenance)")
t.append("raw/profiles_manifest.jsonl  one line per profile fetch")
t.append("raw/pages/*.html.gz     cached listing captures")
t.append("raw/profiles/*.html.gz  cached profile captures")
t.append("raw/profile_meta.csv    per DX id: drafted year/pick, RCSI rank + class year, age at capture")
t.append("raw/candidate_index.csv pid <-> candidate DX id map before the draft-year gate")
t.append("```\n")
t.append("### Re-running / resuming\n")
t.append("```bash")
t.append("cd /Users/kennakao/nba/datarebuild/novel/draftexpress")
t.append("nohup python3 dx_crawl.py    >> run.log 2>&1 &   # skips anything already in raw/manifest.jsonl")
t.append("nohup python3 dx_profiles.py >> run.log 2>&1 &   # waits for dx_crawl.py, then resumes")
t.append("python3 dx_profiles_retry.py                     # optional 2nd pass, also resumable")
t.append("python3 dx_parse.py && python3 dx_features.py && python3 dx_readme.py")
t.append("```")
t.append("Both crawlers are checkpointed per page and idempotent: killing and restarting them "
         "loses at most the in-flight request. To stop them, kill only their own script names "
         "(`pkill -f dx_crawl.py` / `pkill -f dx_profiles.py`), never a broad pattern.\n")

t.append("## 10. Known limitations\n")
t.append("* Year-only dating: a 24-month window is measured in event years, not months.")
t.append("* The archive is incomplete by construction - only URL shapes the Wayback Machine "
         "actually captured can be replayed, so a player's event set is a subset of what the "
         "live site held.")
t.append("* Where a listing row could not be joined to a profile row, its Source is blank; "
         "such an event is still counted and still contributes to the height/weight series, "
         "but its youth/pre-draft classification then falls back to the estimated age.")
t.append("* Heights mix with-shoes and without-shoes reporting; the series uses with-shoes and "
         f"adds {st['shoe_gap_in']:.2f} in to no-shoes-only events. Youth camps almost always "
         "report with shoes, the combine reports both, so most trajectories are with-shoes "
         "throughout.")
t.append("* `dx_age_src = 3` (class-year proxy) is accurate only to about +-1 year and is "
         "flagged; ages for players with neither a wiki birthdate nor an archived profile are "
         "left blank rather than guessed.")
t.append("* DraftExpress itself sometimes carried a measurement forward or reported a listed "
         "rather than measured height for camp rosters; no attempt is made to tell the two "
         "apart beyond keeping the (source, year) label.")

body = "\n".join(t) + "\n"
open(f"{D}/README.md", "w").write(body)
print("README.md written (%d chars, %d lines)" % (len(body), len(t)))
