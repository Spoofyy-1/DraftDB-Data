#!/usr/bin/env python3
"""
Build the age-relative FIBA youth feature block from the cached crawl.

Reads raw/parsed/*.json (written by crawl.py) and raw/parsed/hoop_summit.json
(written by hoop_summit.py) and writes, in the collector directory:

  player_tournaments.csv  one row per matched pid x tournament (numeric only,
                          plus the tournament id / level / dates), including
                          the tournament field's mean and SD for age and for
                          every per-40 stat
  field_tournaments.csv   one row per tournament: id, level, dates, field size
  features.csv            one row per pid in the identity file, fy_* features
  unmatched.csv           FIBA youth players that could not be matched, and
                          ambiguous matches, with the reason
  provenance.csv          pid -> fiba person id, tournaments used, source URLs

Nothing outside this directory is written.

Usage: python3 build.py
"""
import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

from fibalib import HERE, PARSED, log, norm_name
from competitions import COMPETITIONS, LEVEL_LABEL, level_of

IDENTITY = ("/Users/kennakao/Downloads/nba_redraft_handoff/"
            "identity_KEEP_SEPARATE/tabular_names.csv")
AGEFILE = "/Users/kennakao/nba/datarebuild/age_verified_wiki.csv"

# Draft-night cutoffs from COLLECTOR_RULES.md (22:00 UTC on this date).
CUTOFF = {
    2000: "2000-06-28", 2001: "2001-06-27", 2002: "2002-06-26",
    2003: "2003-06-26", 2004: "2004-06-24", 2005: "2005-06-28",
    2006: "2006-06-28", 2007: "2007-06-28", 2008: "2008-06-26",
    2009: "2009-06-25", 2010: "2010-06-24", 2011: "2011-06-23",
    2012: "2012-06-28", 2013: "2013-06-27", 2014: "2014-06-26",
    2015: "2015-06-25", 2016: "2016-06-23", 2017: "2017-06-22",
    2018: "2018-06-21", 2019: "2019-06-20", 2020: "2020-11-18",
    2021: "2021-07-29", 2022: "2022-06-23", 2023: "2023-06-22",
    2024: "2024-06-26", 2025: "2025-06-25",
}

# Field-qualification rule for the z-score reference distribution.
MIN_GAMES = 3
MIN_MINUTES = 40.0
AGE_LO, AGE_HI = 14.0, 20.0        # plausible age at a U15-U19 tournament
SMALL_FIELD = 6                    # below this many teams a "continental" title is demoted

PER40 = ["pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pir",
         "usage"]
RATES = ["ts", "efg", "tpar", "ftr", "ftpct"]


def dparse(s):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def years_between(d0, d1):
    return (d1 - d0).days / 365.2425


def mean_sd(xs):
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        return None, None, 0
    mu = sum(xs) / n
    if n < 2:
        return mu, None, n
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return mu, math.sqrt(var), n


def z(x, mu, sd):
    if x is None or mu is None or sd is None or sd <= 1e-9:
        return None
    return (x - mu) / sd


# --------------------------------------------------------------- load ------
def load_tournaments():
    """Return (tournaments, rows) parsed from the crawl cache."""
    tours, rows = {}, []
    for path in sorted(glob.glob(os.path.join(PARSED, "*_*.json"))):
        base = os.path.basename(path)
        if not re.match(r"^\d+_\d+\.json$", base):
            continue
        with open(path) as fh:
            rec = json.load(fh)
        if rec.get("skip") or not rec.get("meta"):
            continue
        slug = rec["comp_slug"]
        if slug not in COMPETITIONS:
            continue
        tier, scope, age = COMPETITIONS[slug]
        meta = rec["meta"]
        tid = "%s_%s" % (rec["comp_id"], rec["event_id"])
        start, end = dparse(meta.get("start")), dparse(meta.get("end"))
        if end is None:
            end = start
        n_teams = len([t for t in rec.get("teams", []) if isinstance(t, dict)])
        lvl = level_of(tier, scope, age)
        # A "continental championship" with fewer than SMALL_FIELD teams (the
        # Oceania events are usually AUS v NZL) is not the same test as a
        # 16-team EuroBasket, so it drops one rung.  Rule-based, no judgement
        # about individual players.
        if scope == "continental" and tier == "A" and 0 < n_teams < SMALL_FIELD:
            lvl = max(1, lvl - 1)
        tours[tid] = {
            "tid": tid, "comp_id": rec["comp_id"], "comp_slug": slug,
            "event_id": rec["event_id"], "season": meta.get("season"),
            "start": start, "end": end, "n_teams": n_teams,
            "level": lvl, "tier": tier, "scope": scope,
            "age_group": age, "age_category": meta.get("ageCategory"),
            "zone": meta.get("fibaZone"),
            "url": "https://www.fiba.basketball/en/history/%s/%s"
                   % (slug, rec["event_id"]),
        }

        # team id -> slug (for players whose team came through as a
        # back-reference on the /players page)
        id2slug = {t["teamId"]: t["slug"] for t in rec.get("teams", [])
                   if isinstance(t, dict) and t.get("teamId")}
        stat_by_pid = {}
        team_by_pid = {}
        for tslug, plist in rec.get("team_stats", {}).items():
            for s in plist:
                stat_by_pid[s["player_id"]] = s
                team_by_pid[s["player_id"]] = tslug
        finish = rec.get("team_finish", {})

        for p in rec.get("players", []):
            pid_f = p["player_id"]
            s = stat_by_pid.get(pid_f)
            tslug = p.get("team_slug") or team_by_pid.get(pid_f) \
                or id2slug.get(p.get("team_id"))
            row = {"tid": tid, "fiba_id": pid_f,
                   "first": p.get("first_name") or "",
                   "last": p.get("last_name") or "",
                   "nat": p.get("nationality"), "dob": dparse(p.get("dob")),
                   "team": tslug, "finish": finish.get(tslug)}
            row.update(_stat_block(s))
            rows.append(row)
        # players present in team stats but absent from the /players listing
        listed = {p["player_id"] for p in rec.get("players", [])}
        for tslug, plist in rec.get("team_stats", {}).items():
            for s in plist:
                if s["player_id"] in listed:
                    continue
                row = {"tid": tid, "fiba_id": s["player_id"],
                       "first": s.get("first_name") or "",
                       "last": s.get("last_name") or "", "nat": None,
                       "dob": None, "team": tslug,
                       "finish": finish.get(tslug)}
                row.update(_stat_block(s))
                rows.append(row)
    return tours, rows


def _stat_block(s):
    out = {"g": None, "min": None}
    for k in PER40 + RATES:
        out[k] = None
    if not s:
        return out
    g = s.get("totalGamesPlayed")
    secs = s.get("totalPlayTimeInSeconds")
    mins = (secs / 60.0) if secs else None
    out["g"] = g
    out["min"] = mins
    fga = s.get("totalFieldGoalsAttempted")
    fgm = s.get("totalFieldGoalsMade")
    tpa = s.get("totalThreePointsAttempted")
    tpm = s.get("totalThreePointsMade")
    fta = s.get("totalFreeThrowsAttempted")
    ftm = s.get("totalFreeThrowsMade")
    pts = s.get("totalPoints")
    tov = s.get("totalTurnovers")
    if mins and mins > 0:
        f = 40.0 / mins
        out["pts"] = (pts or 0) * f
        out["reb"] = (s.get("totalRebounds") or 0) * f
        out["oreb"] = (s.get("totalReboundsOffensive") or 0) * f
        out["dreb"] = (s.get("totalReboundsDefensive") or 0) * f
        out["ast"] = (s.get("totalAssists") or 0) * f
        out["stl"] = (s.get("totalSteals") or 0) * f
        out["blk"] = (s.get("totalBlocks") or 0) * f
        out["tov"] = (tov or 0) * f
        out["pir"] = (s.get("totalEfficiency") or 0) * f
        out["usage"] = ((fga or 0) + 0.44 * (fta or 0) + (tov or 0)) * f
    if fga and fga > 0:
        out["efg"] = ((fgm or 0) + 0.5 * (tpm or 0)) / fga
        out["tpar"] = (tpa or 0) / fga
        out["ftr"] = (fta or 0) / fga
    den = 2.0 * ((fga or 0) + 0.44 * (fta or 0))
    if den > 0 and pts is not None:
        out["ts"] = pts / den
    if fta and fta > 0:
        out["ftpct"] = (ftm or 0) / fta
    return out


# ------------------------------------------------------------ identity -----
def load_identity():
    ident = []
    with open(IDENTITY, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                dy = int(float(r["draft_year"]))
            except (TypeError, ValueError):
                continue
            ident.append({"pid": r["pid"], "draft_year": dy,
                          "name": r["player_name"],
                          "norm": norm_name(r["player_name"])})
    by_norm = defaultdict(list)
    for r in ident:
        by_norm[r["norm"]].append(r)
    birth = {}
    with open(AGEFILE, newline="") as fh:
        for r in csv.DictReader(fh):
            d = dparse(r.get("birth_date"))
            if d:
                birth[r["pid"]] = d
    return ident, by_norm, birth


# ------------------------------------------------------------- matching ----
def match(rows, tours, by_norm, birth, ident=None):
    """Match FIBA persons to pids.  Returns (fiba_id -> pid, unmatched log)."""
    persons = defaultdict(lambda: {"names": set(), "dobs": set(),
                                   "tids": set(), "nats": set()})
    for r in rows:
        p = persons[r["fiba_id"]]
        p["names"].add((r["first"], r["last"]))
        if r["dob"]:
            p["dobs"].add(r["dob"])
        p["tids"].add(r["tid"])
        if r["nat"]:
            p["nats"].add(r["nat"])

    out, log_rows = {}, []
    for fid, p in persons.items():
        keys = []
        for (fn, ln) in sorted(p["names"]):     # FIBA can spell a player two
            for k in (norm_name("%s %s" % (fn, ln)),   # ways across editions
                      norm_name("%s %s" % (ln, fn))):
                if k and k not in keys:
                    keys.append(k)
        dob = sorted(p["dobs"])[0] if p["dobs"] else None
        tyears = sorted({tours[t]["season"] for t in p["tids"]
                         if t in tours and tours[t]["season"]})
        if not tyears:
            continue
        cands, key_used = [], None
        for k in keys:
            c = [x for x in by_norm.get(k, [])]
            if c:
                cands, key_used = c, k
                break
        if not cands:
            continue                                    # not a drafted player
        ok = []
        for c in cands:
            dy = c["draft_year"]
            if min(tyears) > dy:
                continue                                # all post-draft
            if dob is not None:
                ages = [years_between(dob, tours[t]["start"] or tours[t]["end"])
                        for t in p["tids"]
                        if t in tours and (tours[t]["start"] or tours[t]["end"])]
                ages = [a for a in ages if a is not None]
                if ages and not any(AGE_LO <= a <= AGE_HI for a in ages):
                    continue
                bd = birth.get(c["pid"])
                if bd is not None:
                    if bd.year != dob.year:
                        continue                        # birth year conflict
                elif dy - dob.year < 16:
                    continue                            # impossible draft age
            else:
                if not (0 <= dy - min(tyears) <= 8):
                    continue
            ok.append(c)
        if len(ok) == 1:
            out[fid] = ok[0]["pid"]
        elif len(ok) > 1:
            log_rows.append({"fiba_id": fid, "reason": "ambiguous",
                             "n_candidates": len(ok), "name_key": key_used,
                             "dob_year": dob.year if dob else "",
                             "tournament_years": ";".join(map(str, tyears)),
                             "candidate_pids": ";".join(c["pid"] for c in ok)})
        else:
            log_rows.append({"fiba_id": fid, "reason": "name hit, filters rejected",
                             "n_candidates": 0, "name_key": key_used,
                             "dob_year": dob.year if dob else "",
                             "tournament_years": ";".join(map(str, tyears)),
                             "candidate_pids": ";".join(c["pid"] for c in cands)})

    # ---- pass 2: exact verified birthdate + surname, for FIBA persons the
    # name key missed entirely (transliterations and short forms such as
    # Juan/Juancho).  Conservative: an exact date-of-birth agreement with
    # age_verified_wiki.csv AND a shared surname token AND the same
    # draft-year/age plausibility as pass 1.  Never a fuzzy name comparison.
    if ident:
        by_bd = defaultdict(list)
        for c in ident:
            bd = birth.get(c["pid"])
            if bd:
                by_bd[bd.date()].append(c)
        taken = set(out.values())
        for fid, p in persons.items():
            if fid in out or not p["dobs"]:
                continue
            dob = sorted(p["dobs"])[0]
            cands = [c for c in by_bd.get(dob.date(), [])
                     if c["pid"] not in taken]
            if not cands:
                continue
            surname = set()
            for (_fn, ln) in p["names"]:
                surname |= set(norm_name(ln).split())
            tyears = sorted({tours[t]["season"] for t in p["tids"]
                             if t in tours and tours[t]["season"]})
            if not tyears:
                continue
            ok = []
            for c in cands:
                if min(tyears) > c["draft_year"]:
                    continue
                toks = set(c["norm"].split())
                if not (surname & toks):
                    continue
                ages = [years_between(dob, tours[t]["start"] or tours[t]["end"])
                        for t in p["tids"]
                        if t in tours and (tours[t]["start"] or tours[t]["end"])]
                if ages and not any(AGE_LO <= a <= AGE_HI for a in ages):
                    continue
                ok.append(c)
            if len(ok) == 1:
                out[fid] = ok[0]["pid"]
                taken.add(ok[0]["pid"])
            elif len(ok) > 1:
                log_rows.append({"fiba_id": fid,
                                 "reason": "pass2 dob+surname ambiguous",
                                 "n_candidates": len(ok), "name_key": "",
                                 "dob_year": dob.year,
                                 "tournament_years": ";".join(map(str, tyears)),
                                 "candidate_pids": ";".join(c["pid"] for c in ok)})

    # a pid claimed by two different FIBA persons -> drop both, log
    rev = defaultdict(list)
    for fid, pid in out.items():
        rev[pid].append(fid)
    for pid, fids in rev.items():
        if len(fids) > 1:
            for fid in fids:
                out.pop(fid, None)
                log_rows.append({"fiba_id": fid,
                                 "reason": "pid claimed by multiple fiba ids",
                                 "n_candidates": len(fids), "name_key": "",
                                 "dob_year": "", "tournament_years": "",
                                 "candidate_pids": pid})
    return out, log_rows


# ------------------------------------------------------------ main ---------
def main():
    tours, rows = load_tournaments()
    log("tournaments parsed: %d ; field rows: %d" % (len(tours), len(rows)))
    if not tours:
        log("nothing parsed yet -- run crawl.py first")
        return

    # ---- tournament field distributions -----------------------------------
    by_tid = defaultdict(list)
    for r in rows:
        by_tid[r["tid"]].append(r)
    field = {}
    for tid, rs in by_tid.items():
        t = tours[tid]
        ref = t["start"] or t["end"]
        ages = []
        for r in rs:
            a = years_between(r["dob"], ref) if (r["dob"] and ref) else None
            # implausible ages are DOB data errors -> dropped, not clamped
            if a is not None and not (AGE_LO - 1 <= a <= AGE_HI + 1):
                a = None
            r["age"] = a
            if a is not None:
                ages.append(a)
        qual = [r for r in rs
                if r["g"] and r["g"] >= MIN_GAMES
                and r["min"] and r["min"] >= MIN_MINUTES]
        f = {}
        f["age_mean"], f["age_sd"], f["age_n"] = mean_sd(ages)
        for k in PER40 + RATES:
            mu, sd, n = mean_sd([r[k] for r in qual])
            f[k + "_mean"], f[k + "_sd"] = mu, sd
        f["n_qual"] = len(qual)
        f["n_roster"] = len(rs)
        field[tid] = f

    ident0, by_norm, birth = load_identity()
    fid2pid, unmatched = match(rows, tours, by_norm, birth, ident0)
    log("matched fiba persons: %d ; unmatched/ambiguous logged: %d"
        % (len(fid2pid), len(unmatched)))

    # ---- per player-tournament table --------------------------------------
    pt = []
    for r in rows:
        pid = fid2pid.get(r["fiba_id"])
        if not pid:
            continue
        t = tours[r["tid"]]
        f = field[r["tid"]]
        rec = {"pid": pid, "fiba_id": r["fiba_id"], "tid": r["tid"],
               "comp_id": t["comp_id"], "event_id": t["event_id"],
               "level": t["level"], "age_group": t["age_group"],
               "scope": t["scope"], "division": t["tier"],
               "year": t["season"],
               "date_start": t["start"].date().isoformat() if t["start"] else "",
               "date_end": t["end"].date().isoformat() if t["end"] else "",
               "games": r["g"], "minutes": r["min"],
               "age_at_tournament": r["age"],
               "team_finish": r["finish"],
               "field_n_roster": f["n_roster"], "field_n_qual": f["n_qual"],
               "field_age_mean": f["age_mean"], "field_age_sd": f["age_sd"]}
        for k in PER40 + RATES:
            rec[k + "40" if k in PER40 else k] = r[k]
            rec["field_%s_mean" % k] = f[k + "_mean"]
            rec["field_%s_sd" % k] = f[k + "_sd"]
        pt.append(rec)
    log("player-tournament rows (matched): %d" % len(pt))

    # ---- hoop summit ------------------------------------------------------
    hs_path = os.path.join(PARSED, "hoop_summit.json")
    hs_world, hs_years_cov = {}, set()
    hs_meta = {}
    if os.path.exists(hs_path):
        with open(hs_path) as fh:
            hs = json.load(fh)
        hs_meta = {"url": hs["source_url"], "revid": hs["revid"],
                   "rev_ts": hs["rev_ts"]}
        for r in hs["rows"]:
            hs_years_cov.add(r["draft_year"])
            cands = by_norm.get(r["name_norm"], [])
            exact = [c for c in cands if c["draft_year"] == r["draft_year"]]
            if exact:
                pick = exact
            elif len(cands) == 1 and cands[0]["draft_year"] >= r["draft_year"]:
                pick = cands            # undrafted-then-signed identity rows
            else:
                pick = []
            for c in pick:
                pre = [y for y in r["nhs_years"] if y <= c["draft_year"]]
                if not pre:
                    continue
                cur = hs_world.get(c["pid"], 0)
                hs_world[c["pid"]] = max(cur, 1 if r["nhs_team"] == "World" else 0)
    hs_lo = min(hs_years_cov) if hs_years_cov else None
    hs_hi = max(hs_years_cov) if hs_years_cov else None

    # ---- features ---------------------------------------------------------
    ident, _, _ = load_identity()
    by_pid = defaultdict(list)
    for rec in pt:
        by_pid[rec["pid"]].append(rec)

    feats = {}
    used = defaultdict(list)
    no_cutoff = set()
    for c in ident:
        pid, dy = c["pid"], c["draft_year"]
        cut = dparse(CUTOFF.get(dy))
        if cut is None:
            # No documented draft-night cutoff for this class (the rules list
            # 2000-2025).  Without a cutoff nothing can be certified pre-draft,
            # so every column stays empty rather than guessing a date.
            feats[pid] = {"pid": pid}
            no_cutoff.add(dy)
            continue
        mine = []
        for rec in by_pid.get(pid, []):
            end = dparse(rec["date_end"]) or dparse(rec["date_start"])
            if end is None or end >= cut:
                continue                       # not knowable before draft night
            mine.append(rec)
        mine.sort(key=lambda r: (r["date_end"] or r["date_start"], r["tid"]))
        f = {"pid": pid}
        hw = hs_world.get(pid)
        if hs_lo is not None and hs_lo <= dy <= hs_hi:
            f["fy_hoop_summit_world"] = 1 if hw else 0
        else:
            f["fy_hoop_summit_world"] = ""
        if not mine:
            f["fy_has_youth"] = 0
            f["fy_n_tournaments"] = 0
            feats[pid] = f
            continue
        used[pid] = [r["tid"] for r in mine]
        last, first = mine[-1], mine[0]
        fl, ff = field[last["tid"]], field[first["tid"]]
        f["fy_has_youth"] = 1
        f["fy_n_tournaments"] = len(mine)
        f["fy_best_level"] = max(r["level"] for r in mine)

        def arel(r):
            fm = field[r["tid"]]["age_mean"]
            if r["age_at_tournament"] is None or fm is None:
                return None
            return r["age_at_tournament"] - fm
        f["fy_age_rel_last"] = arel(last)
        rels = [a for a in (arel(r) for r in mine) if a is not None]
        f["fy_age_rel_min"] = min(rels) if rels else None
        f["fy_underage_flag"] = (1 if any(a <= -1.0 for a in rels)
                                 else (0 if rels else None))

        f["fy_pts40_z_last"] = z(last["pts40"], fl["pts_mean"], fl["pts_sd"])
        f["fy_pir40_z_last"] = z(last["pir40"], fl["pir_mean"], fl["pir_sd"])
        f["fy_ts_z_last"] = z(last["ts"], fl["ts_mean"], fl["ts_sd"])
        f["fy_ast40_z_last"] = z(last["ast40"], fl["ast_mean"], fl["ast_sd"])
        sb = None
        if last["stl40"] is not None and last["blk40"] is not None:
            sb = last["stl40"] + last["blk40"]
        mu_sb, sd_sb, _ = mean_sd(
            [(r["stl"] + r["blk"]) for r in by_tid[last["tid"]]
             if r["stl"] is not None and r["blk"] is not None
             and r["g"] and r["g"] >= MIN_GAMES
             and r["min"] and r["min"] >= MIN_MINUTES])
        f["fy_stl_blk40_z_last"] = z(sb, mu_sb, sd_sb)
        f["fy_usage_proxy_z_last"] = z(last["usage40"], fl["usage_mean"],
                                       fl["usage_sd"])

        pz = [z(r["pts40"], field[r["tid"]]["pts_mean"],
                field[r["tid"]]["pts_sd"]) for r in mine]
        ez = [z(r["pir40"], field[r["tid"]]["pir_mean"],
                field[r["tid"]]["pir_sd"]) for r in mine]
        pzv = [x for x in pz if x is not None]
        ezv = [x for x in ez if x is not None]
        f["fy_best_pts40_z"] = max(pzv) if pzv else None
        f["fy_best_pir40_z"] = max(ezv) if ezv else None
        f["fy_z_trend"] = (ez[-1] - ez[0]) if (len(mine) > 1 and
                                               ez[-1] is not None and
                                               ez[0] is not None) else None
        f["fy_minutes_share_last"] = ((last["minutes"] / last["games"]) / 40.0
                                      if (last["minutes"] and last["games"])
                                      else None)
        f["fy_team_finish_last"] = last["team_finish"]
        feats[pid] = f

    # ---- write ------------------------------------------------------------
    _write_pt(pt)
    _write_tours(tours, field)
    cols = ["pid", "fy_has_youth", "fy_n_tournaments", "fy_best_level",
            "fy_age_rel_last", "fy_age_rel_min", "fy_underage_flag",
            "fy_pts40_z_last", "fy_pir40_z_last", "fy_ts_z_last",
            "fy_ast40_z_last", "fy_stl_blk40_z_last", "fy_usage_proxy_z_last",
            "fy_best_pts40_z", "fy_best_pir40_z", "fy_z_trend",
            "fy_minutes_share_last", "fy_team_finish_last",
            "fy_hoop_summit_world"]
    with open(os.path.join(HERE, "features.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in ident:
            f = feats.get(c["pid"], {"pid": c["pid"]})
            w.writerow([_fmt(f.get(k, "")) for k in cols])

    with open(os.path.join(HERE, "unmatched.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, ["fiba_id", "reason", "n_candidates",
                                "name_key", "dob_year", "tournament_years",
                                "candidate_pids"])
        w.writeheader()
        for r in unmatched:
            w.writerow(r)

    with open(os.path.join(HERE, "provenance.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pid", "source", "fiba_person_id", "n_tournaments_predraft",
                    "tournament_ids", "urls"])
        pid2fid = {}
        for fid, pid in fid2pid.items():
            pid2fid[pid] = fid
        for c in ident:
            pid = c["pid"]
            tids = used.get(pid, [])
            if tids:
                w.writerow([pid, "fiba.basketball", pid2fid.get(pid, ""),
                            len(tids), ";".join(tids),
                            ";".join(tours[t]["url"] for t in tids)])
        for pid, v in sorted(hs_world.items()):
            if v:
                w.writerow([pid, "wikipedia:Nike_Hoop_Summit",
                            hs_meta.get("revid", ""), "", "",
                            hs_meta.get("url", "")])

    nat_by_pid = {}
    for r in rows:
        pidx = fid2pid.get(r['fiba_id'])
        if pidx and r.get('nat'):
            nat_by_pid.setdefault(pidx, r['nat'])
    # ---- self-checks (fail loudly rather than shipping a leak) -----------
    dyof = {c["pid"]: c["draft_year"] for c in ident}
    leaks = 0
    for pid, tids in used.items():
        cut = dparse(CUTOFF[dyof[pid]])
        for tid in tids:
            e = tours[tid]["end"] or tours[tid]["start"]
            if e is None or e >= cut:
                leaks += 1
    log("self-check: post-cutoff tournaments used = %d (must be 0)" % leaks)
    npid = len({c["pid"] for c in ident})
    log("self-check: unique pids in features.csv = %d of %d rows"
        % (npid, len(ident)))

    if no_cutoff:
        log("draft years with no documented cutoff -> all columns empty: %s"
            % ", ".join(str(y) for y in sorted(no_cutoff)))
    _report(ident, feats, tours, pt, hs_meta, hs_lo, hs_hi, nat_by_pid)


def _fmt(v):
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        return "%.6g" % v
    return v


def _write_pt(pt):
    if not pt:
        return
    cols = ["pid", "fiba_id", "tid", "comp_id", "event_id", "level",
            "age_group", "scope", "division", "year", "date_start", "date_end",
            "games", "minutes", "age_at_tournament", "team_finish",
            "field_n_roster", "field_n_qual", "field_age_mean", "field_age_sd"]
    for k in PER40:
        cols += [k + "40", "field_%s_mean" % k, "field_%s_sd" % k]
    for k in RATES:
        cols += [k, "field_%s_mean" % k, "field_%s_sd" % k]
    with open(os.path.join(HERE, "player_tournaments.csv"), "w",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in sorted(pt, key=lambda x: (x["pid"], x["date_start"])):
            w.writerow([_fmt(r.get(c, "")) for c in cols])


def _write_tours(tours, field):
    with open(os.path.join(HERE, "field_tournaments.csv"), "w",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["tid", "comp_slug", "event_id", "year", "level",
                    "age_group", "scope", "division", "zone", "date_start",
                    "date_end", "n_teams", "n_roster", "n_qualified",
                    "field_age_mean", "field_age_sd", "url"])
        for tid, t in sorted(tours.items(),
                             key=lambda kv: (kv[1]["season"] or 0, kv[0])):
            f = field.get(tid, {})
            w.writerow([tid, t["comp_slug"], t["event_id"], t["season"],
                        t["level"], t["age_group"], t["scope"], t["tier"],
                        t["zone"] or "",
                        t["start"].date().isoformat() if t["start"] else "",
                        t["end"].date().isoformat() if t["end"] else "",
                        t.get("n_teams", 0),
                        f.get("n_roster", 0), f.get("n_qual", 0),
                        _fmt(f.get("age_mean")), _fmt(f.get("age_sd")),
                        t["url"]])


V4_DIR = "/Users/kennakao/nba/datarebuild/v4_build/data_v4"


def ncaa_track():
    """Read-only US/international proxy from the frozen v4 inputs: a pid with
    non-empty col_gp has NCAA season data, i.e. came through US college
    basketball.  (intl_gp is NOT usable for this: the crude youth lines the
    project already has were merged into the intl_* pro block, so US high-
    schoolers with one FIBA youth appearance carry intl_gp too.)
    Returns pid -> 1 (NCAA-track) / 0 (non-NCAA); pids absent from the v4
    inputs are absent from the dict.  Nothing is written."""
    out = {}
    files = [os.path.join(V4_DIR, "train_2000_2018.csv")]
    files += sorted(glob.glob(os.path.join(V4_DIR, "tests", "*_inputs.csv")))
    for path in files:
        if not os.path.exists(path):
            continue
        try:
            with open(path, newline="") as fh:
                for r in csv.DictReader(fh):
                    pid = r.get("pid")
                    if not pid:
                        continue
                    v = (r.get("col_gp") or "").strip() not in ("", "nan", "NaN")
                    out[pid] = max(out.get(pid, 0), 1 if v else 0)
        except Exception as e:                       # never fatal, read-only
            log("  (v4 inputs unreadable: %r)" % e)
    return out


DEFS = [
    ("fy_has_youth", "1 if the player appears in >=1 FIBA U15-U19 men's "
     "tournament that ended before his draft-night cutoff, else 0."),
    ("fy_n_tournaments", "Count of those pre-draft FIBA youth tournaments."),
    ("fy_best_level", "Max level ladder over them: 4 = U19 World Cup, "
     "3 = U17 World Cup or U18/U19 continental div A, 2 = U16/U17 continental "
     "div A, 1 = div B/C, qualifier, challenger or sub-zone event."),
    ("fy_age_rel_last", "Age in years at the latest pre-draft tournament minus "
     "that tournament field's mean age (negative = younger than the field)."),
    ("fy_age_rel_min", "Most negative age-minus-field-mean achieved across all "
     "pre-draft tournaments (youngest relative age)."),
    ("fy_pts40_z_last", "Points per 40 minutes at the latest tournament, "
     "z-scored within that tournament's qualified field "
     "(>=3 games and >=40 total minutes)."),
    ("fy_pir40_z_last", "FIBA efficiency (PIR) per 40 minutes at the latest "
     "tournament, z-scored within the same field."),
    ("fy_best_pir40_z", "Best (max) PIR-per-40 z-score across all pre-draft "
     "tournaments."),
    ("fy_underage_flag", "1 if in any pre-draft tournament the player was at "
     "least 1.0 year younger than that field's mean age, else 0."),
    ("fy_minutes_share_last", "Minutes per game at the latest tournament "
     "divided by 40 (share of a regulation game)."),
]


def _report(ident, feats, tours, pt, hs_meta, hs_lo, hs_hi, nat_by_pid=None):
    bands = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018),
             ("2019-25", 2019, 2025)]
    log("")
    log("rows in features.csv: %d" % len(ident))
    log("tournaments in field_tournaments.csv: %d" % len(tours))
    log("player-tournament rows: %d" % len(pt))
    log("")
    log("coverage by draft-year band (fy_has_youth = 1):")
    for name, lo, hi in bands:
        tot = [c for c in ident if lo <= c["draft_year"] <= hi]
        got = [c for c in tot if feats.get(c["pid"], {}).get("fy_has_youth")]
        log("  %-8s %4d / %4d  (%5.1f%%)" % (
            name, len(got), len(tot), 100.0 * len(got) / max(1, len(tot))))
    it = ncaa_track()
    log("")
    log("coverage by track (col_gp in the frozen v4 inputs; read-only proxy):")
    for label, sel in (("US / NCAA-track", lambda p: it.get(p) == 1),
                       ("non-NCAA (intl)", lambda p: it.get(p) == 0),
                       ("not in v4 inputs", lambda p: p not in it)):
        tot = [c for c in ident if sel(c["pid"])]
        got = [c for c in tot if feats.get(c["pid"], {}).get("fy_has_youth")]
        log("  %-17s %4d / %4d  (%5.1f%%)" % (
            label, len(got), len(tot), 100.0 * len(got) / max(1, len(tot))))
    if nat_by_pid:
        usa = sum(1 for p, n in nat_by_pid.items()
                  if n == "USA" and feats.get(p, {}).get("fy_has_youth"))
        oth = sum(1 for p, n in nat_by_pid.items()
                  if n != "USA" and feats.get(p, {}).get("fy_has_youth"))
        log("  covered players by FIBA nationality: USA %d, other %d" % (usa, oth))
    log("")
    log("hoop summit source: %s rev %s (%s); table covers draft years %s-%s"
        % (hs_meta.get("url", "n/a"), hs_meta.get("revid", "n/a"),
           hs_meta.get("rev_ts", "n/a"), hs_lo, hs_hi))
    log("")
    log("top 10 feature definitions:")
    for i, (k, d) in enumerate(DEFS, 1):
        log("  %2d. %-22s %s" % (i, k, d))


if __name__ == "__main__":
    main()
