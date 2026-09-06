"""Pre-draft text snapshots: for every drafted player 2010-2026, the English Wikipedia article revision that existed
the day BEFORE his draft (leak-proof by timestamp). Runs on the Mac (names live here), 1 req/s, cached, output cached
per pid. Later step: an LLM scores each snapshot into numeric features (hype, injury language, role projection)."""
import json,os,re,time,csv,urllib.request,urllib.parse,unicodedata,collections
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}; API="https://en.wikipedia.org/w/api.php"
H="/Users/kennakao/Downloads/nba_redraft_handoff"
DRAFT={2000:"2000-06-28",2001:"2001-06-27",2002:"2002-06-26",2003:"2003-06-26",2004:"2004-06-24",2005:"2005-06-28",2006:"2006-06-28",2007:"2007-06-28",2008:"2008-06-26",2009:"2009-06-25",2010:"2010-06-24",2011:"2011-06-23",2012:"2012-06-28",2013:"2013-06-27",2014:"2014-06-26",2015:"2015-06-25",2016:"2016-06-23",2017:"2017-06-22",2018:"2018-06-21",2019:"2019-06-20",2020:"2020-11-18",2021:"2021-07-29",2022:"2022-06-23",2023:"2023-06-22",2024:"2024-06-26",2025:"2025-06-25",2026:"2026-06-24"}
def get(params,fn):
    p=f"wiki_raw/{fn}"
    if os.path.exists(p): return json.load(open(p))
    time.sleep(1.0); url=API+"?"+urllib.parse.urlencode(dict(params,format="json"))
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r: d=json.load(r)
    json.dump(d,open(p,"w")); return d
def norm(s): return re.sub(r"[^a-z0-9 ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower())
ids=[r for r in csv.DictReader(open(f"{H}/identity_KEEP_SEPARATE/tabular_names.csv")) if r.get("actual_pick") not in("","nan",None) and 2000<=int(float(r["draft_year"]))<=2026]
print("drafted players 2010-2026:",len(ids),flush=True); res={}; c=collections.Counter()
for n,t in enumerate(ids,1):
    pid=t["pid"]; dy=int(float(t["draft_year"])); out=f"wiki_raw/prerev_{pid}.json"
    if os.path.exists(out): c["cached"]+=1; continue
    try:
        title=None
        sp=f"wiki_raw/search_{pid}.json"
        if os.path.exists(sp): hits=json.load(open(sp)).get("query",{}).get("search",[])
        else: hits=get(dict(action="query",list="search",srsearch=t["player_name"]+" basketball",srlimit=3),f"search_{pid}.json").get("query",{}).get("search",[])
        for h in hits:
            if norm(t["player_name"].split()[-1]) in norm(h["title"]): title=h["title"]; break
        if not title: json.dump(dict(status="no_page"),open(out,"w")); c["no_page"]+=1; continue
        rv=get(dict(action="query",prop="revisions",titles=title,rvlimit=1,rvdir="older",rvstart=DRAFT[dy]+"T00:00:00Z",rvprop="ids|timestamp|size"),f"prerevq_{pid}.json")
        pages=list(rv.get("query",{}).get("pages",{}).values()); revs=pages[0].get("revisions",[]) if pages else []
        if not revs: json.dump(dict(status="no_prior_revision",title=title),open(out,"w")); c["no_prior_revision"]+=1; continue
        r0=revs[0]; wt=get(dict(action="parse",oldid=r0["revid"],prop="wikitext"),f"prerevtext_{pid}.json")
        text=wt.get("parse",{}).get("wikitext",{}).get("*","")
        json.dump(dict(status="ok",title=title,revid=r0["revid"],rev_ts=r0["timestamp"],size=r0.get("size"),draft_date=DRAFT[dy],wikitext=text),open(out,"w")); c["ok"]+=1
    except Exception as e:
        json.dump(dict(status="err",err=repr(e)[:100]),open(out,"w")); c["err"]+=1
    if n%50==0: print(f"{n}/{len(ids)} {dict(c)}",flush=True)
print("status:",dict(c),flush=True); print("PREREV_DONE")
