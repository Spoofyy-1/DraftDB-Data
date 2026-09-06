"""'Weird data' collector, all dated before draft night, all from Wikimedia APIs (CC BY-SA, open):
  - attention: how long the player's article existed before the draft, how many edits/editors in the 90/365 days before,
    article size the night before, daily pageviews in the 90 days before (2016+ classes)
  - pedigree facts from the infobox (college teams, high school, birthplace, relatives) for program/hometown features
Runs on the Mac (names live here). Output per pid in wiki_raw/attn_{pid}.json; no names leave this machine."""
import json,os,re,time,csv,glob,urllib.request,urllib.parse,unicodedata,collections,datetime as dt
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}; API="https://en.wikipedia.org/w/api.php"
PV="https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{t}/daily/{a}/{b}"
H="/Users/kennakao/Downloads/nba_redraft_handoff"; SLEEP=0.4
DRAFT={2000:"2000-06-28",2001:"2001-06-27",2002:"2002-06-26",2003:"2003-06-26",2004:"2004-06-24",2005:"2005-06-28",2006:"2006-06-28",2007:"2007-06-28",2008:"2008-06-26",2009:"2009-06-25",2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
def call(url):
    time.sleep(SLEEP)
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r: return json.load(r)
def api(params): return call(API+"?"+urllib.parse.urlencode(dict(params,format="json")))
def norm(s): return re.sub(r"[^a-z0-9 ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower())
names={r["pid"]:r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv"))}
rows=[]
for r in csv.DictReader(open(f"{H}/data/train_2000_2018.csv")):
    if 2000<=int(float(r["draft_year"]))<=2018: rows.append((r["pid"],int(float(r["draft_year"])),r.get("actual_pick","")))
for fp in sorted(glob.glob(f"{H}/data/tests/test_*_inputs.csv")):
    yr=int(re.search(r"test_(\d{4})",fp).group(1))
    for r in csv.DictReader(open(fp)): rows.append((r["pid"],yr,"1" if r.get("was_drafted") in("1","1.0") else ""))
rows=[x for x in rows if x[0] in names]; rows.sort(key=lambda x:(x[2]=="",x[1]))   # drafted players first
print("universe:",len(rows),"pids",flush=True); c=collections.Counter()
exec(open("traj_features.py").read().split('if __name__=="__main__":')[0]); _rows_from=rows_from
def infobox(wt):
    out={}
    for k in("college","high_school","birth_place","relatives","nationality","position","draft_year","career_start"):
        m=re.search(r"\|\s*"+k+r"\s*=\s*(.+)",wt or "")
        if m: out[k]=re.sub(r"<ref.*?(/>|</ref>)","",m.group(1)).strip()[:300]
    return out
for n,(pid,dy,drafted) in enumerate(rows,1):
    out=f"wiki_raw/attn_{pid}.json"
    if os.path.exists(out): c["cached"]+=1; continue
    rec=dict(pid=pid,draft_year=dy,draft_date=DRAFT[dy])
    try:
        sp=f"wiki_raw/search_{pid}.json"
        if os.path.exists(sp): hits=json.load(open(sp)).get("query",{}).get("search",[])
        else:
            hits=api(dict(action="query",list="search",srsearch=names[pid]["player_name"]+" basketball",srlimit=3)).get("query",{}).get("search",[]); json.dump({"query":{"search":hits}},open(sp,"w"))
        title=None
        for h in hits:
            if norm(names[pid]["player_name"].split()[-1]) in norm(h["title"]): title=h["title"]; break
        if not title: rec.update(status="no_page",wp_exists=0); json.dump(rec,open(out,"w")); c["no_page"]+=1; continue
        rec["title"]=title
        # ---- pre-draft revision history (oldest -> draft night)
        revs=[]; cont={}
        while True:
            q=api(dict(action="query",prop="revisions",titles=title,rvlimit="max",rvdir="newer",rvend=DRAFT[dy]+"T00:00:00Z",rvprop="timestamp|user|size",**cont))
            pg=list(q.get("query",{}).get("pages",{}).values())
            revs+=pg[0].get("revisions",[]) if pg else []
            if "continue" in q and len(revs)<3000: cont=q["continue"]
            else: break
        d0=dt.datetime.strptime(DRAFT[dy],"%Y-%m-%d")
        if not revs: rec.update(status="no_predraft_article",wp_exists=0)
        else:
            ts=[dt.datetime.strptime(r["timestamp"],"%Y-%m-%dT%H:%M:%SZ") for r in revs]
            rec.update(status="ok",wp_exists=1,wp_created_days_before=(d0-ts[0]).days,wp_revs_pre=len(revs),
                       wp_revs_90d=sum(1 for t in ts if (d0-t).days<=90),wp_revs_365d=sum(1 for t in ts if (d0-t).days<=365),
                       wp_editors_90d=len({r.get("user") for r,t in zip(revs,ts) if (d0-t).days<=90}),wp_editors_pre=len({r.get("user") for r in revs}),
                       wp_size_pre=revs[-1].get("size"),wp_size_365d_ago=next((r.get("size") for r,t in zip(revs,ts) if (d0-t).days<=365),None))
            if dy>=2016:
                try:
                    a=(d0-dt.timedelta(days=90)).strftime("%Y%m%d"); b=(d0-dt.timedelta(days=1)).strftime("%Y%m%d")
                    pv=call(PV.format(t=urllib.parse.quote(title.replace(" ","_"),safe=""),a=a,b=b)).get("items",[])
                    v=[x["views"] for x in pv]; v30=[x["views"] for x in pv if x["timestamp"]>=(d0-dt.timedelta(days=30)).strftime("%Y%m%d00")]
                    rec.update(wp_views_90d=sum(v),wp_views_30d=sum(v30),wp_views_peak=max(v) if v else 0,wp_views_days=len(v))
                except Exception as e: rec["views_err"]=repr(e)[:60]
        # ---- infobox facts (current text; the facts themselves are pre-draft)
        try:
            wt=api(dict(action="parse",page=title,prop="wikitext",redirects=1)).get("parse",{}).get("wikitext",{}).get("*","")
            rec["infobox"]=infobox(wt); rec["career_rows"]=_rows_from(wt)
        except Exception as e: rec["infobox_err"]=repr(e)[:60]
        json.dump(rec,open(out,"w")); c[rec["status"]]+=1
    except Exception as e:
        rec.update(status="err",err=repr(e)[:100]); json.dump(rec,open(out,"w")); c["err"]+=1
    if n%50==0: print(f"{n}/{len(rows)} {dict(c)}",flush=True)
print("status:",dict(c),flush=True); print("ATTN_DONE")
