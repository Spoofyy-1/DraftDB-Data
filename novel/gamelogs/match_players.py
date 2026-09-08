"""Match drafted players (identity file) to ncaahoopR team-seasons.

Evidence, in priority order:
  R  ncaahoopR rosters      (seasons 2008-09..2024-25)  full name + team dir  -- exact naming
  T  Torvik player tables   (2008..2026 cached csv.gz)  full name + team      -- mapped via teams.ekey
  W  Wikipedia infobox 'college' (all years, from wiki_raw/attn_*.json)       -- college + year span
Every kept (pid, season, team) must later be confirmed by the player's abbreviated
box-score name ("I. Lastname") appearing in that team-season's box scores.
Outputs: work/player_seasons.csv, work/match_log.csv
"""
import csv, glob, gzip, json, re, sys, collections, unicodedata
sys.path.insert(0, "/Users/kennakao/nba/datarebuild/novel/gamelogs")
import teams as TM

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
IDF = "/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"
DB = "/Users/kennakao/nba/datarebuild"

CUT = {2000:"2000-06-28",2001:"2001-06-27",2002:"2002-06-26",2003:"2003-06-26",2004:"2004-06-24",
       2005:"2005-06-28",2006:"2006-06-28",2007:"2007-06-28",2008:"2008-06-26",2009:"2009-06-25",
       2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",
       2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",
       2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",
       2025:"2025-06-25",2026:"2026-06-24"}   # 2026 extrapolated (4th Wed/Thu of June)

SUF = r"\b(jr|sr|ii|iii|iv|v)\b"
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`’]", "", s)
    s = re.sub(r"[^a-z ]", " ", s)
    s = re.sub(SUF, " ", s)
    return re.sub(r"\s+", " ", s).strip()

def sy(season):   # "2018-19" -> 2019 (season-ending year)
    return int(season[:4]) + 1

# ---------- inputs -----------------------------------------------------------
ids = list(csv.DictReader(open(IDF)))
sched = list(csv.DictReader(gzip.open(f"{D}/raw/schedules.csv.gz", "rt")))
team_seasons = collections.defaultdict(set)          # season -> set(team_dir)
for r in sched: team_seasons[r["season"]].add(r["team"])
key2dir = collections.defaultdict(dict)              # season -> key -> dir
for ssn, ts in team_seasons.items():
    for t in ts: key2dir[ssn].setdefault(TM.key(t), t)

ros = list(csv.DictReader(gzip.open(f"{D}/raw/rosters.csv.gz", "rt")))
R = collections.defaultdict(list)
for r in ros: R[norm(r["name"])].append(r)

TCOLS = ["player_name","team","conf","GP","Min_per","ORtg","usg","eFG","TS_per","ORB_per","DRB_per",
         "AST_per","TO_per","FTM","FTA","FT_per","twoPM","twoPA","twoP_per","TPM","TPA","TP_per",
         "blk_per","stl_per","ftr","yr","ht","num","porpag","adjoe","pfr","year","tpid"]
T = collections.defaultdict(list)
for fp in sorted(glob.glob(f"{DB}/tracking_raw/torvik_*.csv.gz")):
    yr = int(fp.split("_")[-1][:4])
    for row in csv.reader(gzip.open(fp, "rt", errors="ignore")):
        if len(row) < 33: continue
        d = dict(zip(TCOLS, row[:33])); d["_y"] = yr
        T[norm(d["player_name"])].append(d)

WIKI = {}
for fp in glob.glob(f"{DB}/wiki_raw/attn_*.json"):
    try: d = json.load(open(fp))
    except Exception: continue
    c = (d.get("infobox") or {}).get("college", "")
    if c: WIKI[d["pid"]] = c

LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*?)\]\]")
def wiki_colleges(raw):
    """-> list of (college_name, first_year, last_year|None) in wikitext order."""
    out = []
    for part in re.split(r"\n|\*|<br\s*/?>|;", raw):
        names = LINK.findall(part)
        nm = names[0] if names else re.sub(r"\(.*?\)", "", part).strip()
        nm = re.sub(r"\s*\(.*?\)\s*$", "", nm).strip()
        if not nm: continue
        m = re.search(r"\((\d{4})\s*[–—-]?\s*(\d{4})?\)", part)
        out.append((nm, int(m.group(1)) if m else None,
                    int(m.group(2)) if m and m.group(2) else None))
    return out

# ---------- match ------------------------------------------------------------
rows, log = [], []
cnt = collections.Counter()
for t in ids:
    pid = t["pid"]; dy = int(float(t["draft_year"])); nm = norm(t["player_name"])
    lo, hi = dy - 5, dy
    cand = collections.defaultdict(set)               # season -> set(team_dir), plus src
    srcs = collections.defaultdict(set)
    for r in R.get(nm, []):
        if lo <= sy(r["season"]) <= hi:
            cand[r["season"]].add(r["team"]); srcs[r["season"]].add("R")
    for d in T.get(nm, []):
        if not (lo <= d["_y"] <= hi): continue
        ssn = "%d-%02d" % (d["_y"] - 1, d["_y"] % 100)
        dir_ = key2dir.get(ssn, {}).get(TM.ekey(d["team"]))
        if dir_: cand[ssn].add(dir_); srcs[ssn].add("T")
    wdirs = set()
    for cn, y0, y1 in wiki_colleges(WIKI.get(pid, "")):
        k = TM.ekey(re.sub(r"\s+Tar Heels|\s+Wildcats", "", cn))
        for ssn in team_seasons:
            if k in key2dir.get(ssn, {}) and lo <= sy(ssn) <= hi:
                if y0 and not (y0 < sy(ssn) <= (y1 or hi) + 0): continue
                wdirs.add((ssn, key2dir[ssn][k]))
    if not cand and wdirs:                            # W-only (mostly pre-2008 drafts)
        for ssn, dir_ in wdirs:
            cand[ssn].add(dir_); srcs[ssn].add("W")
    if not cand:
        cnt["no_college_evidence"] += 1
        log.append(dict(pid=pid, draft_year=dy, reason="no_college_evidence", detail="")); continue
    last = max(sy(s) for s in cand)
    if last < dy - 1:
        cnt["stale_last_season"] += 1
        log.append(dict(pid=pid, draft_year=dy, reason="stale_last_season", detail=str(last))); continue
    wd = {d for _, d in wdirs}
    kept = 0
    for ssn in sorted(cand):
        ds = cand[ssn]
        if len(ds) > 1:
            pick = ds & wd
            if len(pick) == 1: ds = pick
            else:
                cnt["ambiguous_team"] += 1
                log.append(dict(pid=pid, draft_year=dy, reason="ambiguous_team",
                                detail=f"{ssn}:{'|'.join(sorted(ds))}")); continue
        rows.append(dict(pid=pid, draft_year=dy, cutoff=CUT[dy], season=ssn,
                         team=list(ds)[0], src="".join(sorted(srcs[ssn])),
                         norm_name=nm, last_season=last)); kept += 1
    cnt["matched" if kept else "all_seasons_ambiguous"] += 1

with open(f"{D}/work/player_seasons.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid","draft_year","cutoff","season","team","src","norm_name","last_season"])
    w.writeheader(); w.writerows(rows)
with open(f"{D}/work/match_log.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid","draft_year","reason","detail"]); w.writeheader(); w.writerows(log)

print("identity rows", len(ids))
for k, v in cnt.most_common(): print("  ", k, v)
print("player-seasons", len(rows), "distinct pids", len({r['pid'] for r in rows}),
      "distinct team-seasons", len({(r['season'], r['team']) for r in rows}))
band = lambda y: "2000-07" if y <= 2007 else ("2008-18" if y <= 2018 else "2019-26")
bp = collections.Counter(band(int(float(t["draft_year"]))) for t in ids)
bm = collections.Counter(band(y) for _, y in {(x["pid"], x["draft_year"]) for x in rows})
for b in sorted(bp): print("  band", b, "matched %d / %d = %.1f%%" % (bm[b], bp[b], 100*bm[b]/bp[b]))
print("src mix", collections.Counter(r["src"] for r in rows).most_common())
