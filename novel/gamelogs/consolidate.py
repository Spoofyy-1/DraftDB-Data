"""Consolidate ncaahoopR_data schedules + rosters (sparse checkout) into compact gz bundles under raw/."""
import csv, glob, gzip, os, re, sys
D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
R = D + "/raw/ncaa_repo"

def bundle(kind, suffix, cols, out):
    n = 0
    with gzip.open(out, "wt", newline="") as fh:
        w = csv.writer(fh); w.writerow(["season", "team"] + cols)
        for p in sorted(glob.glob(f"{R}/*/{kind}/*{suffix}")):
            parts = p.split("/"); season = parts[-3]
            team = os.path.basename(p)[: -len(suffix)]
            try:
                rd = csv.DictReader(open(p, errors="ignore"))
                if not rd.fieldnames: continue
                for row in rd:
                    w.writerow([season, team] + [row.get(c, "") for c in cols]); n += 1
            except Exception as e:
                print("ERR", p, e, file=sys.stderr)
    print(kind, "rows", n, "->", out)

bundle("schedules", "_schedule.csv",
       ["game_id", "date", "opponent", "location", "team_score", "opp_score"],
       D + "/raw/schedules.csv.gz")
bundle("rosters", "_roster.csv",
       ["number", "name", "position", "height", "weight", "class", "hometown"],
       D + "/raw/rosters.csv.gz")
