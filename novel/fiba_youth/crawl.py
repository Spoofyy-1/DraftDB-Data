#!/usr/bin/env python3
"""
Crawl fiba.basketball youth (U15-U19) men's national-team competitions,
2000-2025, and cache everything under raw/.

Three stages, all resumable (delete nothing to resume; just re-run):

  1. competition sitemap_index.xml  -> edition (event) ids
  2. <event>/players                -> event metadata, team list, full player
                                       field with dates of birth
  3. <event>/teams/<slug>           -> per-player tournament totals and the
                                       team's final ranking

Every page is stored gzipped under raw/pages/ and the extracted JSON under
raw/parsed/<comp_id>_<event_id>.json, which doubles as the per-tournament
checkpoint: an event whose parsed file exists and is marked complete is
skipped on the next run.

robots.txt (fetched 2026-09-08) disallows only /login /register /welcome
/forgot-password /auth-callback and their localised variants; nothing under
/en/history/ is disallowed.  Requests are throttled to <= 1 per 1.1 s with
exponential backoff on 429/5xx and a descriptive User-Agent.

Usage:  cd .../novel/fiba_youth && nohup python3 crawl.py >> run.log 2>&1 &
Resume: run the same command again.
"""
import json
import os
import re
import sys

from fibalib import (BASE, PAGES, PARSED, SITEMAPS, fetch, find_arr, flight,
                     json_at, log)
from competitions import COMPETITIONS

YEAR_MIN, YEAR_MAX = 2000, 2025


def comp_id(slug):
    return slug.split("-", 1)[0]


# ------------------------------------------------------------ stage 1 ------
def editions(slug):
    """Event ids for a competition, from its sitemap_index.xml."""
    cid = comp_id(slug)
    path = os.path.join(SITEMAPS, "%s.xml" % cid)
    url = "%s/en/history/%s/sitemap_index.xml" % (BASE, slug)
    xml = fetch(url, path)
    if not xml:
        return []
    ids = []
    for loc in re.findall(r"<loc>(.*?)</loc>", xml):
        m = re.search(r"/history/%s/(\d+)/sitemap\.xml" % re.escape(slug), loc)
        if m:
            ids.append(m.group(1))
    return sorted(set(ids), key=int)


# ------------------------------------------------------------ stage 2 ------
def parse_players_page(buf):
    """Event metadata + team list + player field from a /players page."""
    meta = None
    m = re.search(r'"fibaSourceDatas"\s*:\s*\{', buf)
    if m:
        meta = json_at(buf, m.end() - 1)
    teams = []
    tm = re.search(r'"teams"\s*:\s*\[\s*\{\s*"teamId"', buf)
    if tm:
        from fibalib import json_array_at
        teams = json_array_at(buf, buf.index("[", tm.start())) or []
    players = []
    seen = set()
    for pm in re.finditer(r'"player"\s*:\s*\{', buf):
        obj = json_at(buf, pm.end() - 1)
        if not obj or "playerId" not in obj:
            continue
        pidk = obj["playerId"]
        if pidk in seen:
            continue
        seen.add(pidk)
        # RSC payloads sometimes emit "team":"$hh" back-references instead of
        # an inline object; those rows get their team from the team pages.
        t = obj.get("team")
        if not isinstance(t, dict):
            t = {}
        players.append({
            "player_id": pidk,
            "first_name": obj.get("firstName"),
            "last_name": obj.get("lastName"),
            "nationality": obj.get("nationality"),
            "position": obj.get("positionCode"),
            "games_played": obj.get("gamesPlayed"),
            "dob": obj.get("dateOfBirth"),
            "team_id": t.get("teamId"),
            "team_slug": t.get("slug"),
            "team_code": t.get("code"),
        })
    return meta, teams, players


# ------------------------------------------------------------ stage 3 ------
STAT_KEYS = [
    "totalGamesPlayed", "totalPlayTimeInSeconds", "totalPoints",
    "totalRebounds", "totalReboundsOffensive", "totalReboundsDefensive",
    "totalAssists", "totalSteals", "totalBlocks", "totalTurnovers",
    "totalFouls", "totalEfficiency", "totalPlusMinus",
    "totalFieldGoalsMade", "totalFieldGoalsAttempted",
    "totalTwoPointsMade", "totalTwoPointsAttempted",
    "totalThreePointsMade", "totalThreePointsAttempted",
    "totalFreeThrowsMade", "totalFreeThrowsAttempted",
    "totalGamesWon", "totalGamesLost",
]


def parse_team_page(buf):
    """(final_ranking, [player stat dicts]) from an event team page."""
    stats = find_arr(buf, "playerInCompetitionTeamStatistics") or []
    out = []
    for s in stats:
        if not isinstance(s, dict) or "playerId" not in s:
            continue
        rec = {"player_id": s["playerId"],
               "first_name": s.get("firstName"),
               "last_name": s.get("lastName"),
               "team_id": s.get("teamId")}
        for k in STAT_KEYS:
            rec[k] = s.get(k)
        out.append(rec)
    fr = None
    m = re.search(r'"finalRanking"\s*:\s*(\d+|null)', buf)
    if m and m.group(1) != "null":
        fr = int(m.group(1))
    return fr, out


# ------------------------------------------------------------- driver ------
def do_event(slug, cid, eid):
    out_path = os.path.join(PARSED, "%s_%s.json" % (cid, eid))
    if os.path.exists(out_path):
        try:
            with open(out_path) as fh:
                rec = json.load(fh)
            if rec.get("complete"):
                return rec
        except Exception:
            pass

    url = "%s/en/history/%s/%s/players" % (BASE, slug, eid)
    html = fetch(url, os.path.join(PAGES, cid, "%s_players.html.gz" % eid))
    if not html:
        rec = {"comp_slug": slug, "comp_id": cid, "event_id": eid,
               "complete": True, "skip": "players page unavailable"}
        _save(out_path, rec)
        return rec
    buf = flight(html)
    meta, teams, players = parse_players_page(buf)

    rec = {"comp_slug": slug, "comp_id": cid, "event_id": eid,
           "meta": meta, "teams": teams, "players": players,
           "team_stats": {}, "team_finish": {}, "complete": False}

    season = (meta or {}).get("season")
    gender = (meta or {}).get("gender")
    if season is None or not (YEAR_MIN <= int(season) <= YEAR_MAX):
        rec["skip"] = "season %s outside %d-%d" % (season, YEAR_MIN, YEAR_MAX)
        rec["complete"] = True
        _save(out_path, rec)
        log("  %s/%s season=%s SKIP (out of range)" % (cid, eid, season))
        return rec
    if gender and str(gender).lower() not in ("men", "boys", "male"):
        rec["skip"] = "gender %s" % gender
        rec["complete"] = True
        _save(out_path, rec)
        log("  %s/%s gender=%s SKIP" % (cid, eid, gender))
        return rec

    slugs = [t.get("slug") for t in teams if t.get("slug")]
    for ts in slugs:
        turl = "%s/en/history/%s/%s/teams/%s" % (BASE, slug, eid, ts)
        thtml = fetch(turl, os.path.join(PAGES, cid,
                                         "%s_team_%s.html.gz" % (eid, ts)))
        if not thtml:
            continue
        tbuf = flight(thtml)
        fr, ps = parse_team_page(tbuf)
        rec["team_stats"][ts] = ps
        if fr is not None:
            rec["team_finish"][ts] = fr
    rec["complete"] = True
    _save(out_path, rec)
    log("  %s/%s season=%s teams=%d players=%d stats=%d" % (
        cid, eid, season, len(slugs), len(players),
        sum(len(v) for v in rec["team_stats"].values())))
    return rec


def _save(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh)
    os.replace(tmp, path)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    # highest-signal competitions first so a partial run is still useful
    def rank(s):
        tier, scope, age = COMPETITIONS[s]
        return (0 if scope == "world" else 1 if scope == "continental" else 2,
                0 if tier == "A" else 1, -age, s)
    slugs = sorted(COMPETITIONS, key=rank)
    if only:
        slugs = [s for s in slugs if s.startswith(only)]
    log("crawl start: %d competitions" % len(slugs))
    for slug in slugs:
        cid = comp_id(slug)
        eids = editions(slug)
        log("%s -> %d editions" % (slug, len(eids)))
        for eid in eids:
            try:
                do_event(slug, cid, eid)
            except Exception as e:
                log("  ERROR %s/%s: %r" % (cid, eid, e))
    log("crawl done")


if __name__ == "__main__":
    main()
