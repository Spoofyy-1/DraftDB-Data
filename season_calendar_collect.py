"""NBA season calendar per player (which calendar seasons each player actually played, with minutes) from the stats API via the
G League host, for every pid with an nba_id in the identity file. Purpose: map ordinal outcome seasons (y_s1..y_s5) to calendar
years so expanding-window and fold labels only use seasons completed before the scored draft. Cached per player."""
import json,os,time,subprocess,csv,random
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
H="/Users/kennakao/Downloads/nba_redraft_handoff"
def get(url,out):
    subprocess.run(["curl","-s","--http1.1","-m","40","-H",f"User-Agent: {UA}","-H","Referer: https://www.nba.com/","-H","Origin: https://www.nba.com","-H","x-nba-stats-origin: stats","-H","x-nba-stats-token: true","-H","Accept: application/json, text/plain, */*","-o",out,url])
    return os.path.getsize(out) if os.path.exists(out) else 0
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")) if r.get("nba_id") not in ("","nan",None)]
ids.sort(key=lambda r:-int(float(r["draft_year"])))
SH=int(os.environ.get("SHARD","0")); NS=int(os.environ.get("NSHARD","1")); ids=[r for k,r in enumerate(ids) if k%NS==SH]
print("players with nba_id:",len(ids),flush=True); n=0; bad=0
for r in ids:
    nid=str(r["nba_id"]).split(".")[0]; out=f"calendar_raw/career_{r['pid']}.json"
    if os.path.exists(out) and os.path.getsize(out)>200: continue
    sz=get(f"https://stats.gleague.nba.com/stats/playercareerstats?PlayerID={nid}&LeagueID=00&PerMode=Totals",out)
    try: d=json.load(open(out)); rs=[x for x in d["resultSets"] if x["name"]=="SeasonTotalsRegularSeason"][0]; ok=len(rs["rowSet"])>=0
    except Exception: ok=False; bad+=1
    n+=1
    if n%100==0: print(f"{n} done, parse failures {bad}",flush=True)
    time.sleep(1.5+random.random()*1.0)
    if bad>=200: print("too many failures, stopping",flush=True); break
print("CALENDAR_DONE",n,bad,flush=True)
