"""French Wikipedia (CC-BY-SA, API) career-stat tables for prospects whose English page has no pro table.
Same rules as wiki_collect.py: runs on the Mac, 1 req/s, cached, output is pid-keyed with no names."""
import json,os,re,time,csv,urllib.request,urllib.parse,unicodedata,collections
UA={"User-Agent":"DraftDB-research/1.0 (mike@alphax.inc) python-urllib"}; API="https://fr.wikipedia.org/w/api.php"
def get(params,fn):
    p=f"wiki_raw/{fn}"
    if os.path.exists(p): return json.load(open(p))
    time.sleep(1.0); url=API+"?"+urllib.parse.urlencode(dict(params,format="json"))
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=40) as r: d=json.load(r)
    json.dump(d,open(p,"w")); return d
def norm(s): return re.sub(r"[^a-z0-9 ]","",unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower())
I2={r["pid"]:r for r in csv.DictReader(open("intl2_features.csv"))}
targets=[t for t in csv.DictReader(open("targets_LOCAL_names.csv")) if t["path"]=="international" and I2.get(t["pid"],{}).get("intl2_has_pro")!="1"]
print("targets for fr pass:",len(targets),flush=True); res={}
for n,t in enumerate(targets,1):
    try:
        s=get(dict(action="query",list="search",srsearch=t["name"]+" basket-ball",srlimit=3),f"fr_search_{t['pid']}.json")
        hits=s.get("query",{}).get("search",[])
        if not hits: res[t["pid"]]=dict(status="no_page"); continue
        title=None
        for h in hits:
            if norm(t["name"].split()[-1]) in norm(h["title"]): title=h["title"]; break
        title=title or hits[0]["title"]
        pg=get(dict(action="parse",page=title,prop="text",redirects=1),f"fr_page_{t['pid']}.json")
        res[t["pid"]]=dict(status="ok",title=title,nchars=len(pg.get("parse",{}).get("text",{}).get("*","")))
    except Exception as e: res[t["pid"]]=dict(status="err",err=repr(e)[:80])
    if n%20==0: print(f"{n}/{len(targets)}",flush=True)
json.dump(res,open("wiki_raw/_fr_matches.json","w")); print("status:",dict(collections.Counter(v["status"] for v in res.values())),flush=True); print("FR_DONE")
