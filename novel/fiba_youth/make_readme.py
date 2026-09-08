#!/usr/bin/env python3
"""
Generate README.md for the fiba_youth collector.  Static prose plus tables
regenerated from the current outputs, so the README never drifts from the CSVs.

Usage: python3 make_readme.py      (run after build.py)
"""
import csv
import glob
import gzip
import json
import os
import re
from collections import defaultdict

from fibalib import HERE, PARSED
from competitions import COMPETITIONS, LEVEL_LABEL, level_of
from build import (CUTOFF, DEFS, MIN_GAMES, MIN_MINUTES, AGE_LO, AGE_HI,
                   load_identity, ncaa_track)

BASE = "https://www.fiba.basketball/en/history"


def read(path):
    p = os.path.join(HERE, path)
    if not os.path.exists(p):
        return []
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    tours = read("field_tournaments.csv")
    feats = read("features.csv")
    pts = read("player_tournaments.csv")
    unm = read("unmatched.csv")
    ident, by_norm, birth = load_identity()
    dy = {c["pid"]: c["draft_year"] for c in ident}

    # ---- per-competition table -------------------------------------------
    seen = defaultdict(list)
    for t in tours:
        seen[t["comp_slug"]].append(t)
    edition_counts = {}
    for path in glob.glob(os.path.join(HERE, "raw", "sitemaps", "*.xml")):
        cid = os.path.basename(path)[:-4]
        if not cid.isdigit():
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                xml = fh.read()
        except OSError:                       # not gzipped
            with open(path, encoding="utf-8", errors="replace") as fh:
                xml = fh.read()
        edition_counts[cid] = len(re.findall(r"/(\d+)/sitemap\.xml", xml))

    rows_comp = []
    for slug in sorted(COMPETITIONS, key=lambda s: (-level_of(*COMPETITIONS[s]),
                                                    s)):
        tier, scope, age = COMPETITIONS[slug]
        cid = slug.split("-", 1)[0]
        got = seen.get(slug, [])
        yrs = sorted(int(t["year"]) for t in got if t["year"])
        rows_comp.append((
            slug, level_of(tier, scope, age), scope, tier, age,
            edition_counts.get(cid, ""), len(got),
            ("%d-%d" % (yrs[0], yrs[-1])) if yrs else "-",
            sum(int(t["n_roster"]) for t in got),
            "%s/%s" % (BASE, slug)))

    # ---- coverage --------------------------------------------------------
    has = {f["pid"]: (f.get("fy_has_youth") == "1") for f in feats}
    bands = [("2000-2007", 2000, 2007), ("2008-2018", 2008, 2018),
             ("2019-2025", 2019, 2025)]
    cov_band = []
    for name, lo, hi in bands:
        tot = [c for c in ident if lo <= c["draft_year"] <= hi]
        got = [c for c in tot if has.get(c["pid"])]
        cov_band.append((name, len(got), len(tot),
                         100.0 * len(got) / max(1, len(tot))))
    nt = ncaa_track()
    cov_track = []
    for label, sel in (("US / NCAA-track (col_gp present)",
                        lambda p: nt.get(p) == 1),
                       ("non-NCAA, i.e. international track",
                        lambda p: nt.get(p) == 0),
                       ("not present in the v4 inputs",
                        lambda p: p not in nt)):
        tot = [c for c in ident if sel(c["pid"])]
        got = [c for c in tot if has.get(c["pid"])]
        cov_track.append((label, len(got), len(tot),
                          100.0 * len(got) / max(1, len(tot))))

    nat = defaultdict(int)
    for r in pts:
        pass
    # nationality mix of covered players, from provenance-free info in raw
    natmix = {"USA": 0, "other": 0}
    prov = read("provenance.csv")
    fiba_nat = {}
    for path in sorted(glob.glob(os.path.join(PARSED, "*_*.json"))):
        if not re.match(r"^\d+_\d+\.json$", os.path.basename(path)):
            continue
        with open(path) as fh:
            rec = json.load(fh)
        for p in rec.get("players", []):
            if p.get("nationality"):
                fiba_nat.setdefault(p["player_id"], p["nationality"])
    for r in prov:
        if r["source"] != "fiba.basketball":
            continue
        try:
            fid = int(r["fiba_person_id"])
        except (TypeError, ValueError):
            continue
        n = fiba_nat.get(fid)
        if not n:
            continue
        natmix["USA" if n == "USA" else "other"] += 1

    hs_lo = hs_hi = hs_rev = hs_ts = "n/a"
    hs_path = os.path.join(PARSED, "hoop_summit.json")
    n_world = 0
    if os.path.exists(hs_path):
        with open(hs_path) as fh:
            hs = json.load(fh)
        ys = [r["draft_year"] for r in hs["rows"]]
        hs_lo, hs_hi = (min(ys), max(ys)) if ys else ("n/a", "n/a")
        hs_rev, hs_ts = hs["revid"], hs["rev_ts"]
        n_world = sum(1 for f in feats if f.get("fy_hoop_summit_world") == "1")

    n_feat_cols = len(feats[0]) - 1 if feats else 0

    out = []
    A = out.append
    A("# fiba_youth - age-relative FIBA youth-tournament feature block")
    A("")
    A("Pre-draft features built from FIBA's own competition archive for men's")
    A("U15-U19 national-team tournaments, 2000-2025, plus Nike Hoop Summit")
    A("World Select participation from Wikipedia.")
    A("")
    A("This block is deliberately **separate** from the existing `intl_*`")
    A("inputs.  The project's current inputs fold crude youth lines")
    A("(`intl_youth_pts36`, `intl_youth_n`) into the international *pro*")
    A("season block, which mixes a 16-year-old's U16 EuroBasket week with a")
    A("grown man's Liga ACB season and penalises college players.  Everything")
    A("here is instead **age-relative**: every rate is z-scored inside the")
    A("field of the tournament the player actually played in, and age is")
    A("expressed relative to that same field's mean age.  Nothing in this")
    A("directory writes to `data_v4` or to any existing input file.")
    A("")
    A("## Outputs")
    A("")
    A("| file | rows | contents |")
    A("|---|---|---|")
    A("| `features.csv` | %d | one row per pid in the identity file, %d numeric `fy_*` columns, missing = empty |"
      % (len(feats), n_feat_cols))
    A("| `player_tournaments.csv` | %d | one row per matched pid x tournament: level, dates, games, minutes, per-40 rates, shooting rates, age, team finish, and the tournament field's mean/SD for age and every per-40 stat |"
      % len(pts))
    A("| `field_tournaments.csv` | %d | one row per tournament actually parsed: id, level, dates, team count, roster size, qualified-field size, field mean/SD age, URL |"
      % len(tours))
    A("| `unmatched.csv` | %d | FIBA youth players whose name hit the identity file but were rejected or ambiguous, with the reason |"
      % len(unm))
    A("| `provenance.csv` | %d | pid -> FIBA person id, tournaments used, source URLs |"
      % len(prov))
    A("")
    A("Raw pages are cached gzipped under `raw/pages/`, sitemaps under")
    A("`raw/sitemaps/`, and the per-tournament extraction (which doubles as")
    A("the crawl checkpoint) under `raw/parsed/`.  Re-runs are offline.")
    A("")
    A("## Sources")
    A("")
    A("* `https://www.fiba.basketball/en/history-sitemap_index.xml` - the 259")
    A("  competitions in the FIBA archive (fetched 2026-09-08).")
    A("* `https://www.fiba.basketball/en/history/<comp>/sitemap_index.xml` -")
    A("  the editions of one competition.")
    A("* `https://www.fiba.basketball/en/history/<comp>/<eventId>/players` -")
    A("  event metadata, team list, and the **full player field** with dates")
    A("  of birth, nationality, position and games played.")
    A("* `https://www.fiba.basketball/en/history/<comp>/<eventId>/teams/<team>`")
    A("  - per-player tournament totals for that team and the team's final")
    A("  ranking.")
    A("* `https://en.wikipedia.org/wiki/Nike_Hoop_Summit` - the \"Alumni")
    A("  selected in the NBA draft\" table (Name / Draft Year / NHS Year(s) /")
    A("  NHS Team), revision %s captured %s." % (hs_rev, hs_ts))
    A("")
    A("The `/stats` (leaders) tab was **not** used: it only returns the top 50")
    A("per category, which cannot define a field distribution.  Team pages give")
    A("the complete field at 1 + n_teams requests per edition.")
    A("")
    A("## Competitions crawled")
    A("")
    A("Selection rule applied to the 259 archive competitions: keep every")
    A("men's national-team competition at age category U15-U19.  Excluded:")
    A("women's events (slug contains `womens`), U20 and older, club")
    A("competitions, 3x3, and the U18 All-Star Game.")
    A("")
    A("`editions` counts every edition in the competition's sitemap;")
    A("`in range` counts those with season 2000-2025 that returned a player")
    A("field.  A cancelled edition (e.g. the 2020 U17 World Cup) contributes 0")
    A("roster rows.")
    A("")
    A("| competition | level | scope | div | age | editions | in range | years | roster rows | URL |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows_comp:
        A("| `%s` | %d | %s | %s | U%d | %s | %d | %s | %d | %s |" % r)
    A("")
    A("### Editions present, top-tier competitions")
    A("")
    A("The archive is not gap-free.  Years actually captured, 2000-2025:")
    A("")
    for slug, lvl, scope, tier, age, ed, n, yrs, roster, url in rows_comp:
        if lvl < 2:
            continue
        ys = sorted(int(t["year"]) for t in seen.get(slug, []) if t["year"])
        A("* `%s`: %s" % (slug, ", ".join(str(y) for y in ys) or "none"))
    A("")
    A("The FIBA U19 World Cup editions of **2001 (Japan) and 2005")
    A("(Argentina) are absent from FIBA's own competition sitemap**, so no")
    A("player from those tournaments is in this block.  That is a source gap,")
    A("not a filter, and it falls on the 2001-2008 draft classes.")
    A("")
    A("### Level ladder (`fy_best_level`)")
    A("")
    for k in sorted(LEVEL_LABEL, reverse=True):
        A("* **%d** - %s" % (k, LEVEL_LABEL[k]))
    A("")
    A("Two further rule-based adjustments on top of that ladder.")
    A("")
    A("**Same-season multi-phase records.** Before about 2005 FIBA files a")
    A("European championship as several events under one season - e.g. U18")
    A("EuroBasket 2000 appears as a 29-team qualifying round played in August")
    A("1999, an 18-team second round in April 2000, and the 12-team final")
    A("round in July 2000.  Within one competition-season the event with the")
    A("smallest field is treated as the final round and keeps its level; the")
    A("others drop one rung.  Each remains a separate row with its own dates")
    A("and its own field distribution, because each really was a separate")
    A("tournament, so `fy_n_tournaments` counts them separately.")
    A("")
    A("**Small continental fields.** A division-A")
    A("continental championship whose field has fewer than 6 teams drops one")
    A("rung.  The Oceania U16/U17/U18 championships are usually just Australia")
    A("versus New Zealand, and beating New Zealand twice is not the same test")
    A("as a 16-team U18 EuroBasket.  `field_tournaments.csv` carries `n_teams`")
    A("so the demotion is auditable.")
    A("")
    A("## Parsing rules")
    A("")
    A("fiba.basketball is a Next.js app that server-renders its data into the")
    A("RSC \"flight\" payload.  Extraction is purely rule-based:")
    A("")
    A("1. Concatenate every `self.__next_f.push([1,\"...\"])` argument and")
    A("   JSON-unescape each one (`json.loads('\"'+chunk+'\"')`), which")
    A("   preserves accented names exactly.")
    A("2. Event metadata = the object at `\"fibaSourceDatas\":{...}`, sliced by")
    A("   brace balancing and parsed with `json.loads`.  Fields used:")
    A("   `season`, `start`, `end`, `gender`, `ageCategory`, `fibaZone`,")
    A("   `competitionCategory`.")
    A("3. Team list = the first `\"teams\":[{\"teamId\"...` array.")
    A("4. Player field = every `\"player\":{...}` object carrying a")
    A("   `playerId` on the `/players` page.  Some rows emit")
    A("   `\"team\":\"$hh\"` RSC back-references instead of an inline team")
    A("   object; those get their team from the team pages via `teamId`.")
    A("5. Per-player totals = the `\"playerInCompetitionTeamStatistics\":[...]`")
    A("   array on each team page.  Team finish = `\"finalRanking\":<int>`.")
    A("6. Only rows with `gender` in {Men, boys, male} and `season` in")
    A("   2000-2025 are kept.")
    A("")
    A("Derived quantities (all from totals, never from the site's rounded")
    A("per-game numbers):")
    A("")
    A("```")
    A("minutes      = totalPlayTimeInSeconds / 60")
    A("<stat>40     = total<Stat> * 40 / minutes")
    A("pir40        = totalEfficiency * 40 / minutes      (FIBA efficiency/PIR)")
    A("usage40      = (FGA + 0.44*FTA + TOV) * 40 / minutes")
    A("TS%          = PTS / (2 * (FGA + 0.44*FTA))")
    A("eFG%         = (FGM + 0.5*3PM) / FGA")
    A("3PAr         = 3PA / FGA        FTr = FTA / FGA    FT% = FTM / FTA")
    A("```")
    A("")
    A("### Tournament field distribution")
    A("")
    A("Age is measured at the tournament's **last day**.  For a normal 10-day")
    A("event that is within a week of the start; for the few pre-2005 records")
    A("where FIBA merged qualifying and final phases into one entry spanning")
    A("months, it is the date of the final phase.  Age-relative features are")
    A("unaffected by the choice because the whole field uses the same")
    A("reference date.")
    A("")
    A("* **Age field** = every rostered player with a listed date of birth")
    A("  whose age at the tournament start is in [%.0f, %.0f] years; values"
      % (AGE_LO - 1, AGE_HI + 1))
    A("  outside that are DOB data errors and are dropped, not clamped.")
    A("* **Stat field** = players with >= %d games **and** >= %.0f total"
      % (MIN_GAMES, MIN_MINUTES))
    A("  minutes.  Per-40 rates explode for 3-minute cameos, so they are")
    A("  excluded from the mean/SD that define the z-scores.  Both counts are")
    A("  in `field_tournaments.csv` (`n_roster`, `n_qualified`) and in every")
    A("  `player_tournaments.csv` row.")
    A("* Mean and SD are the sample mean and sample SD (n-1).  A z-score is")
    A("  left empty when the field SD is 0 or the field has < 2 members.")
    A("")
    A("## Dating")
    A("")
    A("Every tournament carries `start` and `end` dates from the event")
    A("metadata.  A tournament is used for a player only if its **end date is")
    A("strictly before that player's draft-night cutoff** (22:00 UTC on the")
    A("dates listed in `COLLECTOR_RULES.md`, reproduced in `build.py`).  This")
    A("matters: the U19 World Cup is usually played in late June or early")
    A("July, so for example the 2017 edition (2017-07-01 to 2017-07-09) is")
    A("*post*-draft for a 2017 draftee and pre-draft for a 2019 draftee, and")
    A("is filtered accordingly.  Nothing is dated by season label alone.")
    A("")
    A("Nike Hoop Summit: the game is played in April, always before that")
    A("year's draft; a roster row is used only when its NHS year <= the")
    A("player's draft year.  The Wikipedia revision id and timestamp are")
    A("recorded (`%s`, `%s`)." % (hs_rev, hs_ts))
    A("")
    A("## Matching rules")
    A("")
    A("Identity file:")
    A("`/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv`")
    A("(2,560 rows).  Verified birthdates for 947 pids:")
    A("`/Users/kennakao/nba/datarebuild/age_verified_wiki.csv`.")
    A("")
    A("Matching is done once per **FIBA person** (`playerId` is stable across")
    A("editions), not per row, so a player's tournaments cannot disagree.")
    A("")
    A("1. Normalise both sides: NFKD, strip combining accents, map")
    A("   `Ø ø Đ đ Ł ł`, lower-case, drop punctuation, drop trailing")
    A("   `Jr/Sr/II/III/IV/V`, squeeze whitespace.")
    A("2. Primary key `\"first last\"`; if that has no identity hit, fall back")
    A("   to `\"last first\"` (FIBA reverses some names).")
    A("3. Candidates must satisfy **tournament year <= draft year**.")
    A("4. If FIBA lists a date of birth:")
    A("   * the player's age at at least one of his tournaments must be in")
    A("     [%.0f, %.0f];" % (AGE_LO, AGE_HI))
    A("   * if the pid has a verified birthdate in `age_verified_wiki.csv`,")
    A("     the **birth years must agree exactly**, otherwise the candidate is")
    A("     rejected (this is what separates the two Justin Jacksons);")
    A("   * otherwise `draft_year - birth_year >= 16`.")
    A("5. If FIBA lists no date of birth: `0 <= draft_year - first tournament")
    A("   year <= 8`.")
    A("6. Exactly one surviving candidate -> match.  Zero or more than one ->")
    A("   written to `unmatched.csv` with the reason; never guessed.")
    A("7. Post-check: if two FIBA persons claim the same pid (there are")
    A("   several Marko Simonovics), keep the one whose birth year implies a")
    A("   normal draft age (`17 <= draft_year - birth_year <= 28`) when that")
    A("   singles one out; otherwise drop them all.  Every drop is logged.")
    A("")
    A("**Second pass (legal name vs common name).** FIBA uses passport names,")
    A("so pass 1 misses `Benjamin Simmons` -> `Ben Simmons`,")
    A("`Guillermo Hernangomez` -> `Willy Hernangomez`,")
    A("`Michael Gilchrist` -> `Michael Kidd-Gilchrist`,")
    A("`Rowan Barrett` -> `RJ Barrett`.  For FIBA persons still unmatched, a")
    A("second pass requires **all** of: the FIBA date of birth equal to the")
    A("verified birthdate in `age_verified_wiki.csv` to the exact day; at least")
    A("one shared surname token; tournament year <= draft year; and an age at")
    A("some tournament in [%.0f, %.0f].  Exactly one survivor -> match; more"
      % (AGE_LO, AGE_HI))
    A("than one -> logged as ambiguous.  A pid already claimed by pass 1 is")
    A("never reused.  This pass is only possible for the 947 pids with a")
    A("verified birthdate, and it is still an exact-key join - no fuzzy string")
    A("similarity is used anywhere.")
    A("")
    A("**Draft classes without a documented cutoff.** `COLLECTOR_RULES.md`")
    A("lists draft-night cutoffs for 2000-2025.  The identity file also")
    A("contains a 2026 class; those pids get every column empty (not 0),")
    A("because without a cutoff no record can be certified pre-draft.  Add the")
    A("date to `CUTOFF` in `build.py` and re-run to fill them in.")
    A("")
    A("Note that `draft_year` in the identity file is the year the player")
    A("entered the NBA universe, which for a few undrafted-then-signed players")
    A("is later than their actual draft class; the rules above therefore do")
    A("not impose an upper bound on draft age beyond the age-at-tournament")
    A("window.")
    A("")
    A("Hoop Summit rows are matched on normalised name **and** draft year")
    A("(exact), with a single fallback: if the normalised name is unique in the")
    A("identity file and the identity draft year is >= the table's draft year,")
    A("the unique candidate is accepted.")
    A("")
    A("## Features (`features.csv`)")
    A("")
    A("All columns are numeric; empty means unknown, never 0.  Only")
    A("tournaments ending before the draft-night cutoff contribute.")
    A("\"Latest\" always means the last such tournament by end date.")
    A("")
    A("| column | definition |")
    A("|---|---|")
    A("| `fy_has_youth` | 1 if the player has >= 1 pre-draft FIBA U15-U19 tournament in this archive, else 0.  0 is a real observation (searched, not found), subject to the coverage caveats below. |")
    A("| `fy_n_tournaments` | Number of those tournaments. |")
    A("| `fy_best_level` | Max level ladder value over them (4/3/2/1 as above). |")
    A("| `fy_age_rel_last` | Age in years at the latest tournament minus that field's mean age.  Negative = younger than the field. |")
    A("| `fy_age_rel_min` | Minimum (most negative) age-minus-field-mean over all pre-draft tournaments. |")
    A("| `fy_underage_flag` | 1 if in any pre-draft tournament the player was >= 1.0 year younger than the field mean, else 0. |")
    A("| `fy_pts40_z_last` | Points per 40 at the latest tournament, z-scored in that tournament's qualified field. |")
    A("| `fy_pir40_z_last` | FIBA efficiency (PIR) per 40 at the latest tournament, z-scored in the same field. |")
    A("| `fy_ts_z_last` | True-shooting % at the latest tournament, z-scored in the same field. |")
    A("| `fy_ast40_z_last` | Assists per 40, z-scored in the same field. |")
    A("| `fy_stl_blk40_z_last` | (Steals + blocks) per 40, z-scored against the same field's steals+blocks per 40. |")
    A("| `fy_usage_proxy_z_last` | (FGA + 0.44*FTA + TOV) per 40, z-scored in the same field. |")
    A("| `fy_best_pts40_z` | Max points-per-40 z over all pre-draft tournaments. |")
    A("| `fy_best_pir40_z` | Max PIR-per-40 z over all pre-draft tournaments. |")
    A("| `fy_z_trend` | PIR-per-40 z at the latest tournament minus PIR-per-40 z at the first.  Empty when the player has only one tournament. |")
    A("| `fy_minutes_share_last` | Minutes per game at the latest tournament / 40. |")
    A("| `fy_team_finish_last` | The player's team's final ranking at the latest tournament (1 = winner). |")
    A("| `fy_hoop_summit_world` | 1 if the player appears on a Nike Hoop Summit **World Select** roster in a year <= his draft year, 0 if he appears only on the USA roster or not at all.  Empty for draft years outside %s-%s, which the Wikipedia table does not cover. |"
      % (hs_lo, hs_hi))
    A("")
    A("`player_tournaments.csv` additionally carries, per player-tournament:")
    A("tournament id, competition id, event id, level, age group, scope,")
    A("division, year, start/end dates, games, minutes, age at tournament,")
    A("team finish, `pts40 reb40 oreb40 dreb40 ast40 stl40 blk40 tov40 pir40")
    A("usage40`, `ts efg tpar ftr ftpct`, and for each of those the")
    A("tournament field's `field_<stat>_mean` and `field_<stat>_sd`, plus")
    A("`field_age_mean`, `field_age_sd`, `field_n_roster`, `field_n_qual`.")
    A("")
    A("## Coverage")
    A("")
    A("### By draft-year band")
    A("")
    A("| band | with FIBA youth data | drafted players | share |")
    A("|---|---|---|---|")
    for name, g, t, p in cov_band:
        A("| %s | %d | %d | %.1f%% |" % (name, g, t, p))
    A("")
    A("### US vs international")
    A("")
    A("The identity file has no nationality column, so the split below uses a")
    A("read-only proxy from the frozen v4 inputs: a pid with a non-empty")
    A("`col_gp` has NCAA season data and came through US college basketball.")
    A("(`intl_gp` is unusable for this: the crude youth lines were merged into")
    A("the `intl_*` pro block, so US high-schoolers with one FIBA youth")
    A("appearance carry `intl_gp` too - exactly the contamination this block")
    A("exists to replace.)")
    A("")
    A("| group | with FIBA youth data | players | share |")
    A("|---|---|---|---|")
    for label, g, t, p in cov_track:
        A("| %s | %d | %d | %.1f%% |" % (label, g, t, p))
    A("")
    A("Among the players actually covered, FIBA nationality splits **USA %d /"
      % natmix["USA"])
    A("other %d** - USA Basketball sends full-strength teams to the U17 and"
      % natmix["other"])
    A("U19 World Cups, so this block is not an internationals-only feature.")
    A("")
    A("Nike Hoop Summit: %d pids flagged as World Select." % n_world)
    A("")
    A("## Terms of service and robots")
    A("")
    A("* `https://www.fiba.basketball/robots.txt` (fetched 2026-09-08)")
    A("  disallows only `/login`, `/register`, `/welcome`,")
    A("  `/forgot-password`, `/auth-callback` and their localised variants.")
    A("  Nothing under `/en/history/` is disallowed, and the file advertises")
    A("  the sitemaps this collector uses.")
    A("* FIBA Terms and Conditions section 4 is a standard copyright")
    A("  reservation over site \"Content\" (pictures, graphics, logos, texts,")
    A("  videos, animations, sounds, games and other works); there is no")
    A("  anti-crawling, anti-robot or rate clause.  This collector keeps the")
    A("  fetched pages only as a local cache for reproducibility and publishes")
    A("  only derived numeric aggregates, no FIBA text, images or video.")
    A("* Requests: one connection, >= 1.1 s apart, exponential backoff with")
    A("  jitter on 429/500/502/503/504, descriptive User-Agent")
    A("  `DraftDB-Research/1.0 (non-commercial NBA draft research; contact")
    A("  mike@alphax.inc)`.  No login, no paywall, no JS challenge, no")
    A("  Cloudflare bypass: the pages are plain server-rendered HTML.")
    A("* Wikipedia is read through the public MediaWiki API with the same")
    A("  User-Agent; content is CC BY-SA and only two derived bits are kept.")
    A("* Sites the project bans (sports-reference, kenpom, synergy, realgm,")
    A("  proballers, eurobasket.com, legabasket, tblstat, acb.com, nikeeyb,")
    A("  EYBL) were **not** contacted.")
    A("")
    A("## Known limitations")
    A("")
    A("1. **Archive depth.** FIBA's per-player box scores thin out before the")
    A("   mid-2000s: some editions from 2000-2004 list rosters without dates")
    A("   of birth or without per-player totals.  A player with no DOB gets no")
    A("   age-relative feature (empty, not 0) even when his rate stats parse.")
    A("   This is why the 2000-2007 draft band is much thinner than the later")
    A("   ones - it is a source-coverage effect, not a signal.")
    A("2. **`fy_has_youth = 0` is asymmetric across eras** for the same")
    A("   reason.  Any model using it should be aware that a 2001 draftee's 0")
    A("   is weaker evidence than a 2021 draftee's 0.")
    A("3. **The Hoop Summit source stops at the 2022 draft** (the Wikipedia")
    A("   article carries a `Missing information: 2023-2025 NBA drafts` tag),")
    A("   so `fy_hoop_summit_world` is empty for those draft years rather than")
    A("   0.  It is also derived from a table of *drafted* alumni, which is")
    A("   fine here because the universe is drafted players, but it would not")
    A("   generalise to undrafted prospects.")
    A("4. **Name matching is conservative.** Players whose name normalises to")
    A("   more than one identity row, or whose FIBA birth year contradicts the")
    A("   verified birthdate, are dropped and logged rather than guessed, so")
    A("   coverage is a slight under-count.")
    A("5. **Final ranking is a team outcome**, not a player one, and small")
    A("   fields (some zone events have 4-6 teams) make it a coarse variable.")
    A("6. **Division B/C and zone events have weak fields**, so a big z-score")
    A("   there is worth much less than the same z at a U19 World Cup;")
    A("   `fy_best_level` is provided so a model can interact the two.")
    A("")
    A("## Running and resuming")
    A("")
    A("```sh")
    A("cd /Users/kennakao/nba/datarebuild/novel/fiba_youth")
    A("nohup python3 -u crawl.py >> run.log 2>&1 &   # crawl (resumable)")
    A("python3 hoop_summit.py                        # Wikipedia, seconds")
    A("python3 build.py | tee build.log              # features from cache")
    A("python3 make_readme.py                        # regenerate this file")
    A("```")
    A("")
    A("`crawl.py` checkpoints one JSON per tournament in `raw/parsed/`; an")
    A("event whose file exists with `\"complete\": true` is skipped, and every")
    A("HTTP response is cached under `raw/pages/`, so re-running after an")
    A("interruption costs only the un-fetched pages.  `crawl.py <prefix>`")
    A("restricts the run to competitions whose slug starts with `<prefix>`.")
    A("`build.py` reads only the cache and can be re-run at any time, including")
    A("while the crawl is still going - it simply reports whatever is on disk.")
    A("")
    A("To stop the crawl, find it with `pgrep -f 'python3 -u crawl.py'` and")
    A("kill that pid only (never a broad pattern).")
    A("")

    with open(os.path.join(HERE, "README.md"), "w") as fh:
        fh.write("\n".join(out))
    print("README.md written (%d lines)" % len(out))


if __name__ == "__main__":
    main()
