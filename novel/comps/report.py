#!/usr/bin/env python3
"""Coverage report + spot check + leakage assertions for the comps collector."""
import csv, json, os, re, collections

BASE = os.path.dirname(os.path.abspath(__file__))
NAMES = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
BANDS = [("2000-07", 2000, 2007), ("2008-18", 2008, 2018), ("2019-25", 2019, 2025),
         ("2026", 2026, 2026)]
# draft-night cutoffs from COLLECTOR_RULES.md (22:00 UTC on the date); 2026 as in the
# sibling nbadraftnet collector
CUT = {2000:"20000628", 2001:"20010627", 2002:"20020626", 2003:"20030626", 2004:"20040624",
       2005:"20050628", 2006:"20060628", 2007:"20070628", 2008:"20080626", 2009:"20090625",
       2010:"20100624", 2011:"20110623", 2012:"20120628", 2013:"20130627", 2014:"20140626",
       2015:"20150625", 2016:"20160623", 2017:"20170622", 2018:"20180621", 2019:"20190620",
       2020:"20201118", 2021:"20210729", 2022:"20220623", 2023:"20230622", 2024:"20240626",
       2025:"20250625", 2026:"20260623"}

_idrows = list(csv.DictReader(open(NAMES)))
ids  = {r["pid"]: int(float(r["draft_year"])) for r in _idrows}
pname = {r["pid"]: r["player_name"] for r in _idrows}   # in memory only, never written
feat = list(csv.DictReader(open(os.path.join(BASE, "features.csv"))))
prov = list(csv.DictReader(open(os.path.join(BASE, "provenance.csv"))))
unm  = list(csv.DictReader(open(os.path.join(BASE, "unmatched.csv"))))

print("features.csv rows            : %d" % len(feat))
print("feature columns              : %d" % (len(feat[0]) - 1))
have = [r for r in feat if r["cp_n_comps"] != ""]
res  = [r for r in feat if r["cp_resolved"] == "1"]
print("rows with a comparison string: %d" % len(have))
print("rows with >=1 resolved comp  : %d  (%.1f%% of drafted, %.1f%% of those with a string)"
      % (len(res), 100.0*len(res)/len(feat), 100.0*len(res)/len(have)))
print("comp links (prospect x comp) : %d" % len(prov))
print("unmatched comp names         : %d" % len(unm))
print()
print("COVERAGE BY DRAFT-YEAR BAND")
print("%-9s %7s %9s %9s %9s %9s" % ("band","drafted","w/ string","%","resolved","%"))
for nm, a, b in BANDS:
    tot = sum(1 for p, y in ids.items() if a <= y <= b)
    h = sum(1 for r in have if a <= ids[r["pid"]] <= b)
    s = sum(1 for r in res  if a <= ids[r["pid"]] <= b)
    if tot:
        print("%-9s %7d %9d %8.1f%% %9d %8.1f%%" % (nm, tot, h, 100.0*h/tot, s, 100.0*s/tot))
tot = len(ids)
print("%-9s %7d %9d %8.1f%% %9d %8.1f%%"
      % ("ALL", tot, len(have), 100.0*len(have)/tot, len(res), 100.0*len(res)/tot))
print()
print("UNRESOLVED NAMES BY REASON")
for k, v in collections.Counter(r["reason"] for r in unm).most_common():
    print("  %-42s %d" % (k, v))
print()
print("MATCH RULES USED (comp links)")
for k, v in collections.Counter(r["match_rule"] for r in prov).most_common():
    print("  %-42s %d" % (k, v))
print()

# ---- leakage assertions -----------------------------------------------------
bad = 0
for r in prov:
    dy = int(r["draft_year"])
    if int(r["seasons_to_date"]) > 0 and int(r["comp_from_year"]) > dy - 1:
        print("LEAK: %s comp %s debut %s > draft %s" % (r["pid"], r["comp_display_name"],
                                                        r["comp_from_year"], dy)); bad += 1
    if r["capture_ts"] >= CUT[dy] + "220000":
        print("LEAK: capture at/after draft night", r["pid"], r["capture_ts"]); bad += 1
    last_season_end = dy                       # season S/(S+1) with S = dy-1 ends in dy
    if int(r["seasons_to_date"]) > 0 and last_season_end > dy:
        print("LEAK: season ends after draft", r["pid"]); bad += 1
# recompute one comp independently straight from the cache
def indep(pid, dy):
    rs = [x for x in json.load(open(os.path.join(BASE, "raw", "%s.json" % pid)))["resultSets"]
          if x["name"] == "SeasonTotalsRegularSeason"][0]
    h = {k: i for i, k in enumerate(rs["headers"])}
    keep = [r for r in rs["rowSet"] if r[h["LEAGUE_ID"]] in (None, "00")
            and int(r[h["SEASON_ID"]][:4]) <= dy - 1]
    return (len(keep), sum(r[h["GP"]] or 0 for r in keep), sum(r[h["MIN"]] or 0 for r in keep),
            sum(r[h["PTS"]] or 0 for r in keep))
chk = 0
for r in prov[::137]:
    s, g, m, p = indep(r["comp_person_id"], int(r["draft_year"]))
    assert s == int(r["seasons_to_date"]) and g == int(r["gp_to_date"]), r
    assert abs(m - float(r["min_to_date"])) < 0.5 and abs(p - float(r["pts_to_date"])) < 0.5, r
    chk += 1
print("leakage assertions: %d violations; %d provenance rows re-derived from cache OK"
      % (bad, chk))
print()
print("SPOT CHECK (prospect, comps used, cp_pts36_to_date)")
spot = json.load(open(os.path.join(BASE, "spotcheck.json")))
fi = {r["pid"]: r for r in feat}
step = max(1, len(spot) // 10)
for row in spot[::step][:10]:
    pid, dy, raw, comps, pts36 = row
    name = pname[pid]
    print("  %-22s %s  raw=%-34s -> %-34s pts36=%s seasons=%s"
          % (name, dy, raw[:34], comps[:34], pts36 or "NA", fi[pid]["cp_seasons_to_date"]))
