from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import json, os, math, time
HERE=os.path.dirname(os.path.abspath(__file__)); app=FastAPI()
@app.get("/api/runs")
def runs():
    p=f"{HERE}/lab_runs.jsonl"
    if not os.path.exists(p): return JSONResponse([])
    def clean(o):
        if isinstance(o,float):
            return None if (math.isnan(o) or math.isinf(o)) else o
        if isinstance(o,dict): return {k:clean(v) for k,v in o.items()}
        if isinstance(o,list): return [clean(v) for v in o]
        return o
    out=[]
    for line in open(p):
        line=line.strip()
        if not line: continue
        try: out.append(clean(json.loads(line)))
        except Exception: pass
    return JSONResponse(out)
@app.get("/",response_class=HTMLResponse)
def index():
    return open(f"{HERE}/dash.html").read()

@app.get("/api/stack")
def stack():
    """All result styles, in completion order. Each style is tagged with its source file, that file's
    modification time and its position, so the page can find the newest trained model."""
    out={"styles":{}}; idx=0
    for fn in ["best_results.json","r7/overnight_results.json"]+sorted(os.path.relpath(p,HERE) for p in __import__("glob").glob(f"{HERE}/r7/r7_results*.json")):
        p=f"{HERE}/{fn}"
        if os.path.exists(p):
            try:
                mt=os.path.getmtime(p); S=json.load(open(p)).get("styles",{})
                for k,v in S.items():
                    v=dict(v); v["_src"]=fn; v["_mtime"]=mt; v["_idx"]=idx; idx+=1; out["styles"][k]=v
            except Exception: pass
    # curated = frozen best + each island's CURRENT champion (latest accepted, gate-confirmed lineage) + adopted references.
    # Unadopted panel entries and superseded island champions are hidden by default (they passed a walk-forward gate only).
    cur=set()
    for lg in __import__("glob").glob(f"{HERE}/r7/lineage*.json"):
        try:
            L=json.load(open(lg)); isl=os.path.basename(lg)[len("lineage"):-5]
            acc=[h for h in L.get("history",[]) if h.get("accepted")]
            last=acc[-1]["gen"] if acc else 0
            cur.add(f"EVO{isl} gen{last}"); cur.add(f"EVO{isl} gen{last} (BEST MODEL)")
        except Exception: pass
    # also keep the three best lineage models by EXPANDING accuracy visible (adopted at the time; the metric that counts)
    def xacc(v):
        rx=[r for r in v.get("rows",[]) if r.get("kind")=="BLINDX"]; return sum(r["stack"] for r in rx)/len(rx) if rx else None
    lin=[(xacc(v),k) for k,v in out["styles"].items() if k.startswith("EVO") and xacc(v) is not None]
    for _,k in sorted(lin,reverse=True)[:3]: cur.add(k)
    for k,v in out["styles"].items():
        v["_curated"]=bool(k.startswith("BEST MODEL") or k in cur or v.get("adopted"))
    out["now"]=time.time()
    return JSONResponse(out)
@app.get("/api/evo")
def evo():
    """Live search activity: last log lines of every evolution island, generation counters, critic status."""
    import glob,re
    out={"islands":[],"now":time.time()}
    for lg in sorted(glob.glob(f"{HERE}/r7/evolve3*.log")):
        isl=os.path.basename(lg)[len("evolve3"):-4] or "main"
        try: lines=[l.rstrip() for l in open(lg) if l.strip() and (l.startswith("[") or "critic suggestion" in l or "NEW CHAMPION" in l or l.startswith("gen0") or "GUARD" in l or "Traceback" in l or "review_request" in l)]
        except Exception: lines=[]
        gens=[l for l in lines if re.match(r"\[\d\d:\d\d:\d\d\] gen\d+",l)]
        keeps=sum(1 for l in gens if " KEEP " in l)
        running=os.popen(f"pgrep -f 'r7/evolve3.py' >/dev/null && echo 1 || echo 0").read().strip()=="1"
        out["islands"].append(dict(island=isl,log=os.path.basename(lg),mtime=os.path.getmtime(lg),gens=len(gens),accepted=keeps,tail=lines[-8:],running=running))
    rq=f"{HERE}/r7/review_request.json"; sg=f"{HERE}/r7/suggestions.json"
    try: out["critic"]=dict(review_gen=json.load(open(rq)).get("gen") if os.path.exists(rq) else None,review_mtime=os.path.getmtime(rq) if os.path.exists(rq) else None,
                            suggestions=json.load(open(sg)) if os.path.exists(sg) else None,suggestions_mtime=os.path.getmtime(sg) if os.path.exists(sg) else None)
    except Exception as e: out["critic"]={"error":str(e)[:80]}
    return JSONResponse(out)
@app.get("/stack",response_class=HTMLResponse)
def stackpage(): return open(f"{HERE}/stack_r8.html").read()

@app.get("/api/ledger")
def ledger():
    p=f"{HERE}/vault/ledger.jsonl"; n=sum(1 for l in open(p) if l.strip()) if os.path.exists(p) else 0
    return JSONResponse({"blind_evaluations":n})

@app.get("/stack-legacy",response_class=HTMLResponse)
def legacy_stackpage():
    return open(f"{HERE}/stack.html").read().replace("<header>", '<div style="padding:12px;color:#e3b341;background:#161b22">HISTORICAL RESULTS — old cutoff and selection protocols; not certified under R8. <a href="/stack" style="color:#58a6ff">Return to current research</a></div><header>', 1)

@app.get("/api/r8")
def research_state():
    candidates=__import__("glob").glob(f"{HERE}/r*/results/state.json")
    path=max(candidates,key=os.path.getmtime) if candidates else f"{HERE}/r8/results/state.json"
    if not os.path.exists(path): return JSONResponse(dict(status="preparing",message="Calendar audit complete; preparing isolated worker."))
    try:
        s=json.load(open(path))
        for key,extra in [('test_result','r8baseline/results/test_result.json'),('resources','telemetry/state.json'),('collection','collection_state.json')]:
            ep=f"{HERE}/{extra}"
            if os.path.exists(ep):
                try: s[key]=json.load(open(ep))
                except Exception: pass
        groups={}
        for record in s.get('candidates',[]):
            if 'score' not in record or 'task_id' not in record: continue
            ident=record['task_id'].rsplit('_seed',1)[0]
            groups.setdefault(ident,[]).append(record)
        complete=[dict(id=k,score=sum(v['score'] for v in rows)/len(rows),seeds=len(rows)) for k,rows in groups.items() if len(rows)==3]
        if complete: s['best_configuration']=max(complete,key=lambda r:r['score'])
        if not os.path.exists(f"{HERE}/r8e/results/state.json"):
            s['queued']={'name':'50 individual statistics, three seeds, then gated combinations','runs':153}
        def compact(value):
            if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k!='predictions'}
            if isinstance(value,list):return [compact(v) for v in value]
            return value
        return JSONResponse(compact(s))
    except Exception: return JSONResponse(dict(status="updating",message="Reading the latest research state."))
