"""Turn each dated pre-draft Wikipedia snapshot into numeric features with an LLM (extraction, strict JSON).
Leak-proof by construction: the text is the article as it stood the night before the draft. Runs on the Mac; only
pid-keyed numbers leave. Cached per pid in wiki_raw/txtfeat_{pid}.json. 3 workers."""
import json,os,re,glob,subprocess,concurrent.futures as cf,time,collections
CLAUDE="/Users/kennakao/.local/bin/claude"; MODEL=os.environ.get("TXT_MODEL","claude-haiku-4-5-20251001")
SCHEMA={"hype":"0-1 how strongly the article frames him as an elite/top prospect (lottery, five-star, player of the year, consensus top pick)",
        "injury":"0-1 salience of injuries/surgeries/missed time","character":"0-1 salience of off-court, discipline, eligibility or attitude concerns",
        "pro_family":"1 if a parent/sibling/relative played professional basketball, else 0","nba_family":"1 if a parent, sibling or other relative played in the NBA or WNBA, else 0","breakout":"0-1 how strongly the article describes improvement over time (breakout season, took a leap, improved shooting, grew into a role, late riser)","left_handed":"1 if described as left-handed, else 0","late_bloomer":"1 if described as unranked, lightly recruited, walk-on, late growth spurt or late bloomer, else 0",
        "awards":"integer count of major honors mentioned (All-American, conference player of the year, MVP, McDonald's All-American, national team medals)",
        "national_team":"1 if he played for a national team at any level, else 0","transfer":"1 if he transferred schools/clubs, else 0",
        "shooter":"0-1 emphasis on shooting","athlete":"0-1 emphasis on athleticism/explosiveness","playmaker":"0-1 emphasis on passing/playmaking","defender":"0-1 emphasis on defense",
        "size_for_position":"0-1 emphasis on unusual size/length for his position","role_projection":"1-5 how the article projects his NBA role (1 fringe, 3 starter, 5 franchise player); 0 if not discussed",
        "tone":"-1 to 1 overall tone toward his prospects"}
PROMPT="You extract numeric features from a Wikipedia article about a basketball prospect as it stood before his NBA draft. Use ONLY the text. Return ONLY one JSON object with these keys and value definitions, no prose:\n"+json.dumps(SCHEMA,indent=0)+"\n\nARTICLE:\n"
def clean(wt):
    wt=re.sub(r"\{\{[^{}]*\}\}","",wt); wt=re.sub(r"\{\{[^{}]*\}\}","",wt); wt=re.sub(r"<ref[^>]*/>|<ref.*?</ref>","",wt,flags=re.S)
    wt=re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]",r"\1",wt); wt=re.sub(r"'{2,}","",wt); wt=re.sub(r"<[^>]+>","",wt); wt=re.sub(r"\n{2,}","\n",wt)
    return wt.strip()[:14000]
def score(fp):
    pid=fp.split("prerev_")[1][:-5]; out=f"wiki_raw/txtfeat_{pid}.json"
    if os.path.exists(out): return "cached"
    d=json.load(open(fp))
    if d.get("status")!="ok": json.dump(dict(pid=pid,status=d.get("status")),open(out,"w")); return d.get("status")
    text=clean(d["wikitext"])
    try:
        r=subprocess.run([CLAUDE,"-p","--model",MODEL,"--output-format","text"],input=PROMPT+text,capture_output=True,text=True,timeout=240)
        m=re.search(r"\{.*\}",r.stdout,re.S); v=json.loads(m.group(0)) if m else None
    except Exception as e: v=None; err=repr(e)[:80]
    if not isinstance(v,dict): json.dump(dict(pid=pid,status="parse_fail",raw=(r.stdout if 'r' in dir() else '')[:300]),open(out,"w")); return "parse_fail"
    rec=dict(pid=pid,status="ok",txt_len=len(text),txt_size_pre=d.get("size"),rev_ts=d.get("rev_ts"))
    for k in SCHEMA:
        try: rec["txt_"+k]=float(v.get(k)) if v.get(k) is not None else None
        except Exception: rec["txt_"+k]=None
    json.dump(rec,open(out,"w")); return "ok"
files=sorted(glob.glob("wiki_raw/prerev_*.json")); print("snapshots:",len(files),"model:",MODEL,flush=True)
c=collections.Counter(); t0=time.time()
with cf.ThreadPoolExecutor(6) as ex:
    for i,res in enumerate(ex.map(score,files),1):
        c[res]+=1
        if i%40==0: print(f"{i}/{len(files)} {dict(c)} {time.time()-t0:.0f}s",flush=True)
print("done:",dict(c),flush=True); print("TXT_DONE")
