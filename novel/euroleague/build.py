#!/usr/bin/env python3
"""
Build the international data spine from the cached Euroleague API responses.

Runs entirely offline against raw/ so it can be re-run at any time while the
pull is still going (it simply sees more games each time).

Stages
  1. parse    raw/stats/**  -> player_games.csv.gz  (one row per player-game)
                            -> registrations.csv.gz (person x season x club)
  2. match    persons -> pid  (identity file + wiki birthdates)
                            -> matches.csv, unmatched.csv
  3. features pre-draft-only aggregation -> features.csv, provenance.csv

Usage:  python3 build.py            (all stages)
        python3 build.py parse      (single stage)
"""
import gzip
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
IDENTITY = ("/Users/kennakao/Downloads/nba_redraft_handoff/"
            "identity_KEEP_SEPARATE/tabular_names.csv")
WIKI_AGE = "/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"

PG_PATH = os.path.join(HERE, "player_games.csv.gz")
REG_PATH = os.path.join(HERE, "registrations.csv.gz")
MATCH_PATH = os.path.join(HERE, "matches.csv")
UNMATCHED_PATH = os.path.join(HERE, "unmatched.csv")
FEAT_PATH = os.path.join(HERE, "features.csv")
PROV_PATH = os.path.join(HERE, "provenance.csv")

# Draft-night cutoffs from COLLECTOR_RULES.md: a record counts as pre-draft
# only if its timestamp is strictly before 22:00 UTC on this date.
DRAFT_DATES = {
    2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26", 2003: "2003-06-26",
    2004: "2004-06-24", 2005: "2005-06-28", 2006: "2006-06-28", 2007: "2007-06-28",
    2008: "2008-06-26", 2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
    2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26", 2015: "2015-06-25",
    2016: "2016-06-23", 2017: "2017-06-22", 2018: "2018-06-21", 2019: "2019-06-20",
    2020: "2020-11-18", 2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
    2024: "2024-06-26", 2025: "2025-06-25",
}
# 2026 has no published cutoff in COLLECTOR_RULES.md.  Rather than invent a
# draft night we use a deliberately conservative 2026-06-01 (earlier than any
# plausible draft date), so those rows can only ever under-count, never leak.
CONSERVATIVE_2026 = "2026-06-01"

# Vashro level-of-competition ratings (fansided.com deep-dives article, 2015).
TIER = {"E": 1.61, "U": 0.92, "AL": 0.82, "J": -0.65}

COMP_PREFIX = {"E": "el2", "U": "eu2"}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def norm_name(s):
    """Accent-strip, drop punctuation and generational suffixes, sort tokens."""
    if not isinstance(s, str) or not s.strip():
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("'", "").replace("`", "").replace("’", "")
    s = re.sub(r"[^a-z ]+", " ", s)
    toks = [t for t in s.split() if t and t not in SUFFIXES]
    return " ".join(toks)


def name_key(s):
    """Order-insensitive key: handles 'SURNAME, FIRST' vs 'First Surname'."""
    n = norm_name(s.replace(",", " ") if isinstance(s, str) else s)
    return " ".join(sorted(n.split()))


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def cutoff_for(draft_year):
    d = DRAFT_DATES.get(int(draft_year))
    if d is None:
        if int(draft_year) == 2026:
            return datetime.fromisoformat(CONSERVATIVE_2026 + "T00:00:00")
        return None
    return datetime.fromisoformat(d + "T22:00:00")


# Some API person records carry a corrupt birthDate (e.g. persons listed in the
# 2006 U18 tournament with a 1998 birth year -> age 8).  Ages outside these
# bands are treated as unknown rather than propagated into features.
# The JT08/JT09 tournaments carry a block of placeholder birthdates set to
# exactly 20.0 years before the tournament date; genuine U18 fields top out at
# 18.4, so a 19.0 ceiling excludes the placeholders without touching real data.
ANGT_FIELD_BAND = (14.0, 19.0)    # who counts as part of a U18 tournament field
ANGT_PLAYER_BAND = (13.0, 19.5)   # our own player's age at a U18 tournament
SENIOR_BAND = (14.0, 45.0)        # our own player's age in a senior competition


def guard_age(a, band):
    """Return NaN for an implausible age instead of propagating bad birthdates."""
    if a is None or pd.isna(a):
        return np.nan
    return float(a) if band[0] <= a <= band[1] else np.nan


def safe_div(a, b):
    """Return NaN (-> empty in the csv) rather than 0 when the denominator is 0."""
    a, b = float(a), float(b)
    return a / b if b > 0 else np.nan


# --------------------------------------------------------------------------
# stage 1: parse the raw cache
# --------------------------------------------------------------------------
STAT_MAP = [
    ("min_sec", "timePlayed"), ("pir", "valuation"), ("pts", "points"),
    ("fg2m", "fieldGoalsMade2"), ("fg2a", "fieldGoalsAttempted2"),
    ("fg3m", "fieldGoalsMade3"), ("fg3a", "fieldGoalsAttempted3"),
    ("ftm", "freeThrowsMade"), ("fta", "freeThrowsAttempted"),
    ("fgm", "fieldGoalsMadeTotal"), ("fga", "fieldGoalsAttemptedTotal"),
    ("treb", "totalRebounds"), ("dreb", "defensiveRebounds"),
    ("oreb", "offensiveRebounds"), ("ast", "assistances"), ("stl", "steals"),
    ("tov", "turnovers"), ("blk", "blocksFavour"), ("blk_ag", "blocksAgainst"),
    ("pf", "foulsCommited"), ("fd", "foulsReceived"), ("pm", "plusMinus"),
]


def parse():
    rows, regs = [], {}
    # game metadata: dates come from the cached game listings
    meta = {}
    for comp in ("E", "U", "J"):
        gdir = os.path.join(RAW, "games", comp)
        if not os.path.isdir(gdir):
            continue
        for fn in sorted(os.listdir(gdir)):
            if not fn.endswith(".json.gz"):
                continue
            season = fn[:-8]
            for g in read_gz(os.path.join(gdir, fn)).get("data", []):
                dt = parse_dt(g.get("utcDate")) or parse_dt(g.get("date"))
                meta[(comp, season, g.get("gameCode"))] = {
                    "dt": dt,
                    "season_year": (g.get("season") or {}).get("year"),
                    "phase": (g.get("phaseType") or {}).get("code"),
                    "round": g.get("round"),
                    "local": ((g.get("local") or {}).get("club") or {}).get("code", ""),
                    "road": ((g.get("road") or {}).get("club") or {}).get("code", ""),
                }
    log(f"parse: {len(meta)} games in the cached listings")

    n_files = n_missing = 0
    for comp in ("E", "U", "J"):
        sdir = os.path.join(RAW, "stats", comp)
        if not os.path.isdir(sdir):
            continue
        for season in sorted(os.listdir(sdir)):
            pdir = os.path.join(sdir, season)
            if not os.path.isdir(pdir):
                continue
            for fn in sorted(os.listdir(pdir)):
                if not fn.endswith(".json.gz"):
                    continue
                gc = int(fn[:-8])
                try:
                    d = read_gz(os.path.join(pdir, fn))
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("_missing"):
                    n_missing += 1
                    continue
                n_files += 1
                m = meta.get((comp, season, gc), {})
                gdt = m.get("dt")
                for side, other in (("local", "road"), ("road", "local")):
                    blk = d.get(side) or {}
                    players = blk.get("players") or []
                    if not players:
                        continue
                    tot = blk.get("total") or {}
                    team_min = sum((p.get("stats") or {}).get("timePlayed", 0)
                                   for p in players) / 60.0
                    # opponent from the game listing (authoritative); fall back
                    # to the other side's first player's club code
                    opp_club = m.get("road" if side == "local" else "local", "")
                    if not opp_club:
                        opp = ((d.get(other) or {}).get("players") or [{}])
                        if opp:
                            opp_club = (((opp[0].get("player") or {}).get("club")
                                         or {}).get("code", ""))
                    for p in players:
                        pl = p.get("player") or {}
                        per = pl.get("person") or {}
                        st = p.get("stats") or {}
                        code = per.get("code")
                        if not code:
                            continue
                        club = (pl.get("club") or {}).get("code", "")
                        r = {
                            "comp": comp, "season": season,
                            "season_year": m.get("season_year"),
                            "game_code": gc,
                            "game_dt": gdt.isoformat() if gdt else "",
                            "phase": m.get("phase") or "",
                            "person_code": code,
                            "name": per.get("name") or "",
                            "birth_date": (parse_dt(per.get("birthDate")).date().isoformat()
                                           if parse_dt(per.get("birthDate")) else ""),
                            "height": per.get("height") or "",
                            "weight": per.get("weight") or "",
                            "country": (per.get("country") or {}).get("code", ""),
                            "birth_country": (per.get("birthCountry") or {}).get("code", ""),
                            "team": club, "opponent": opp_club,
                            "home": 1 if side == "local" else 0,
                            "start": 1 if st.get("startFive") else 0,
                            "team_min": round(team_min, 3),
                            "team_fga": tot.get("fieldGoalsAttemptedTotal", 0),
                            "team_fta": tot.get("freeThrowsAttempted", 0),
                            "team_tov": tot.get("turnovers", 0),
                            "team_pts": tot.get("points", 0),
                        }
                        for out_k, in_k in STAT_MAP:
                            r[out_k] = st.get(in_k, 0) or 0
                        r["min"] = round(r.pop("min_sec") / 60.0, 3)
                        rows.append(r)

                        rs, re_ = pl.get("startDate"), pl.get("endDate")
                        key = (code, comp, season, club, rs, re_)
                        if key not in regs:
                            regs[key] = {
                                "person_code": code, "comp": comp, "season": season,
                                "club": club,
                                "reg_start": (parse_dt(rs).date().isoformat()
                                              if parse_dt(rs) else ""),
                                "reg_end": (parse_dt(re_).date().isoformat()
                                            if parse_dt(re_) else ""),
                            }

    pg = pd.DataFrame(rows)
    log(f"parse: {n_files} box scores ({n_missing} cached-missing) -> "
        f"{len(pg)} player-game rows, {pg.person_code.nunique() if len(pg) else 0} persons")
    pg.to_csv(PG_PATH, index=False, compression="gzip")
    pd.DataFrame(list(regs.values())).to_csv(REG_PATH, index=False, compression="gzip")
    log(f"parse: wrote {PG_PATH} and {REG_PATH} ({len(regs)} registrations)")
    return pg


# --------------------------------------------------------------------------
# stage 2: match Euroleague persons to drafted pids
# --------------------------------------------------------------------------
def coverage_report():
    """Per competition-season: games played vs box scores cached.  Written to
    coverage.csv so a features.csv built mid-pull is never mistaken for final."""
    rows = []
    for comp in ("E", "U", "J"):
        gdir = os.path.join(RAW, "games", comp)
        if not os.path.isdir(gdir):
            continue
        for fn in sorted(os.listdir(gdir)):
            if not fn.endswith(".json.gz"):
                continue
            season = fn[:-8]
            games = read_gz(os.path.join(gdir, fn)).get("data", [])
            played = [g for g in games if g.get("played")]
            sdir = os.path.join(RAW, "stats", comp, season)
            have = len([f for f in os.listdir(sdir)
                        if f.endswith(".json.gz")]) if os.path.isdir(sdir) else 0
            dates = [parse_dt(g.get("utcDate")) or parse_dt(g.get("date"))
                     for g in played]
            dates = [d for d in dates if d]
            rows.append({
                "comp": comp, "season": season,
                "season_year": (played[0].get("season") or {}).get("year") if played else "",
                "games_played": len(played), "box_scores_cached": have,
                "complete": int(have >= len(played)),
                "first_game": min(dates).date().isoformat() if dates else "",
                "last_game": max(dates).date().isoformat() if dates else "",
            })
    c = pd.DataFrame(rows)
    c.to_csv(os.path.join(HERE, "coverage.csv"), index=False)
    inc = c[c.complete == 0]
    log(f"coverage: {int(c.complete.sum())}/{len(c)} competition-seasons complete, "
        f"{int(c.box_scores_cached.sum())}/{int(c.games_played.sum())} box scores cached")
    if len(inc):
        log(f"coverage: WARNING - {len(inc)} season(s) incomplete "
            f"({', '.join(inc.comp + ' ' + inc.season)[:200]}...); "
            f"features built now are PARTIAL - rerun build.py when pull.py finishes")
    return c


def match(pg=None):
    if pg is None:
        pg = pd.read_csv(PG_PATH, low_memory=False)
    ident = pd.read_csv(IDENTITY)
    wiki = pd.read_csv(WIKI_AGE)[["pid", "birth_date"]].rename(
        columns={"birth_date": "wiki_birth"})
    ident = ident.merge(wiki, on="pid", how="left")
    ident["key"] = ident.player_name.map(name_key)

    # one row per API person
    pg = pg[pg.game_dt.astype(str) != ""].copy()
    pg["dt"] = pd.to_datetime(pg.game_dt, errors="coerce")
    persons = []
    for code, grp in pg.groupby("person_code"):
        nm = Counter(grp.name.dropna()).most_common(1)[0][0]
        bd = Counter([b for b in grp.birth_date.dropna() if str(b) != ""]).most_common(1)
        persons.append({
            "person_code": code,
            "name": nm,
            "api_birth": bd[0][0] if bd else "",
            "first_game": grp.dt.min(),
            "last_game": grp.dt.max(),
            "first_season_year": int(grp.season_year.min()) if grp.season_year.notna().any() else np.nan,
            "comps": "".join(sorted(grp.comp.unique())),
            "games": len(grp),
        })
    persons = pd.DataFrame(persons)
    persons["key"] = persons.name.map(name_key)
    log(f"match: {len(persons)} API persons, {len(ident)} drafted players")

    by_key = defaultdict(list)
    for r in ident.itertuples():
        by_key[r.key].append(r)

    matches, unmatched = [], []
    for p in persons.itertuples():
        cands = by_key.get(p.key, [])
        if not cands:
            continue
        api_b = parse_dt(p.api_birth) if p.api_birth else None
        ok, rejected = [], []
        for c in cands:
            # (a) draft year plausibility: a game season must precede the draft
            if not np.isnan(p.first_season_year) and p.first_season_year > c.draft_year:
                rejected.append((c, "draft_year_before_first_season"))
                continue
            # (b) birthdate agreement where both sides know it
            wb = parse_dt(c.wiki_birth) if isinstance(c.wiki_birth, str) else None
            day_mismatch = 0
            if wb is not None and api_b is not None:
                dd = abs((wb - api_b).days)
                if dd > 1:
                    if wb.year == api_b.year:
                        # Same birth year, different day: the API carries the
                        # occasional data-entry error (e.g. a month typo).  The
                        # year still separates namesakes, so keep the match and
                        # flag it rather than silently dropping a real player.
                        day_mismatch = 1
                    else:
                        rejected.append((c, "birthdate_conflict"))
                        continue
            elif api_b is not None:
                # No verified birthdate on our side -> fall back to an age
                # window.  A real drafted PICK is never old (the 947 verified
                # draftees span 18.5-24.8), so a namesake veteran is rejected;
                # rows with no pick are NBA-entry-year rows (undrafted players,
                # late European arrivals) and can legitimately be any age.
                age = c.draft_year - api_b.year
                drafted = not (isinstance(c.actual_pick, float)
                               and np.isnan(c.actual_pick))
                lo, hi = (16, 27) if drafted else (16, 40)
                if not (lo <= age <= hi):
                    rejected.append((c, "age_implausible_pick"
                                     if drafted else "age_implausible_entry"))
                    continue
            ok.append((c, day_mismatch))
        if len(ok) == 1:
            c, day_mismatch = ok[0]
            matches.append({
                "pid": c.pid, "person_code": p.person_code,
                "api_name": p.name, "identity_name": c.player_name,
                "draft_year": c.draft_year, "api_birth": p.api_birth,
                "wiki_birth": c.wiki_birth if isinstance(c.wiki_birth, str) else "",
                "comps": p.comps, "games_all": p.games,
                "first_game": p.first_game.date().isoformat(),
                "last_game": p.last_game.date().isoformat(),
                "birth_day_mismatch": day_mismatch,
            })
        elif len(ok) > 1:
            unmatched.append({
                "person_code": p.person_code, "api_name": p.name,
                "api_birth": p.api_birth, "comps": p.comps, "games_all": p.games,
                "first_game": p.first_game.date().isoformat(),
                "reason": "ambiguous_multiple_pids",
                "detail": "|".join(f"{c.pid}:{c.draft_year}" for c, _ in ok),
            })
        else:
            unmatched.append({
                "person_code": p.person_code, "api_name": p.name,
                "api_birth": p.api_birth, "comps": p.comps, "games_all": p.games,
                "first_game": p.first_game.date().isoformat(),
                "reason": ";".join(sorted({r for _, r in rejected})),
                "detail": "|".join(f"{c.pid}:{c.draft_year}" for c, _ in rejected),
            })

    m = pd.DataFrame(matches)
    # one pid may legitimately own several person codes (E/U vs J use different
    # code spaces); flag any pid whose codes disagree on birthdate.
    if len(m):
        conflict = []
        for pid, grp in m.groupby("pid"):
            bs = {b for b in grp.api_birth if b}
            if len(bs) > 1:
                conflict.append(pid)
                for r in grp.itertuples():
                    unmatched.append({
                        "person_code": r.person_code, "api_name": r.api_name,
                        "api_birth": r.api_birth, "comps": r.comps,
                        "games_all": r.games_all, "first_game": r.first_game,
                        "reason": "same_pid_conflicting_birthdates",
                        "detail": f"{pid}:{'|'.join(sorted(bs))}",
                    })
        if conflict:
            log(f"match: {len(conflict)} pids have person codes with conflicting "
                f"birthdates -> those person codes dropped")
            m = m[~m.pid.isin(conflict)]

    u = pd.DataFrame(unmatched)
    m.to_csv(MATCH_PATH, index=False)
    u.to_csv(UNMATCHED_PATH, index=False)
    n_dm = int(m.birth_day_mismatch.sum()) if len(m) else 0
    log(f"match: {len(m)} person->pid matches covering {m.pid.nunique() if len(m) else 0} "
        f"pids; {len(u)} rows in unmatched.csv; {n_dm} matched on birth year with "
        f"a day-level mismatch (API data errors, flagged in matches.csv)")
    if len(u):
        log("match: unmatched reasons -> " + json.dumps(
            u.reason.value_counts().to_dict()))
    return m


# --------------------------------------------------------------------------
# stage 3: pre-draft features
# --------------------------------------------------------------------------
PER40 = [("pts", "pts40"), ("oreb", "oreb40"), ("dreb", "dreb40"),
         ("ast", "ast40"), ("stl", "stl40"), ("blk", "blk40"),
         ("tov", "tov40"), ("pf", "pf40"), ("pir", "pir40")]


def rate_block(g, pm_ok_mask=None):
    """Aggregate one set of player-games into rate stats.  `g` must already be
    filtered to a single competition and to pre-draft games."""
    out = {}
    played = g[g["min"] > 0]
    out["games"] = int(len(played))
    out["dnp"] = int((g["min"] <= 0).sum())
    rel = played[played["sf_ok"] == 1] if "sf_ok" in played.columns else played
    out["start_games"] = int(len(rel))
    out["starts"] = int(rel["start"].sum()) if len(rel) else np.nan
    out["start_rate"] = safe_div(rel["start"].sum(), len(rel)) if len(rel) else np.nan
    mins = float(played["min"].sum())
    out["min"] = round(mins, 1)
    # minutes share: over every game he was in the box score (DNPs included)
    out["min_share"] = safe_div(g["min"].sum(), g["team_min"].sum())

    if mins <= 0:
        for _, k in PER40:
            out[k] = np.nan
        for k in ("ts", "efg", "3par", "ftr", "ftpct", "3ppct", "2ppct",
                  "usage", "pm40"):
            out[k] = np.nan
        return out

    s = played.sum(numeric_only=True)
    for col, k in PER40:
        out[k] = s[col] * 40.0 / mins
    fga, fta, ftm = s["fga"], s["fta"], s["ftm"]
    out["ts"] = safe_div(s["pts"], 2.0 * (fga + 0.44 * fta))
    out["efg"] = safe_div(s["fgm"] + 0.5 * s["fg3m"], fga)
    out["3par"] = safe_div(s["fg3a"], fga)
    out["ftr"] = safe_div(fta, fga)
    out["ftpct"] = safe_div(ftm, fta)
    out["3ppct"] = safe_div(s["fg3m"], s["fg3a"])
    out["2ppct"] = safe_div(s["fg2m"], s["fg2a"])
    # usage: share of team possessions used while on the floor
    team_poss = s["team_fga"] + 0.44 * s["team_fta"] + s["team_tov"]
    out["usage"] = safe_div(
        100.0 * (fga + 0.44 * fta + s["tov"]) * (s["team_min"] / 5.0),
        mins * team_poss)
    # plus/minus only where the season actually carries it
    pmg = played[played["pm_ok"] == 1] if "pm_ok" in played.columns else played.iloc[0:0]
    pm_min = float(pmg["min"].sum())
    out["pm40"] = (pmg["pm"].sum() * 40.0 / pm_min) if pm_min > 0 else np.nan
    return out


def features(m=None):
    pg = pd.read_csv(PG_PATH, low_memory=False)
    regs = pd.read_csv(REG_PATH, low_memory=False)
    if m is None:
        m = pd.read_csv(MATCH_PATH)
    ident = pd.read_csv(IDENTITY)
    wiki = pd.read_csv(WIKI_AGE)[["pid", "birth_date"]]

    pg = pg[pg.game_dt.astype(str) != ""].copy()
    pg["dt"] = pd.to_datetime(pg.game_dt, errors="coerce")
    pg = pg[pg.dt.notna()]

    # plusMinus is only recorded for some games (essentially none before the
    # mid-2000s, and a handful of stray early games).  Flag it PER GAME - a
    # game carries plus/minus iff some player in it has a non-zero value - so
    # a player in a game without the data gets an empty pm40, never a fake 0.
    pm_games = (pg.groupby(["comp", "season", "game_code"])["pm"]
                  .apply(lambda s: int((s != 0).any())).rename("pm_ok").reset_index())
    pg = pg.merge(pm_games, on=["comp", "season", "game_code"], how="left")

    # The startFive flag is not recorded in every game (some old box scores
    # have nobody flagged, a few have >5).  Trust it only where exactly five
    # players on that side are flagged, so "starts" is never a fabricated 0.
    sf = (pg.groupby(["comp", "season", "game_code", "team"])["start"]
            .transform("sum"))
    pg["sf_ok"] = (sf == 5).astype(int)

    # first game date of every competition-season, for mid-season registrations
    season_start = pg.groupby(["comp", "season"])["dt"].min().to_dict()

    # ANGT field mean age per tournament
    j = pg[pg.comp == "J"]
    field_mean, field_drop = {}, 0
    if len(j):
        for season, grp in j.groupby("season"):
            t0 = grp.dt.min()
            ages = []
            for code, g2 in grp.groupby("person_code"):
                b = [x for x in g2.birth_date.dropna()
                     if str(x) not in ("", "nan")]
                if not b:
                    continue
                bd = parse_dt(b[0])
                if not bd:
                    continue
                a = (t0 - bd).days / 365.25
                if ANGT_FIELD_BAND[0] <= a <= ANGT_FIELD_BAND[1]:
                    ages.append(a)
                else:
                    field_drop += 1
            # need a real field to compare against
            if len(ages) >= 10:
                field_mean[season] = float(np.mean(ages))
        log(f"features: ANGT field means for {len(field_mean)}/{j.season.nunique()} "
            f"tournaments ({field_drop} persons dropped for implausible birthdates)")

    codes_by_pid = defaultdict(list)
    for r in m.itertuples():
        codes_by_pid[r.pid].append(r.person_code)

    dy = dict(zip(ident.pid, ident.draft_year))
    wb = {r.pid: r.birth_date for r in wiki.itertuples()}
    pg_by_code = {c: g for c, g in pg.groupby("person_code")}
    regs_by_code = {c: g for c, g in regs.groupby("person_code")}

    rows, prov = [], []
    for pid, codes in codes_by_pid.items():
        draft_year = dy.get(pid)
        if draft_year is None:
            continue
        cut = cutoff_for(draft_year)
        if cut is None:
            continue
        g = pd.concat([pg_by_code[c] for c in codes if c in pg_by_code],
                      ignore_index=True) if codes else pd.DataFrame()
        if not len(g):
            continue
        g = g[g.dt < cut]
        if not len(g):
            continue

        # birth date: prefer the verified wiki value, fall back to the API
        bsrc = 1 if isinstance(wb.get(pid), str) and wb.get(pid) else 0
        bd = parse_dt(wb.get(pid)) if bsrc else None
        if bd is None:
            # Fall back to the API, preferring the value recorded in senior
            # (E/U) box scores: the U18 competition carries placeholder
            # birthdates, the senior competitions do not.
            for subset in (g[g.comp.isin(["E", "U"])], g):
                b = [x for x in subset.birth_date.dropna()
                     if str(x) not in ("", "nan")]
                if b:
                    bd = parse_dt(Counter(b).most_common(1)[0][0])
                    break

        row = {"pid": pid, "birth_src_wiki": bsrc,
               "cutoff_inferred": 1 if int(draft_year) == 2026 else 0}
        # listed height as recorded in his LAST pre-draft box score (teenagers
        # grow, so the latest pre-draft observation is the right one)
        h = g.sort_values("dt")["height"].dropna()
        h = h[(h >= 150) & (h <= 240)]
        row["bio_height_cm"] = float(h.iloc[-1]) if len(h) else np.nan

        # ---- el2_ / eu2_ : senior club competitions, never pooled ----
        for comp, pref in COMP_PREFIX.items():
            gc = g[g.comp == comp]
            blk = rate_block(gc)
            for k, v in blk.items():
                row[f"{pref}_{k}"] = v
            if len(gc):
                yrs = sorted(gc.season_year.dropna().unique())
                row[f"{pref}_seasons"] = len(yrs)
                if bd is not None:
                    row[f"{pref}_age_first"] = guard_age(
                        (gc.dt.min() - bd).days / 365.25, SENIOR_BAND)
                    row[f"{pref}_age_last"] = guard_age(
                        (gc.dt.max() - bd).days / 365.25, SENIOR_BAND)
                # last pre-draft season
                if yrs:
                    ls = rate_block(gc[gc.season_year == yrs[-1]])
                    for k, v in ls.items():
                        row[f"{pref}_ls_{k}"] = v
                    fs = rate_block(gc[gc.season_year == yrs[0]])
                    for k in ("pts40", "pir40"):
                        row[f"{pref}_trend_{k}"] = (
                            ls[k] - fs[k]
                            if (ls.get(k) is not None and fs.get(k) is not None
                                and not pd.isna(ls[k]) and not pd.isna(fs[k])
                                and len(yrs) > 1)
                            else np.nan)
            else:
                row[f"{pref}_seasons"] = 0

        # ---- yng_ : senior minutes accrued before the 20th birthday ----
        sen = g[g.comp.isin(["E", "U"])]
        if bd is not None and not len(sen):
            # Senior coverage is complete for these seasons, so "no senior
            # games" is a true zero, not missing data.  Age-at-first-senior and
            # the age-18/19 shares stay empty: there is no senior game to date.
            row["yng_min_e"] = row["yng_min_u"] = row["yng_min_senior"] = 0.0
            row["yng_min_age18"] = row["yng_min_age19"] = 0.0
            row["yng_games_u20"] = 0
        elif bd is not None and len(sen):
            sen = sen.copy()
            sen["age"] = (sen.dt - bd).dt.days / 365.25
            u20 = sen[sen.age < 20]
            row["yng_min_e"] = round(float(u20[u20.comp == "E"]["min"].sum()), 1)
            row["yng_min_u"] = round(float(u20[u20.comp == "U"]["min"].sum()), 1)
            row["yng_min_senior"] = round(row["yng_min_e"] + row["yng_min_u"], 1)
            row["yng_games_u20"] = int((u20["min"] > 0).sum())
            row["yng_age_first_senior"] = guard_age(float(sen.age.min()), SENIOR_BAND)
            for a in (18, 19):
                w = sen[(sen.age >= a) & (sen.age < a + 1)]
                row[f"yng_min_share_age{a}"] = safe_div(w["min"].sum(), w["team_min"].sum())
                row[f"yng_min_age{a}"] = round(float(w["min"].sum()), 1)
        elif len(sen):
            row["yng_min_e"] = row["yng_min_u"] = row["yng_min_senior"] = np.nan

        # ---- angt_ : U18 Adidas Next Generation Tournament, J only ----
        gj = g[g.comp == "J"]
        row["angt_has"] = 1 if len(gj) else 0
        if len(gj):
            blk = rate_block(gj)
            for k in ("games", "starts", "start_rate", "min", "min_share",
                      "pts40", "oreb40", "dreb40", "ast40", "stl40", "blk40",
                      "tov40", "pf40", "pir40", "ts", "efg", "3par", "ftr",
                      "ftpct", "3ppct", "2ppct", "usage"):
                row[f"angt_{k}"] = blk[k]
            row["angt_tournaments"] = int(gj.season.nunique())
            if bd is not None:
                row["angt_age_first"] = guard_age(
                    (gj.dt.min() - bd).days / 365.25, ANGT_PLAYER_BAND)
                rels, wts = [], []
                for season, grp in gj.groupby("season"):
                    fm = field_mean.get(season)
                    if fm is None:
                        continue
                    a = (grp.dt.min() - bd).days / 365.25
                    if not (ANGT_PLAYER_BAND[0] <= a <= ANGT_PLAYER_BAND[1]):
                        continue
                    rels.append(a - fm)
                    wts.append(len(grp))
                row["angt_rel_age"] = (float(np.average(rels, weights=wts))
                                       if rels else np.nan)
        else:
            row["angt_tournaments"] = 0

        # ---- club_ : clubs and mid-season registration moves ----
        rr = pd.concat([regs_by_code[c] for c in codes if c in regs_by_code],
                       ignore_index=True) if codes else pd.DataFrame()
        n_mid = 0
        if len(rr):
            rr = rr[rr.reg_start.astype(str) != ""].copy()
            rr["rs"] = pd.to_datetime(rr.reg_start, errors="coerce")
            rr = rr[rr.rs.notna() & (rr.rs < cut)]
            for r2 in rr.itertuples():
                s0 = season_start.get((r2.comp, r2.season))
                if s0 is not None and (r2.rs - s0).days > 30:
                    n_mid += 1
        row["club_n_senior"] = int(g[g.comp.isin(["E", "U"])].team.nunique())
        row["club_n_all"] = int(g.team.nunique())
        row["club_midseason_moves"] = int(n_mid)
        row["club_registrations"] = int(len(rr)) if len(rr) else 0

        # ---- league tier scalar for the highest pre-draft venue ----
        present = [c for c in ("E", "U", "J") if (g.comp == c).any()]
        tiers = [TIER[c] for c in present]
        row["tier_best"] = max(tiers) if tiers else np.nan
        row["tier_e"] = TIER["E"] if "E" in present else np.nan
        row["tier_u"] = TIER["U"] if "U" in present else np.nan
        row["intl_any"] = 1

        rows.append(row)
        prov.append({
            "pid": pid,
            "person_codes": "|".join(sorted(codes)),
            "competitions": "".join(sorted(present)),
            "seasons": "|".join(sorted(g.season.unique())),
            "n_games_predraft": int(len(g)),
            "first_game_used": g.dt.min().date().isoformat(),
            "last_game_used": g.dt.max().date().isoformat(),
            "cutoff_utc": cut.isoformat(),
            "draft_year": int(draft_year),
        })

    f = pd.DataFrame(rows)
    # pid first, then numeric columns only
    cols = ["pid"] + [c for c in f.columns if c != "pid"]
    f = f[cols]
    for c in f.columns:
        if c != "pid":
            f[c] = pd.to_numeric(f[c], errors="coerce").round(6)
    f = f.sort_values("pid")
    f.to_csv(FEAT_PATH, index=False)
    pd.DataFrame(prov).sort_values("pid").to_csv(PROV_PATH, index=False)
    log(f"features: {len(f)} rows x {len(f.columns)-1} numeric columns -> {FEAT_PATH}")

    # coverage by draft-year band
    dyr = f.pid.map(dy)
    band = pd.cut(dyr, [1999, 2007, 2018, 2026],
                  labels=["2000-07", "2008-18", "2019-25"])
    log("features: coverage by band -> " + json.dumps(
        band.value_counts().sort_index().to_dict()))
    return f


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("all", "parse", "coverage"):
        coverage_report()
    if stage in ("all", "parse"):
        pgd = parse()
    if stage in ("all", "match"):
        md = match(pgd if stage == "all" else None)
    if stage in ("all", "features"):
        features(md if stage == "all" else None)
