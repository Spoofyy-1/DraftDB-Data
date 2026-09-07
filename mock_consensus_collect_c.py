"""Dated multi-publisher mock consensus, 2015-2026: for each site and draft year, the LAST Wayback snapshot captured in the 21 days
before draft day (strictly before). Names are matched in order of first appearance against that class's prospect universe
(identity file rows with draft_year == Y); rank = order of appearance. Sanity per site/year: count and Spearman vs actual pick
(diagnostic of the scrape only). Output: mock_raw/consensus2/*.html cached; mock_consensus2_ranks.csv (pid, draft_year, site, rank, ts)."""
import json,os,re,time,csv,unicodedata,urllib.parse,subprocess,collections
H="/Users/kennakao/Downloads/nba_redraft_handoff"
DRAFT={2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
SITES={"tankathon":"tankathon.com/mock_draft","nbadraft":"www.nbadraft.net/nba-mock-drafts/","cbs":"www.cbssports.com/nba/draft/mock-draft/","draftroom":"www.nbadraftroom.com/p/{y}-nba-mock-draft","hoopshype":"hoopshype.com/nba-mock-draft/",
       "draftroom2":"nbadraftroom.com/p/{y}-nba-mock-draft/","espn_ba":"www.espn.com/nba/draft/bestavailable","espn_ba2":"www.espn.com/nba/draft/bestavailable/_/position/ovr/page/2","ringer":"nbadraft.theringer.com/mock-draft","sportingnews":"www.sportingnews.com/us/nba/news/nba-mock-draft-{y}*"}
def norm(s): return re.sub(r"\s+"," ",re.sub(r"[^a-z ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower().replace(".",""))).strip()
def strip_suffix(n): return re.sub(r"\b(jr|sr|ii|iii|iv)\b","",n).replace("  "," ").strip()
ids=list(csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")))
uni=collections.defaultdict(dict)
for r in ids: uni[int(float(r["draft_year"]))][strip_suffix(norm(r["player_name"]))]=(r["pid"],r.get("actual_pick",""))
def fetch(url,out,timeout=40):
    if os.path.exists(out) and os.path.getsize(out)>500: return open(out,errors="ignore").read()
    subprocess.run(["curl","-s","-L","-m",str(timeout),"-A","Mozilla/5.0 DraftDB-research (mike@alphax.inc)","-o",out,url]); time.sleep(1.5)
    return open(out,errors="ignore").read() if os.path.exists(out) else ""
rows=[]; report=[]
for y,d in [(yy,DRAFT[yy]) for yy in (2023,2025,2018,2015)]:
    dd=d.replace("-",""); start=(int(dd[:4]),dd); 
    import datetime as dt; D=dt.datetime.strptime(d,"%Y-%m-%d"); frm=(D-dt.timedelta(days=40)).strftime("%Y%m%d"); to=(D-dt.timedelta(days=1)).strftime("%Y%m%d")+"235959"
    for site,pat in SITES.items():
        u=pat.format(y=y); cdx=fetch(f"https://web.archive.org/cdx/search/cdx?url={urllib.parse.quote(u)}&from={frm}&to={to}&output=json&filter=statuscode:200&fl=timestamp,original&limit=-1",f"mock_raw/consensus2/cdx40_{site}_{y}.json")
        try: snaps=[(x[0],x[1]) for x in json.loads(cdx)[1:]]
        except Exception: snaps=[]
        if not snaps: report.append((y,site,"no snapshot")); continue
        if u.endswith("*"): snaps=sorted(snaps,key=lambda x:("final" in x[1],x[0]))   # prefer the 'final' mock, then the latest capture
        ts,orig=snaps[-1]; html=fetch(f"https://web.archive.org/web/{ts}id_/{orig}",f"mock_raw/consensus2/snap_{site}_{y}_{ts}.html",60)
        text=re.sub(r"<[^>]+>"," ",html); text=re.sub(r"&amp;","&",text); tn=norm(text)
        found=[]; seen=set()
        # first appearance of each class member's normalized full name in the page text
        pos=[]
        for nm,(pid,pk) in uni[y].items():
            if len(nm.split())<2: continue
            i=tn.find(" "+nm+" ")
            if i>=0: pos.append((i,pid,pk))
        pos.sort()
        for k,(i,pid,pk) in enumerate(pos,1): rows.append(dict(pid=pid,draft_year=y,site=site,rank=k,ts=ts))
        picks=[(k,float(pk)) for k,(i,pid,pk) in enumerate(pos,1) if pk not in ("","nan")]
        rho=None
        if len(picks)>=10:
            import statistics as st
            a=[p[0] for p in picks]; b=[p[1] for p in picks]; ra=sorted(range(len(a)),key=lambda i:a[i]); rb=sorted(range(len(b)),key=lambda i:b[i])
            ranka=[0]*len(a); rankb=[0]*len(b)
            for r_,i in enumerate(ra): ranka[i]=r_
            for r_,i in enumerate(rb): rankb[i]=r_
            n=len(a); rho=1-6*sum((ranka[i]-rankb[i])**2 for i in range(n))/(n*(n*n-1))
        report.append((y,site,f"{len(pos)} names, {len(picks)} drafted, rho vs pick {rho if rho is None else round(rho,2)}, snapshot {ts[:8]}"))
w=csv.DictWriter(open("mock_consensus2_ranks_c.csv","w"),fieldnames=["pid","draft_year","site","rank","ts"]); w.writeheader(); [w.writerow(r) for r in rows]
for r in report: print(r)
print("MOCK2_DONE rows",len(rows))
