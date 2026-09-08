"""Game-level college features (gl2_) for the NBA redraft model.

See README.md for definitions.  All game rows are filtered to date < that player's draft-night
cutoff before anything is computed.
"""
import csv, gzip, math, os, re, sys, collections, unicodedata, datetime as dt
sys.path.insert(0, "/Users/kennakao/nba/datarebuild/novel/gamelogs")

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
SUF = {"jr", "sr", "ii", "iii", "iv", "v"}

def fnum(v):
    try:
        x = float(v)
        return x if x == x else None
    except Exception:
        return None

def nrm_name(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s.replace(".", " ")).strip()

def split_name(full):
    t = [x for x in nrm_name(full).split() if x and x not in SUF]
    return (t[0], t[-1]) if len(t) >= 2 else ((t[0], t[0]) if t else ("", ""))

DOUBLED = re.compile(r"^(.+?)\1")
def clean_box(p):
    """ESPN dumps in the 2003-2008 seasons concatenate the name with the initial/position:
    'K. DurantK' -> 'K. Durant';  'C. PaulC. PaulG' -> 'C. Paul'."""
    p = (p or "").strip()
    for _ in range(3):
        m = DOUBLED.match(p)
        if m and len(m.group(1)) >= 4: p = m.group(1).strip()
        q = re.sub(r"(?<=[a-z])[A-Z]$", "", p)
        if q == p: break
        p = q
    return p.strip()

def box_key(p):
    """box 'C.J. Fair' -> ('cj','fair');  'R. Powell Jr.' -> ('r','powell')"""
    t = [x for x in nrm_name(clean_box(p)).split() if x and x not in SUF]
    if len(t) < 2: return None
    return ("".join(t[:-1]), t[-1])

def gmsc(d):
    return (d["PTS"] + .4*d["FGM"] - .7*d["FGA"] - .4*(d["FTA"]-d["FTM"]) + .7*d["OREB"]
            + .3*d["DREB"] + d["STL"] + .7*d["AST"] + .7*d["BLK"] - .4*d["PF"] - d["TO"])

# ---------------------------------------------------------------- inputs
ps = list(csv.DictReader(open(f"{D}/work/player_seasons.csv")))
need_seasons = sorted({r["season"] for r in ps})

rank = {}; ranksrc = {}
for r in csv.DictReader(open(f"{D}/work/team_ratings.csv")):
    rank[(r["season"], r["team"])] = int(r["rank"]); ranksrc[(r["season"], r["team"])] = r["src"]

tteam = {}
for r in csv.DictReader(open(f"{D}/work/tourney_team.csv")):
    tteam[(r["season"], r["team"])] = r
tgames = {(r["season"], r["game_id"]) for r in csv.DictReader(open(f"{D}/work/tourney_games.csv"))}

sched = collections.defaultdict(dict)                 # (season,team) -> game_id -> row
for r in csv.DictReader(gzip.open(f"{D}/work/games.csv.gz", "rt")):
    sched[(r["season"], r["team"])][r["game_id"]] = r

ros = collections.defaultdict(list)                   # (season,team) -> [names]
for r in csv.DictReader(gzip.open(f"{D}/raw/rosters.csv.gz", "rt")):
    ros[(r["season"], r["team"])].append(r["name"])

BOXF = ["MIN","FGM","FGA","3PTM","3PTA","FTM","FTA","OREB","DREB","REB","AST","STL","BLK","TO","PF","PTS"]
def load_box(season):
    out = collections.defaultdict(list)               # (season,team) -> rows
    fp = f"{D}/raw/box_{season}.csv.gz"
    if not os.path.exists(fp): return out
    for r in csv.DictReader(gzip.open(fp, "rt")):
        out[(season, r["team"])].append(r)
    return out

# ---------------------------------------------------------------- per player-season extraction
need = collections.defaultdict(list)
for r in ps: need[r["season"]].append(r)

pseason = {}                                          # (pid, season) -> dict of game rows + team info
unmatched = []
for season in need_seasons:
    box = load_box(season)
    for r in need[season]:
        pid, team, cut = r["pid"], r["team"], r["cutoff"]
        rows = box.get((season, team), [])
        if not rows:
            unmatched.append(dict(pid=pid, draft_year=r["draft_year"], season=season, team=team,
                                  reason="no_box_scores_in_archive", detail="")); continue
        fst, lst = split_name(r["norm_name"])
        cands = collections.defaultdict(list)
        for b in rows:
            if b["player"].strip().upper() == "TEAM": continue
            k = box_key(b["player"])
            if not k or k[1] != lst: continue
            if not (fst.startswith(k[0]) or k[0].startswith(fst[:1]) and len(k[0]) == 1): continue
            cands[clean_box(b["player"])].append(b)
        if len(cands) > 1:            # prefer the variant whose initials match exactly
            exact = {nm: bs for nm, bs in cands.items() if box_key(nm)[0] == fst}
            if len(exact) == 1: cands = exact
        if not cands:
            unmatched.append(dict(pid=pid, draft_year=r["draft_year"], season=season, team=team,
                                  reason="name_not_in_box", detail="")); continue
        if len(cands) > 1:
            # different people iff two of the variants appear in the same game
            seen = collections.Counter()
            clash = False
            for nm, bs in cands.items():
                gs = {b["game_id"] for b in bs}
                for nm2, bs2 in cands.items():
                    if nm2 <= nm: continue
                    if gs & {b["game_id"] for b in bs2}: clash = True
            if clash:
                unmatched.append(dict(pid=pid, draft_year=r["draft_year"], season=season, team=team,
                                      reason="ambiguous_box_name", detail="|".join(sorted(cands))));continue
        rl = sorted({" ".join(nrm_name(n).split()) for n in ros.get((season, team), [])
                     if split_name(n)[1] == lst and split_name(n)[0]})
        if len(rl) > 1:
            keep = {n for n in rl if split_name(n)[0] == fst}
            if len(keep) != 1:
                unmatched.append(dict(pid=pid, draft_year=r["draft_year"], season=season, team=team,
                                      reason="ambiguous_roster_name", detail="|".join(sorted(rl)))); continue
        pg = {}; na = set()
        for bs in cands.values():
            for b in bs:
                sr = sched[(season, team)].get(b["game_id"], {})
                gdate = sr.get("date") or b.get("date") or ""
                if not gdate or gdate >= cut: continue
                m = fnum(b["MIN"])
                if m is None:                          # "NA" minutes: DNP or an archive gap
                    na.add(b["game_id"]); continue
                d = {c: (fnum(b[c]) or 0.0) for c in BOXF}
                d["gid"] = b["game_id"]; d["date"] = gdate
                d["start"] = 1 if str(b["starter"]).upper() == "TRUE" else 0
                d["gmsc"] = gmsc(d)
                pg[b["game_id"]] = d
        if len(pg) < 2:
            unmatched.append(dict(pid=pid, draft_year=r["draft_year"], season=season, team=team,
                                  reason="fewer_than_2_games", detail=str(len(pg)))); continue
        pseason[(pid, season)] = dict(team=team, games=pg, cutoff=cut, na=len(na - set(pg)),
                                      draft_year=int(r["draft_year"]))

print("player-seasons extracted", len(pseason), "unmatched rows", len(unmatched), flush=True)

# ---------------------------------------------------------------- team-season context
# The observable team schedule is the set of games the archive actually has a box score for:
# using the schedule file instead would turn archive gaps into phantom "missed games".
tctx = {}
for season in need_seasons:
    box = load_box(season)
    for (s, t), rows in box.items():
        tot = collections.defaultdict(float); info = {}
        for b in rows:
            gid = b["game_id"]
            if gid not in info:
                sr = sched[(s, t)].get(gid, {})
                a, bb = fnum(sr.get("ts")), fnum(sr.get("os"))
                info[gid] = dict(game_id=gid, date=sr.get("date") or b.get("date") or "",
                                 loc=sr.get("loc") or b.get("location") or "",
                                 opp_dir=sr.get("opp_dir", ""),
                                 margin=(abs(a - bb) if a is not None and bb is not None else None))
            if b["player"].strip().upper() == "TEAM": continue
            m = fnum(b["MIN"])
            if m: tot[gid] += m
        for gid in info: info[gid]["team_min"] = tot.get(gid, 0.0)
        tctx[(s, t)] = dict(team_min=dict(tot), games=info,
                            n_sched=sum(1 for g in sched[(s, t)].values() if g["date"]))

# ---------------------------------------------------------------- feature helpers
def agg(gl):
    a = {c: 0.0 for c in BOXF}
    for g in gl:
        for c in BOXF: a[c] += g[c]
    a["GMSC"] = sum(g["gmsc"] for g in gl); a["N"] = len(gl)
    return a

def per40(a, c):
    return 40.0 * a[c] / a["MIN"] if a["MIN"] > 0 else None

def rates(a):
    o = {}
    o["fg"] = a["FGM"]/a["FGA"] if a["FGA"] else None
    o["fg3"] = a["3PTM"]/a["3PTA"] if a["3PTA"] else None
    o["ft"] = a["FTM"]/a["FTA"] if a["FTA"] else None
    o["ftr"] = a["FTA"]/a["FGA"] if a["FGA"] else None
    o["efg"] = (a["FGM"]+.5*a["3PTM"])/a["FGA"] if a["FGA"] else None
    den = 2*(a["FGA"]+.44*a["FTA"])
    o["ts"] = a["PTS"]/den if den else None
    return o

def sub(x, y):
    return None if x is None or y is None else x - y

def moments(v):
    n = len(v)
    if n < 2: return (v[0] if v else None), None, None
    m = sum(v)/n
    var = sum((x-m)**2 for x in v)/(n-1)
    sd = math.sqrt(var)
    sk = None
    if n > 2 and sd > 0:
        sk = (n/((n-1)*(n-2))) * sum(((x-m)/sd)**3 for x in v)
    return m, sd, sk

# ---------------------------------------------------------------- build
feat = {}
byp = collections.defaultdict(list)
for (pid, season), v in pseason.items(): byp[pid].append(season)

for pid, seasons in byp.items():
    seasons = sorted(seasons)
    fs = seasons[-1]
    P = pseason[(pid, fs)]; team = P["team"]; cut = P["cutoff"]; gl = list(P["games"].values())
    f = {}
    f["gl2_final_season_end"] = int(fs[:4]) + 1
    f["gl2_final_is_predraft_season"] = int(int(fs[:4]) + 1 == P["draft_year"])
    f["gl2_n_seasons"] = len(seasons)

    TC = tctx.get((fs, team), {})
    tgm = sorted([g for g in TC.get("games", {}).values() if g["date"] and g["date"] < cut],
                 key=lambda g: (g["date"], g["game_id"]))

    # ---- 1. opponent tiers
    def tier(g):
        r = rank.get((fs, g["opp_dir"])) if g["opp_dir"] else None
        return r if r is not None else 999
    gt = {g["game_id"]: tier(g) for g in tgm}
    src_t = [ranksrc.get((fs, g["opp_dir"]), "none") for g in tgm if g["opp_dir"]]
    f["gl2_tier_src_torvik"] = round(sum(1 for s in src_t if s == "torvik")/len(src_t), 4) if src_t else None
    A = agg(gl); f["gl2_g_all"] = A["N"]
    for lab, lim in (("t100", 100), ("t50", 50)):
        sel = [g for g in gl if gt.get(g["gid"], 999) <= lim]
        f[f"gl2_g_{lab}"] = len(sel)
        if len(sel) >= 3:
            S = agg(sel); rs, ra = rates(S), rates(A)
            f[f"gl2_{lab}_mpg"] = round(S["MIN"]/S["N"], 3)
            f[f"gl2_{lab}_ppg"] = round(S["PTS"]/S["N"], 3)
            f[f"gl2_{lab}_rpg"] = round(S["REB"]/S["N"], 3)
            f[f"gl2_{lab}_apg"] = round(S["AST"]/S["N"], 3)
            f[f"gl2_{lab}_spg"] = round(S["STL"]/S["N"], 3)
            f[f"gl2_{lab}_bpg"] = round(S["BLK"]/S["N"], 3)
            f[f"gl2_{lab}_topg"] = round(S["TO"]/S["N"], 3)
            f[f"gl2_{lab}_gmsc"] = round(S["GMSC"]/S["N"], 3)
            for k in ("fg", "fg3", "ft", "ftr", "efg", "ts"):
                f[f"gl2_{lab}_{k}"] = None if rs[k] is None else round(rs[k], 5)
            for c, nm in (("PTS","pts"),("REB","reb"),("AST","ast"),("STL","stl"),
                          ("BLK","blk"),("TO","tov"),("GMSC","gmsc")):
                dv = sub(40.0*S[c]/S["MIN"] if S["MIN"] else None, 40.0*A[c]/A["MIN"] if A["MIN"] else None)
                f[f"gl2_d{lab[1:]}_{nm}40"] = None if dv is None else round(dv, 4)
            for k in ("fg","fg3","ft","ftr","efg","ts"):
                dv = sub(rs[k], ra[k])
                f[f"gl2_d{lab[1:]}_{k}"] = None if dv is None else round(dv, 5)
            f[f"gl2_d{lab[1:]}_mpg"] = round(S["MIN"]/S["N"] - A["MIN"]/A["N"], 3)
    ra = rates(A)
    f["gl2_mpg"] = round(A["MIN"]/A["N"], 3)
    f["gl2_ppg"] = round(A["PTS"]/A["N"], 3)
    f["gl2_gmsc_pg"] = round(A["GMSC"]/A["N"], 3)
    for c, nm in (("PTS","pts"),("REB","reb"),("AST","ast"),("STL","stl"),("BLK","blk"),
                  ("TO","tov"),("GMSC","gmsc")):
        v = per40(A, c); f[f"gl2_{nm}40"] = None if v is None else round(v, 4)
    for k in ("fg","fg3","ft","ftr","efg","ts"):
        f[f"gl2_{k}"] = None if ra[k] is None else round(ra[k], 5)

    # ---- 2. NCAA tournament
    tsel = [g for g in gl if (fs, g["gid"]) in tgames]
    rsel = [g for g in gl if (fs, g["gid"]) not in tgames]
    f["gl2_ncaa_g"] = len(tsel)
    tt = tteam.get((fs, team))
    if tt:
        f["gl2_seed"] = int(tt["seed"]); f["gl2_team_ncaa_w"] = int(tt["wins"])
        f["gl2_exp_wins"] = float(tt["exp_wins"]); f["gl2_pase"] = float(tt["pase"])
        f["gl2_pase_pos"] = max(0.0, float(tt["pase"])); f["gl2_pase_neg"] = min(0.0, float(tt["pase"]))
        f["gl2_final4"] = int(tt["final4"]); f["gl2_champion"] = int(tt["champion"])
    else:
        f["gl2_team_ncaa_w"] = 0; f["gl2_final4"] = 0; f["gl2_champion"] = 0
    if len(tsel) >= 2 and rsel:
        T, R = agg(tsel), agg(rsel)
        for c, nm in (("PTS","pts"),("AST","ast"),("REB","reb"),("STL","stl"),
                      ("TO","tov"),("GMSC","gmsc")):
            dv = sub(40.0*T[c]/T["MIN"] if T["MIN"] else None, 40.0*R[c]/R["MIN"] if R["MIN"] else None)
            f[f"gl2_ncaa_d_{nm}40"] = None if dv is None else round(dv, 4)
        f["gl2_ncaa_d_mpg"] = round(T["MIN"]/T["N"] - R["MIN"]/R["N"], 3)
        rt, rr = rates(T), rates(R)
        f["gl2_ncaa_d_ts"] = None if sub(rt["ts"], rr["ts"]) is None else round(sub(rt["ts"], rr["ts"]), 5)
    cg = cw = cf4 = cch = 0; bseed = None
    for s in seasons:
        Q = pseason[(pid, s)]
        cg += sum(1 for g in Q["games"].values() if (s, g["gid"]) in tgames)
        q = tteam.get((s, Q["team"]))
        if q and any((s, g["gid"]) in tgames for g in Q["games"].values()):
            cw += int(q["wins"]); cf4 = max(cf4, int(q["final4"])); cch = max(cch, int(q["champion"]))
            bseed = int(q["seed"]) if bseed is None else min(bseed, int(q["seed"]))
    f["gl2_ncaa_g_car"] = cg; f["gl2_ncaa_w_car"] = cw
    f["gl2_final4_car"] = cf4; f["gl2_champion_car"] = cch
    if bseed is not None: f["gl2_best_seed_car"] = bseed

    # ---- 3. consistency & trend
    gl_sorted = sorted(gl, key=lambda g: (g["date"], g["gid"]))
    v = [g["gmsc"] for g in gl_sorted]
    m, sd, sk = moments(v)
    f["gl2_gmsc_mean"] = None if m is None else round(m, 4)
    f["gl2_gmsc_sd"] = None if sd is None else round(sd, 4)
    f["gl2_gmsc_skew"] = None if sk is None else round(sk, 4)
    f["gl2_gmsc_cv"] = round(sd/m, 4) if (sd is not None and m and m > 0) else None
    if sd:
        f["gl2_share_gmsc_above_1sd"] = round(sum(1 for x in v if x > m + sd)/len(v), 4)
        f["gl2_share_gmsc_below_1sd"] = round(sum(1 for x in v if x < m - sd)/len(v), 4)
    if len(gl_sorted) >= 14:
        L = agg(gl_sorted[-10:])
        for c, nm in (("PTS","pts"),("GMSC","gmsc")):
            dv = sub(40.0*L[c]/L["MIN"] if L["MIN"] else None, per40(A, c))
            f[f"gl2_last10_d_{nm}40"] = None if dv is None else round(dv, 4)
        f["gl2_last10_d_mpg"] = round(L["MIN"]/L["N"] - A["MIN"]/A["N"], 3)
    y = int(fs[:4]) + 1
    early = [g for g in gl_sorted if g["date"] < f"{y}-02-01"]
    late = [g for g in gl_sorted if g["date"] >= f"{y}-02-01"]
    if len(early) >= 5 and len(late) >= 5:
        E, L = agg(early), agg(late)
        for c, nm in (("PTS","pts"),("GMSC","gmsc"),("AST","ast"),("REB","reb")):
            dv = sub(40.0*L[c]/L["MIN"] if L["MIN"] else None, 40.0*E[c]/E["MIN"] if E["MIN"] else None)
            f[f"gl2_late_d_{nm}40"] = None if dv is None else round(dv, 4)
        f["gl2_late_d_mpg"] = round(L["MIN"]/L["N"] - E["MIN"]/E["N"], 3)
        de = sub(rates(L)["ts"], rates(E)["ts"])
        f["gl2_late_d_ts"] = None if de is None else round(de, 5)

    # ---- 4. availability
    played = {g["gid"] for g in gl}
    f["gl2_team_g"] = len(tgm)
    ns = len([g for g in sched[(fs, team)].values() if g["date"] and g["date"] < cut])
    f["gl2_team_g_sched"] = ns
    f["gl2_box_completeness"] = round(len(tgm)/ns, 4) if ns else None
    f["gl2_gp"] = len(played)
    f["gl2_avail"] = round(len(played)/len(tgm), 4) if tgm else None
    f["gl2_missed"] = len(tgm) - len(played)
    f["gl2_dnp_rows"] = P["na"]
    def blocks(team_games, pmap):
        seq = [(g["game_id"] in pmap) for g in team_games]
        out = []; i = 0
        while i < len(seq):
            if seq[i]: i += 1; continue
            j = i
            while j < len(seq) and not seq[j]: j += 1
            if j - i >= 3:
                pre = [pmap[team_games[k]["game_id"]] for k in range(i-1, -1, -1)
                       if seq[k]][:5]
                post = [pmap[team_games[k]["game_id"]] for k in range(j, len(seq)) if seq[k]][:5]
                if len(pre) >= 2 and len(post) >= 2 and \
                   sum(x["MIN"] for x in pre)/len(pre) >= 15 and sum(x["MIN"] for x in post)/len(post) >= 15:
                    out.append(j - i)
            i = j
        return out
    bl_f = blocks(tgm, P["games"])
    f["gl2_absence_blocks"] = len(bl_f)
    f["gl2_absence_max_len"] = max(bl_f) if bl_f else 0
    cgp = ctg = 0; cbl = []; gapseasons = 0
    for s in seasons:
        Q = pseason[(pid, s)]
        tg2 = sorted([g for g in tctx.get((s, Q["team"]), {}).get("games", {}).values()
                      if g["date"] and g["date"] < Q["cutoff"]], key=lambda g: (g["date"], g["game_id"]))
        cgp += len(Q["games"]); ctg += len(tg2); cbl += blocks(tg2, Q["games"])
    f["gl2_gp_car"] = cgp; f["gl2_team_g_car"] = ctg
    f["gl2_avail_car"] = round(cgp/ctg, 4) if ctg else None
    f["gl2_absence_blocks_car"] = len(cbl)
    yrs = sorted(int(s[:4]) + 1 for s in seasons)
    f["gl2_season_gaps"] = sum(1 for y2 in range(yrs[0], yrs[-1]) if y2 not in yrs)
    allm = [r for r in ps if r["pid"] == pid]
    f["gl2_seasons_no_archive"] = sum(1 for r in allm if (pid, r["season"]) not in pseason)

    # ---- 5. clutch / role
    tmin = TC.get("team_min", {})
    pm = sum(g["MIN"] for g in gl); tmtot = sum(tmin.get(g["gid"], 0) for g in gl)
    f["gl2_min_share"] = round(pm/tmtot, 4) if tmtot else None
    f["gl2_start_share"] = round(sum(g["start"] for g in gl)/len(gl), 4)
    marg = {g["game_id"]: g["margin"] for g in tgm if g["margin"] is not None}
    close = [g for g in gl if marg.get(g["gid"], 99) <= 5]
    blow = [g for g in gl if marg.get(g["gid"], -1) >= 20]
    f["gl2_n_close"] = len(close); f["gl2_n_blowout"] = len(blow)
    if len(close) >= 3:
        C = agg(close)
        f["gl2_close_mpg"] = round(C["MIN"]/C["N"], 3)
        f["gl2_close_gmsc40"] = None if per40(C, "GMSC") is None else round(per40(C, "GMSC"), 4)
        f["gl2_close_d_mpg"] = round(C["MIN"]/C["N"] - A["MIN"]/A["N"], 3)
        dv = sub(per40(C, "GMSC"), per40(A, "GMSC"))
        f["gl2_close_d_gmsc40"] = None if dv is None else round(dv, 4)
        dv = sub(rates(C)["ts"], ra["ts"])
        f["gl2_close_d_ts"] = None if dv is None else round(dv, 5)
    if len(blow) >= 3:
        B = agg(blow)
        f["gl2_blow_mpg"] = round(B["MIN"]/B["N"], 3)
        f["gl2_blow_d_mpg"] = round(B["MIN"]/B["N"] - A["MIN"]/A["N"], 3)
    if len(close) >= 3 and len(blow) >= 3:
        dv = sub(per40(agg(close), "GMSC"), per40(agg(blow), "GMSC"))
        f["gl2_close_minus_blow_gmsc40"] = None if dv is None else round(dv, 4)
        f["gl2_close_minus_blow_mpg"] = round(agg(close)["MIN"]/len(close) - agg(blow)["MIN"]/len(blow), 3)
    loc = {g["game_id"]: g["loc"] for g in tgm}
    nt = [g for g in gl if loc.get(g["gid"]) == "N"]
    f["gl2_n_neutral"] = len(nt)
    if len(nt) >= 3:
        N = agg(nt); dv = sub(per40(N, "GMSC"), per40(A, "GMSC"))
        f["gl2_neutral_d_gmsc40"] = None if dv is None else round(dv, 4)
    away = [g for g in gl if loc.get(g["gid"]) == "A"]
    home = [g for g in gl if loc.get(g["gid"]) == "H"]
    if len(away) >= 4 and len(home) >= 4:
        dv = sub(per40(agg(away), "GMSC"), per40(agg(home), "GMSC"))
        f["gl2_away_minus_home_gmsc40"] = None if dv is None else round(dv, 4)
    feat[pid] = f

# ---------------------------------------------------------------- write
cols = []
for f in feat.values():
    for k in f:
        if k not in cols: cols.append(k)
cols.sort()
with open(f"{D}/features.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["pid"] + cols)
    for pid in sorted(feat):
        f = feat[pid]
        w.writerow([pid] + ["" if f.get(c) is None else f.get(c, "") for c in cols])

ids = {r["pid"]: r for r in csv.DictReader(open("/Users/kennakao/Downloads/nba_redraft_handoff/identity_KEEP_SEPARATE/tabular_names.csv"))}
mlog = list(csv.DictReader(open(f"{D}/work/match_log.csv")))
with open(f"{D}/unmatched.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["pid", "draft_year", "stage", "reason", "detail"])
    w.writeheader()
    done = set(feat)
    for r in mlog:
        if r["pid"] in done: continue
        w.writerow(dict(pid=r["pid"], draft_year=r["draft_year"], stage="team_season_lookup",
                        reason=r["reason"], detail=r["detail"]))
    for r in unmatched:
        w.writerow(dict(pid=r["pid"], draft_year=r["draft_year"], stage="box_score_match",
                        reason=r["reason"], detail=f'{r["season"]}/{r["team"]} {r["detail"]}'))

print("features rows", len(feat), "cols", len(cols) + 1)
band = lambda y: "2002-07" if y <= 2007 else ("2008-18" if y <= 2018 else "2019-25")
tot = collections.Counter(); got = collections.Counter()
for pid, r in ids.items():
    y = int(float(r["draft_year"]))
    if y > 2025: continue
    tot[band(y)] += 1
    if pid in feat: got[band(y)] += 1
for b in sorted(tot): print("  band %s: %d/%d = %.1f%%" % (b, got[b], tot[b], 100*got[b]/tot[b]))
