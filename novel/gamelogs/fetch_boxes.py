"""Fetch only the box-score directories we need from the blobless ncaahoopR_data clone,
season by season (git sparse-checkout cone mode = one batched packfile fetch per season),
consolidate each season into raw/box_<season>.csv.gz, then prune the working tree.
Resumable: a season whose raw/box_<season>.csv.gz exists is skipped."""
import csv, glob, gzip, os, subprocess, sys, time, collections

D = "/Users/kennakao/nba/datarebuild/novel/gamelogs"
R = f"{D}/raw/ncaa_repo"
COLS = ["player","position","MIN","FGM","FGA","3PTM","3PTA","FTM","FTA","OREB","DREB","REB",
        "AST","STL","BLK","TO","PF","PTS","starter","date","opponent","location"]

need = collections.defaultdict(set)
for r in csv.DictReader(open(f"{D}/work/player_seasons.csv")):
    need[r["season"]].add(r["team"])
have = collections.defaultdict(set)
for line in open(f"{D}/raw/tree.txt"):
    p = line.strip().split("/")
    if len(p) == 4 and p[1] == "box_scores":
        have[p[0]].add(p[2])

def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=R, check=True, capture_output=True, text=True, **kw)

sh(["git", "sparse-checkout", "init", "--cone"])
for ssn in sorted(need):
    out = f"{D}/raw/box_{ssn}.csv.gz"
    if os.path.exists(out):
        print(f"[{time.strftime('%H:%M:%S')}] cached {ssn}", flush=True); continue
    dirs = sorted(need[ssn] & have.get(ssn, set()))
    if not dirs:
        gzip.open(out, "wt").write("season,team,game_id," + ",".join(COLS) + "\n")
        print(f"[{time.strftime('%H:%M:%S')}] {ssn}: no box dirs in archive", flush=True); continue
    t0 = time.time()
    sh(["git", "sparse-checkout", "set", "--stdin"],
       input="\n".join(f"{ssn}/box_scores/{d}" for d in dirs) + "\n")
    sh(["git", "checkout", "--", "."])
    nf = nr = 0
    with gzip.open(out + ".part", "wt", newline="") as fh:
        w = csv.writer(fh); w.writerow(["season", "team", "game_id"] + COLS)
        for d in dirs:
            for fp in sorted(glob.glob(f"{R}/{ssn}/box_scores/{d}/*.csv")):
                gid = os.path.basename(fp)[:-4]; nf += 1
                try:
                    rd = csv.DictReader(open(fp, errors="ignore"))
                    if not rd.fieldnames: continue
                    for row in rd:
                        w.writerow([ssn, d, gid] + [row.get(c, "") for c in COLS]); nr += 1
                except Exception as e:
                    print("  ERR", fp, e, flush=True)
    os.replace(out + ".part", out)
    sh(["git", "sparse-checkout", "set", "--stdin"], input="README.md\n")
    subprocess.run(["rm", "-rf", f"{R}/{ssn}"], check=False)
    print(f"[{time.strftime('%H:%M:%S')}] {ssn}: {len(dirs)} teams, {nf} games, {nr} rows, "
          f"{time.time()-t0:.0f}s, gz={os.path.getsize(out)//1024}KB", flush=True)
print("FETCH_DONE", flush=True)
