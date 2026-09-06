"""G League (NBA G League / D-League) player season totals + advanced, all seasons, from the public stats API used by
stats.gleague.nba.com (LeagueID=20). One request per season per measure type; cached. Names stay local (Mac)."""
import json,os,time,subprocess,sys
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(url,out):
    r=subprocess.run(["curl","-s","--http1.1","-m","60","-H",f"User-Agent: {UA}","-H","Referer: https://stats.gleague.nba.com/","-H","Origin: https://stats.gleague.nba.com","-H","x-nba-stats-origin: stats","-H","x-nba-stats-token: true","-H","Accept: application/json, text/plain, */*","-o",out,url])
    return os.path.getsize(out) if os.path.exists(out) else 0
seasons=[f"{y}-{str(y+1)[2:]}" for y in range(2002,2026)]
for s in seasons:
    for mt in ("Base","Advanced"):
        out=f"gleague_raw/gl_{mt.lower()}_{s}.json"
        if os.path.exists(out) and os.path.getsize(out)>1000: continue
        url=f"https://stats.gleague.nba.com/stats/leaguedashplayerstats?LeagueID=20&Season={s}&SeasonType=Regular%20Season&PerMode=Totals&MeasureType={mt}&PlusMinus=N&PaceAdjust=N&Rank=N&Month=0&OpponentTeamID=0&Period=0&LastNGames=0&TeamID=0&PORound=0"
        n=get(url,out)
        try: rows=len(json.load(open(out))["resultSets"][0]["rowSet"])
        except Exception: rows=-1
        print(s,mt,"bytes",n,"rows",rows,flush=True); time.sleep(2.5)
print("GL_DONE",flush=True)
