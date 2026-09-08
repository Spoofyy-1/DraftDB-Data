"""Current Wikipedia infobox for every prospect (time-invariant facts only are used downstream: relatives whose NBA career began
before the player's draft, birth place). Titles come from the pre-draft collectors' cached title per pid. Cached per pid."""
import json,glob,os,re,time,subprocess,csv,urllib.parse
H="/Users/kennakao/Downloads/nba_redraft_handoff"
titles={}
for fp in glob.glob("wiki_raw/attn_*.json")+glob.glob("wiki_raw/prerev*_*.json"):
    try: a=json.load(open(fp))
    except Exception: continue
    pid=a.get("pid") or (re.search(r"prerevq?_(P[0-9a-f]+)",fp) or [None,None])[1] if not a.get("pid") else a.get("pid")
    m=re.search(r"(P[0-9a-f]{10})",fp); pid=m.group(1) if m else None
    if pid and a.get("title") and pid not in titles: titles[pid]=a["title"]
print("titles:",len(titles),flush=True); n=0; bad=0
for pid,title in titles.items():
    out=f"wiki_raw/current/{pid}.json"
    if os.path.exists(out) and os.path.getsize(out)>200: continue
    url="https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main&format=json&formatversion=2&titles="+urllib.parse.quote(title)
    subprocess.run(["curl","-s","-m","40","-A","DraftDB-research (mike@alphax.inc)","-o",out,url])
    try:
        d=json.load(open(out)); t=d["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
        json.dump({"pid":pid,"title":title,"wikitext":t},open(out,"w"))
    except Exception: bad+=1
    n+=1
    if n%200==0: print(n,"fetched, failures",bad,flush=True)
    time.sleep(0.4)
print("CURRENT_DONE",n,bad,flush=True)
