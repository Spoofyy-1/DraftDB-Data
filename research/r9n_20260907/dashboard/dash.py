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
    for stage in ['r8i','r8f']:
        primary=f"{HERE}/{stage}/results/state.json"
        if os.path.exists(primary):
            try:
                if json.load(open(primary)).get('status')=='running':
                    path=primary
                    break
            except Exception:pass
    if not os.path.exists(path): return JSONResponse(dict(status="preparing",message="Calendar audit complete; preparing isolated worker."))
    try:
        s=json.load(open(path))
        for key,extra in [('test_result','r8baseline/results/test_result.json'),('resources','telemetry/state.json'),('collection','collection_state.json'),('performance','r8queuebench/results/progress.json')]:
            ep=f"{HERE}/{extra}"
            if os.path.exists(ep):
                try: s[key]=json.load(open(ep))
                except Exception: pass
        test_progress=f"{HERE}/r9test/results/progress.json"
        if os.path.exists(test_progress):
            s['test_pending']=json.load(open(test_progress))
            s['test_result']=None
        frozen_test=f"{HERE}/r9test/results/test_result.json"
        if os.path.exists(frozen_test):
            result=json.load(open(frozen_test))
            s.pop('test_pending',None)
            full=result['aggregate']['full_legacy']
            observed=result['aggregate']['complete_target_subset']
            s['test_result']={
                'protocol':result['protocol'], 'score':full['score'],
                'observed_score':observed['score'],
                'n_full':sum(r['n_full'] for r in result['rows']),
                'n_observed':sum(r['n_complete_target'] for r in result['rows']),
                'title':'Standalone H TabICL candidate · 2019–2025 benchmark',
                'description':'This is the standalone H TabICL candidate behind the 57.9% development subset result, not a retest of the original XGBoost + TabICL + ridge stack (historically 50.6% expanding over 2020–2025, under a different protocol). Fixed model and three seeds; all seven predictions frozen before scoring. Full and complete-target metrics are separate. Training labels obey each cutoff; 2024/2025 use verified labels only through 2022. Historical player pool and source provenance remain incomplete.',
                'rows':[{'season':r['season'],'k':r['k'],'n':r['n_full'],
                         'stack':r['full_legacy']['score'],'draft':r['full_legacy']['draft'],
                         'observed_n':r['n_complete_target'],
                         'observed_score':r['complete_target_subset']['score'],
                         'label_max':r['training']['actual_admitted_label_max']}
                        for r in result['rows']]}
        s['background_experiments']=[]
        for other in candidates:
            if other==path:continue
            try:
                job=json.load(open(other))
                if job.get('status')=='running':s['background_experiments'].append({k:job.get(k) for k in ['phase','completed','total']})
            except Exception:pass
        performance=s.get('performance') or {}
        if performance.get('status')=='running':
            s['background_experiments'].append(dict(phase='Runner speed check · '+str(performance.get('phase','running')),completed=performance.get('completed',0),total=performance.get('total',72)))
            if performance.get('active_workers'):s['workers']=performance['active_workers']
        queue_path=f'{HERE}/research_queue.json'
        if os.path.exists(queue_path):
            queue=json.load(open(queue_path))
            current_study=os.path.basename(os.path.dirname(os.path.dirname(path)))
            if queue.get('status')=='preparing' and queue.get('study')!=current_study:s['queued']=queue
        next_queue=f'{HERE}/research_queue_next.json'
        if os.path.exists(next_queue):
            followup=json.load(open(next_queue))
            current_study=os.path.basename(os.path.dirname(os.path.dirname(path)))
            if followup.get('status')=='preparing' and followup.get('study')!=current_study:s['queued_followup']=followup
        groups={}
        for record in s.get('candidates',[]):
            if 'score' not in record or 'task_id' not in record: continue
            config=record.get('config',{}); arms=config.get('arms',[])
            if config.get('arm') in ['permuted','RP','PR','PP'] or config.get('bio_arm')=='permuted' or 'permuted' in (arms.values() if isinstance(arms,dict) else arms):continue
            if 'control_' in record.get('task_id',''):continue
            ident=record['task_id'].rsplit('_seed',1)[0]
            groups.setdefault(ident,[]).append(record)
        expected_seeds={}
        registration=os.path.join(os.path.dirname(path),'preregistered_plan.json')
        if os.path.exists(registration):
            frozen=json.load(open(registration))
            plan=frozen.get('plan',frozen)
            for task in plan.get('tasks',[]):
                if isinstance(task,dict) and 'variant' in task and 'seed' in task:
                    expected_seeds.setdefault(task['variant'],set()).add(task['seed'])
        complete=[]
        for ident,rows in groups.items():
            seeds={row.get('seed') for row in rows}
            expected=expected_seeds.get(ident)
            ready=(seeds==expected) if expected else (len(seeds)==3 and None not in seeds)
            if ready and len(rows)==len(seeds) and all(not row.get('error') for row in rows):
                complete.append(dict(id=ident,score=sum(row['score'] for row in rows)/len(rows),seeds=len(seeds)))
        if complete: s['best_configuration']=max(complete,key=lambda r:r['score'])
        if s.get('best_stack'):
            best=s['best_stack']
            s['best_configuration']={'id':best['recipe_id'],'score':best['legacy']['mean_score'],'seeds':3,'kind':'stack','scope':'current study full pool'}
        matched=s.get('matched_summary') or {}
        for pair in matched.get('pairs',[]):
            if 'real_mean' in pair:
                pair.update(RR=pair['real_mean'],RP=pair['control_means']['RP'],PR=pair['control_means']['PR'],
                            joint_minus_A_only=pair['gain_B_given_A'],joint_minus_B_only=pair['gain_A_given_B'],
                            passes=pair['exploratory_complement_candidate'])
        for statistic in matched.get('statistics',[]):
            paired=statistic.get('paired_rows',[])
            if paired and 'real_score' not in statistic:
                statistic['real_score']=sum(r['real'] for r in paired)/len(paired)
                statistic['matched_control_score']=sum(r['mean_control'] for r in paired)/len(paired)
        factorial=matched.get('factorial') or {}
        contrasts=factorial.get('contrasts',[])
        if contrasts:
            for name,control,gain in [('consensus given combine','RP','consensus_given_combine'),('combine given consensus','PR','combine_given_consensus')]:
                matched.setdefault('statistics',[]).append(dict(id=name,real_score=sum(r['RR'] for r in contrasts)/len(contrasts),matched_control_score=sum(r[control] for r in contrasts)/len(contrasts),paired_mean_gain=sum(r[gain] for r in contrasts)/len(contrasts),automatic_promotion=False))
        s['research_notice']='Data audit: inherited weight/BMI can use current NBA measurements and combined train/test imputation. Earlier scores are uncertified diagnostics; affected inputs are being removed.'
        if '/r9k/' in path:
            s['research_notice']='Stack study: label seasons obey each cutoff; weights use out-of-fold training predictions. 44 versus 174 input columns. Historical population and reconstructed source vintage remain incomplete. No new 2019–2025 test result yet.'
        if '/r9l/' in path:
            s['research_notice']='Feature-family stack study: same observed first-season labels and exact 44-input control; three model families, fixed weights, development only. Historical population and source vintage limitations remain. No new 2019–2025 test result.'
        if '/r9m/' in path:
            s['research_notice']='Stack study: models use different combinations of college statistics, combine, game and team inputs. Six exact saved control records are reused; 162 new fits. Fixed weights, pre-2019 development only. No new benchmark result; historical source and population limitations remain.'
        if '/r9n/' in path:
            s['research_notice']='Testing TabICL ensemble size and preprocessing within the fixed college/game/team inputs, reusing verified Ridge and CatBoost predictions. Distinct settings pass input checks before fitting. Pre-2019 development only; no new benchmark result. Historical source and population limitations remain.'
        if not os.path.exists(f"{HERE}/r8e/results/state.json"):
            s['queued']={'name':'50 individual statistics, three seeds, then gated combinations','runs':153}
        def compact(value):
            if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k not in ['predictions','audit']}
            if isinstance(value,list):return [compact(v) for v in value]
            return value
        return JSONResponse(compact(s))
    except Exception: return JSONResponse(dict(status="updating",message="Reading the latest research state."))
