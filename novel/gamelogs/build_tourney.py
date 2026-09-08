"""NCAA tournament games, team seeds and seed-expected wins.

Field + seeds come from the Wikipedia bracket templates (work/seeds.csv, see fetch_seeds.py),
mapped to archive team directories with teams.ekey.  A tournament game is any archive game
played on/after Selection Sunday + 2 days (First Four Tuesday) in which BOTH sides are in that
year's field -- conference tournaments finish on Selection Sunday and NIT/CBI/CIT fields are
disjoint from the NCAA field, so no date-window guessing is needed.
Selection Sunday = the unique Sunday in [Mar 11, Mar 17] of the season-ending year.

Seed -> expected wins ("PASE") is estimated on PRIOR tournaments ONLY: for a tournament in year Y the
table is the mean wins per seed over every detected tournament with year < Y (leave-future-out), so the
feature for a player drafted in year Y uses nothing from year Y or later.  Seasons with fewer than
3 prior tournaments fall back to the historical 1985-2002 seed means shipped in PRIOR_SEED_WINS.
Outputs: work/tourney_games.csv, work/tourney_team.csv
"""
import csv, gzip, collections, datetime as dt, sys
sys.path.insert(0, "/Users/kennakao/nba/datarebuild/novel/gamelogs")
import teams as TM

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"

# published seed averages for the 64-team era before our data starts (1985-2002), used only as the
# prior for the first few seasons; superseded as soon as 3+ observed tournaments are available.
PRIOR_SEED_WINS = {1: 3.30, 2: 2.35, 3: 1.80, 4: 1.55, 5: 1.15, 6: 1.10, 7: 0.90, 8: 0.70,
                   9: 0.55, 10: 0.65, 11: 0.60, 12: 0.50, 13: 0.25, 14: 0.15, 15: 0.05, 16: 0.00}

def selection_sunday(y):
    for d in range(11, 18):
        x = dt.date(y, 3, d)
        if x.weekday() == 6: return x

games = list(csv.DictReader(gzip.open(f"{D}/work/games.csv.gz", "rt")))
by = collections.defaultdict(dict)
for g in games: by[g["season"]].setdefault(g["game_id"], []).append(g)
dirs = collections.defaultdict(dict)
for g in games: dirs[g["season"]].setdefault(TM.key(g["team"]), g["team"])

seeds = collections.defaultdict(dict)          # season -> team_dir -> seed
for r in csv.DictReader(open(f"{D}/work/seeds.csv")):
    y = int(r["year"]); ssn = "%d-%02d" % (y - 1, y % 100)
    d = dirs.get(ssn, {}).get(TM.ekey(r["team_wiki"]))
    if d: seeds[ssn][d] = int(r["seed"])

tg_rows, team_rows, report = [], [], []
for ssn in sorted(by):
    y = int(ssn[:4]) + 1
    field = seeds.get(ssn, {})
    if len(field) < 40:
        report.append((ssn, len(field), 0, 0, "", "")); continue
    start = selection_sunday(y) + dt.timedelta(2)
    tg = []
    for gid, rs in by[ssn].items():
        if len(rs) != 2: continue
        if rs[0]["date"] < start.isoformat(): continue
        if rs[0]["team"] not in field or rs[1]["team"] not in field: continue
        tg.append((gid, rs[0]["date"], rs))
    if not tg:
        report.append((ssn, len(field), 0, 0, "", "")); continue
    dates = sorted({d for _, d, _ in tg})
    fin, sf = dates[-1], (dates[-2] if len(dates) > 1 else None)
    agg = collections.defaultdict(lambda: dict(g=0, w=0, f4=0, ch=0))
    for gid, d, rs in tg:
        for i, r in enumerate(rs):
            o = rs[1 - i]
            try: won = int(int(float(r["ts"])) > int(float(r["os"])))
            except Exception: won = 0
            tg_rows.append(dict(season=ssn, game_id=gid, date=d, team=r["team"], opp=o["team"],
                                won=won, is_final4=int(d in (sf, fin)), is_final=int(d == fin)))
            a = agg[r["team"]]; a["g"] += 1; a["w"] += won
            if d in (sf, fin): a["f4"] = 1
            if d == fin and won: a["ch"] = 1
    for t, a in agg.items():
        team_rows.append(dict(season=ssn, year=y, team=t, seed=field[t], games=a["g"], wins=a["w"],
                              final4=a["f4"], champion=a["ch"]))
    report.append((ssn, len(field), len(agg), len(tg), dates[0], dates[-1]))

# leave-future-out seed -> expected wins
hist = collections.defaultdict(list)
for r in sorted(team_rows, key=lambda r: r["year"]):
    hist[(r["year"], r["seed"])] = hist[(r["year"], r["seed"])]
years = sorted({r["year"] for r in team_rows})
for r in team_rows:
    prior = [x for x in team_rows if x["year"] < r["year"] and x["seed"] == r["seed"]]
    ny = len({x["year"] for x in team_rows if x["year"] < r["year"]})
    if ny >= 3 and prior:
        exp = sum(x["wins"] for x in prior) / len(prior); src = "prior_%dy" % ny
    else:
        exp = PRIOR_SEED_WINS.get(r["seed"], 0.5); src = "prior_table"
    r["exp_wins"] = round(exp, 4); r["pase"] = round(r["wins"] - exp, 4); r["exp_src"] = src

with open(f"{D}/work/tourney_games.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["season","game_id","date","team","opp","won","is_final4","is_final"])
    w.writeheader(); w.writerows(tg_rows)
with open(f"{D}/work/tourney_team.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["season","year","team","seed","games","wins","final4",
                                       "champion","exp_wins","pase","exp_src"])
    w.writeheader(); w.writerows(team_rows)

print("season   seeded  teams-played  games  first        last")
for r in report: print("%s  %4d  %4d  %4d  %-11s  %-11s" % r)
ch = [(r["season"], r["team"]) for r in team_rows if r["champion"]]
print("\ndetected champions:", ch)
print("team rows", len(team_rows), "game rows", len(tg_rows))
