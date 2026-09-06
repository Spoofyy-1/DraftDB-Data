"""Mock-draft momentum from dated Wayback Machine snapshots of nbadraft.net's public mock (Nov -> draft night).
For each class: ~6 snapshots across the season -> per-player rank trajectory -> pid-keyed features. Names stay on the Mac.
Wayback is flaky: every request retries with backoff; everything is cached under mock_raw/."""
import json,os,re,time,csv,html,urllib.request,urllib.parse,unicodedata,collections,datetime as dt
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}; H="/Users/kennakao/Downloads/nba_redraft_handoff"
DRAFT={2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
def fetch(url,tries=8):
    for i in range(tries):
        try:
            time.sleep(1.5)
            with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=60) as r: b=r.read().decode("utf-8","ignore")
            if "Temporarily Offline" in b[:600] or "Verifying your browser" in b[:2000]: raise RuntimeError("offline")
            return b
        except Exception as e:
            time.sleep(min(300,20*(2**i)))
    return None
def norm(s): return re.sub(r"[^a-z0-9 ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()).strip()
def cdx(year):
    p=f"mock_raw/cdx_{year}.json"
    if os.path.exists(p): return json.load(open(p))
    start=dt.datetime.strptime(DRAFT[year],"%Y-%m-%d")-dt.timedelta(days=240); end=dt.datetime.strptime(DRAFT[year],"%Y-%m-%d")
    urls=["nbadraft.net/nba-mock-drafts/","nbadraft.net/nba_mock_drafts/","nbadraft.net/nba-mock-draft/","nbadraft.net/nba_mock_draft/"]
    rows=[]
    for u in urls:
        b=fetch(f"https://web.archive.org/cdx/search/cdx?url={urllib.parse.quote(u)}&from={start:%Y%m%d}&to={end:%Y%m%d}&output=json&filter=statuscode:200&collapse=timestamp:8&limit=400")
        if b and b.startswith("["):
            try: rows+=json.loads(b)[1:]
            except Exception: pass
    json.dump(rows,open(p,"w")); return rows
def parse(htm):
    out=[]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",htm,re.S):
        cells=[html.unescape(re.sub(r"<[^>]+>"," ",c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",tr,re.S)]
        if len(cells)>=3 and re.fullmatch(r"\d{1,2}",cells[0]):
            name=next((c for c in cells[1:4] if re.fullmatch(r"[A-Za-z' .\-]{4,40}",c) and " " in c and not re.search(r"^\*",c)),None)
            # nbadraft tables: [#, Team, Player, H, W, P, School, C]; older layouts differ, so take the first two-word name cell after the pick
            if name: out.append((int(cells[0]),re.sub(r"\s+"," ",name)))
    return out
ids=collections.defaultdict(dict)
for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")): ids[int(float(r["draft_year"]))][norm(r["player_name"])]=r["pid"]
def match(year,name):
    n=norm(name); d=ids.get(year,{})
    if n in d: return d[n]
    last=n.split()[-1] if n else ""; cands=[k for k in d if k.split()[-1]==last and k.split()[0][:3]==n.split()[0][:3]]
    return d[cands[0]] if len(cands)==1 else None
feats={}; log=collections.Counter()
for year in range(2010,2027):
    rows=cdx(year)
    if not rows: log[f"{year}:no_cdx"]+=1; print(year,"no snapshots",flush=True); continue
    # pick up to 7 snapshots spread over the season
    rows.sort(key=lambda r:r[1]); step=max(1,len(rows)//7); picks=rows[::step][:7]
    if rows[-1] not in picks: picks.append(rows[-1])
    traj=collections.defaultdict(dict); d0=dt.datetime.strptime(DRAFT[year],"%Y-%m-%d"); nsnap=0
    for r in picks:
        ts,orig=r[1],r[2]; p=f"mock_raw/snap_{year}_{ts}.html"
        if not os.path.exists(p):
            b=fetch(f"https://web.archive.org/web/{ts}id_/{orig}")
            if not b: continue
            open(p,"w").write(b)
        table=parse(open(p).read())
        if len(table)<20: continue
        nsnap+=1; days=(d0-dt.datetime.strptime(ts[:8],"%Y%m%d")).days
        for rank,name in table:
            pid=match(year,name)
            if pid: traj[pid][days]=rank
            else: log["unmatched"]+=1
    for pid,t in traj.items():
        ds=sorted(t,reverse=True); ranks=[t[d] for d in ds]     # oldest -> newest
        late=[t[d] for d in ds if d<=60]; early=[t[d] for d in ds if d>=120]
        feats[pid]=dict(pid=pid,mock_snaps=nsnap,mock_listed=len(ranks),mock_first=ranks[0],mock_first_days=ds[0],mock_last=ranks[-1],mock_last_days=ds[-1],mock_best=min(ranks),mock_worst=max(ranks),
                        mock_mean=round(sum(ranks)/len(ranks),2),mock_std=round((sum((x-sum(ranks)/len(ranks))**2 for x in ranks)/len(ranks))**.5,2),
                        mock_delta=ranks[-1]-ranks[0],mock_delta_late=(late[-1]-early[-1]) if late and early else None,mock_share=round(len(ranks)/nsnap,2) if nsnap else None)
    print(f"{year}: snapshots {nsnap} players matched {len(traj)}",flush=True)
cols=["pid","mock_snaps","mock_listed","mock_first","mock_first_days","mock_last","mock_last_days","mock_best","mock_worst","mock_mean","mock_std","mock_delta","mock_delta_late","mock_share"]
with open("mock_features.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); [w.writerow(v) for v in feats.values()]
print("features:",len(feats),"log:",dict(log),flush=True); print("MOCK_DONE")
