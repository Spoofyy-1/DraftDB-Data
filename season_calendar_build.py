"""season_calendar.csv: pid, ordinal (1..8), season_start_year, minutes - the calendar year of each player's i-th NBA regular
season (ordinal = seasons actually played, matching how the handoff's y_s{i} outcomes are indexed). Players with no NBA season
are absent (their outcomes are all-missing/zero by construction)."""
import json,glob,csv,re
rows=[]; n=0
for fp in glob.glob("calendar_raw/career_*.json"):
    pid=re.search(r"career_(P[0-9a-f]+)",fp).group(1)
    try: d=json.load(open(fp)); rs=[x for x in d["resultSets"] if x["name"]=="SeasonTotalsRegularSeason"][0]
    except Exception: continue
    h=rs["headers"]; seasons={}
    for r in rs["rowSet"]:
        x=dict(zip(h,r)); sid=str(x.get("SEASON_ID","")); y=int(sid[:4]) if re.match(r"\d{4}",sid) else None
        if y is None: continue
        seasons[y]=seasons.get(y,0)+float(x.get("MIN") or 0)   # TOT rows and team rows share the season; minutes summed conservatively
    n+=1
    for i,y in enumerate(sorted(seasons),1):
        if i<=8: rows.append(dict(pid=pid,ordinal=i,season_start_year=y,minutes=round(seasons[y],1)))
w=csv.DictWriter(open("season_calendar.csv","w"),fieldnames=["pid","ordinal","season_start_year","minutes"]); w.writeheader(); [w.writerow(r) for r in rows]
print("players parsed:",n,"season rows:",len(rows))
