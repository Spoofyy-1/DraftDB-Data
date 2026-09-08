"""Season team ratings + game linkage from the ncaahoopR_data schedules.

game_id appears in BOTH teams' schedule files, so opponents are linked exactly (no name matching).
Ratings: (a) Torvik end-of-season barthag rank (cached barttorvik.com/<year>_team_results.csv), primary for
seasons ending 2008+; (b) archive-derived ridge margin rating (Massey-style, home-court term, margins capped
at +-22), used for earlier seasons and as a cross-check.
Outputs: work/games.csv.gz, work/team_ratings.csv
"""
import csv, glob, gzip, sys, collections, datetime as dt
import numpy as np
sys.path.insert(0, "/Users/kennakao/nba/datarebuild/novel/gamelogs")
import teams as TM

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
CAP = 22.0
LAM = 25.0          # ridge penalty (games-equivalent shrink toward average)

sched = list(csv.DictReader(gzip.open(f"{D}/raw/schedules.csv.gz", "rt")))
print("schedule rows", len(sched))

# ---- game linkage -----------------------------------------------------------
by_game = collections.defaultdict(list)
for r in sched:
    if not r["game_id"]:
        continue
    by_game[(r["season"], r["game_id"])].append(r)

games = []                     # season, game_id, date, team, opp_team(dir or ""), loc, ts, os
for (ssn, gid), rs in by_game.items():
    dirs = [x["team"] for x in rs]
    for x in rs:
        others = [o for o in dirs if o != x["team"]]
        games.append(dict(season=ssn, game_id=gid, date=x["date"], team=x["team"],
                          opp_dir=others[0] if len(others) == 1 else "",
                          opp_name=x["opponent"], loc=x["location"],
                          ts=x["team_score"], os=x["opp_score"]))
n2 = sum(1 for v in by_game.values() if len(v) == 2)
print("games: total ids %d, with both teams in archive %d (%.1f%%), >2 rows %d"
      % (len(by_game), n2, 100 * n2 / len(by_game), sum(1 for v in by_game.values() if len(v) > 2)))

with gzip.open(f"{D}/work/games.csv.gz", "wt", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["season", "game_id", "date", "team", "opp_dir",
                                       "opp_name", "loc", "ts", "os"])
    w.writeheader()
    for g in sorted(games, key=lambda g: (g["season"], g["date"], g["game_id"], g["team"])):
        w.writerow(g)

# ---- archive ridge rating ---------------------------------------------------
arch = {}                                            # (season, team_dir) -> rating
for ssn in sorted({g["season"] for g in games}):
    gs = [g for g in games if g["season"] == ssn and g["opp_dir"]]
    seen = set(); rows = []
    for g in gs:
        k = (g["game_id"], tuple(sorted([g["team"], g["opp_dir"]])))
        if k in seen: continue
        seen.add(k)
        try:
            m = float(g["ts"]) - float(g["os"])
        except Exception:
            continue
        m = max(-CAP, min(CAP, m))
        rows.append((g["team"], g["opp_dir"], m, 0 if g["loc"] == "N" else (1 if g["loc"] == "H" else -1)))
    tl = sorted({t for r in rows for t in r[:2]})
    ix = {t: i for i, t in enumerate(tl)}
    n = len(tl)
    A = np.zeros((n + 1, n + 1)); b = np.zeros(n + 1)
    for a_, b_, m, h in rows:
        i, j = ix[a_], ix[b_]
        x = np.zeros(n + 1); x[i] = 1; x[j] = -1; x[n] = h
        A += np.outer(x, x); b += x * m
    A[np.arange(n), np.arange(n)] += LAM
    A[n, n] += 1.0
    A[:n, :n] += 1e-6                                 # anchor mean to 0
    sol = np.linalg.solve(A, b)
    sol[:n] -= sol[:n].mean()
    for t, i in ix.items():
        arch[(ssn, t)] = float(sol[i])
    if ssn in ("2005-06", "2018-19"):
        top = sorted(tl, key=lambda t: -arch[(ssn, t)])[:8]
        print(ssn, "hca=%.2f" % sol[n], "top8:", [(t, round(arch[(ssn, t)], 1)) for t in top])

# ---- Torvik end-of-season ratings -------------------------------------------
tor = {}                                             # (season, key) -> (barthag, rank)
for fp in sorted(glob.glob("/Users/kennakao/nba/datarebuild/tracking_raw/torvik_team_*.csv")):
    y = int(fp[-8:-4]); ssn = "%d-%02d" % (y - 1, y % 100)
    for r in csv.DictReader(open(fp, errors="ignore")):
        try:
            tor[(ssn, TM.ekey(r["team"]))] = (float(r["barthag"]), int(r["rank"]))
        except Exception:
            pass
print("torvik team-seasons loaded", len(tor))

# ---- unify ------------------------------------------------------------------
out = []
seasons = sorted({s for s, _ in arch})
agree = []
for ssn in seasons:
    ts = sorted([t for (s, t) in arch if s == ssn])
    a_rank = {t: i + 1 for i, t in enumerate(sorted(ts, key=lambda t: -arch[(ssn, t)]))}
    have_tor = {t: tor.get((ssn, TM.key(t))) for t in ts}
    n_tor = sum(1 for v in have_tor.values() if v)
    use_tor = n_tor > 0.8 * len(ts)
    if use_tor:
        # rank within this season's mapped Torvik teams by barthag
        mapped = [t for t in ts if have_tor[t]]
        order = sorted(mapped, key=lambda t: -have_tor[t][0])
        rk = {t: i + 1 for i, t in enumerate(order)}
        r1 = [rk[t] for t in mapped]; r2 = [a_rank[t] for t in mapped]
        agree.append((ssn, n_tor, len(ts), np.corrcoef(np.argsort(np.argsort(r1)),
                                                       np.argsort(np.argsort(r2)))[0, 1],
                      len(set(sorted(mapped, key=lambda t: rk[t])[:50])
                          & set(sorted(mapped, key=lambda t: a_rank[t])[:50])),
                      len(set(sorted(mapped, key=lambda t: rk[t])[:100])
                          & set(sorted(mapped, key=lambda t: a_rank[t])[:100]))))
    for t in ts:
        tv = have_tor[t]
        if use_tor and tv:
            out.append(dict(season=ssn, team=t, rank=rk[t], rating=round(tv[0], 5),
                            src="torvik", arch_rank=a_rank[t], arch_rating=round(arch[(ssn, t)], 3)))
        elif use_tor:
            out.append(dict(season=ssn, team=t, rank=999, rating="",
                            src="unrated", arch_rank=a_rank[t], arch_rating=round(arch[(ssn, t)], 3)))
        else:
            out.append(dict(season=ssn, team=t, rank=a_rank[t], rating=round(arch[(ssn, t)], 3),
                            src="archive", arch_rank=a_rank[t], arch_rating=round(arch[(ssn, t)], 3)))

with open(f"{D}/work/team_ratings.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["season", "team", "rank", "rating", "src", "arch_rank", "arch_rating"])
    w.writeheader(); w.writerows(out)

print("\nseason  torvik/total  spearman(torvik,archive)  top50-overlap  top100-overlap")
for a in agree:
    print("%s  %3d/%3d  %.3f  %2d/50  %3d/100" % a)
bad = [o for o in out if o["src"] == "unrated" and o["arch_rank"] <= 110]
print("\nunrated-but-archive-top-110 (would mis-tier):", [(o['season'], o['team'], o['arch_rank']) for o in bad])
print("team_ratings rows", len(out))
