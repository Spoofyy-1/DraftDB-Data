"""Preregistered gates for 50 single-feature screens and complementary pairs."""
import os
os.environ['OMP_NUM_THREADS']='3';os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import concurrent.futures as cf,multiprocessing as mp
import itertools,json,time
import numpy as np
from worker import run_variant
from research import write
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def main():
    state=json.loads((OUT/'state.json').read_text());plan=json.loads((ROOT/'plan.json').read_text())
    seeds=plan['seeds'];gate=plan['combination_gate'];rows=state['candidates']
    def summarize(vid):
        rs=[r for r in rows if r.get('task_id','').rsplit('_seed',1)[0]==vid and 'score' in r]
        if len(rs)!=len(seeds):return None
        return dict(id=vid,score=float(np.mean([r['score'] for r in rs])),folds={year:float(np.mean([next(t['stack'] for t in r['rows'] if t['season']==year) for r in rs])) for year in plan['folds']})
    base=summarize('baseline')
    if base is None:raise RuntimeError('Baseline incomplete: combination selection prohibited')
    stats=[]
    for v in plan['variants'][1:]:
        s=summarize(v['id'])
        if s is None:continue
        s['gain']=s['score']-base['score'];deltas=[s['folds'][y]-base['folds'][y] for y in plan['folds']]
        s['passes']=s['gain']>=gate['min_mean_gain'] and sum(d>0 for d in deltas)>=gate['min_improved_folds'] and min(deltas)>=-gate['max_fold_regression'];stats.append(s)
    stats.sort(key=lambda s:s['gain'],reverse=True)
    winners=[s['id'] for s in stats if s['passes']][:gate['maximum_winners']]
    (OUT/'single_feature_summary.json').write_text(json.dumps(dict(baseline=base,statistics=stats,winners=winners,interpretation='Development screens, not confirmed winners or test gains'),indent=2))
    combos=list(itertools.combinations(winners,2))
    if len(winners)>2:combos.append(tuple(winners))
    combos += [tuple(pair) for pair in plan.get('prespecified_complementary_pairs',[])]
    combos=list(dict.fromkeys(tuple(sorted(c)) for c in combos))
    combo_plan=OUT/'combination_plan.json'
    registration=dict(created=time.time(),winners=winners,combinations=[list(c) for c in combos],seeds=seeds,selection_rule=gate)
    if combo_plan.exists():
        old=json.loads(combo_plan.read_text());assert old['combinations']==registration['combinations']
    else:combo_plan.write_text(json.dumps(registration,indent=2))
    tasks=[(i,c,seed) for i,c in enumerate(combos) for seed in seeds]
    done={r['task_id'] for r in rows};tasks=[t for t in tasks if f'combo{t[0]:02d}_seed{t[2]}' not in done]
    state.update(status='running',phase='R8f · complementary feature combinations',total=len(plan['variants'])*len(seeds)+len(combos)*len(seeds),message=f'{len(winners)} statistics passed the preregistered development gate; testing {len(combos)} combinations.')
    write(state)
    with cf.ProcessPoolExecutor(max_workers=int(os.environ.get("R8_WORKERS","4")),mp_context=mp.get_context('spawn')) as pool:
        pending={}
        while tasks or pending:
            while tasks and len(pending)<int(os.environ.get("R8_WORKERS","4")):
                i,combo,seed=tasks.pop(0);vid=f'combo{i:02d}'
                v=dict(id=vid,noscout=1,drafted_only=False,context=None,extras=list(combo),drop=['scout_'],hw='uniform')
                pending[pool.submit(run_variant,vid,seed,v)]=(vid,seed)
            state['current']=' | '.join(f'{v} seed{s}' for v,s in pending.values());write(state)
            ready,_=cf.wait(pending,timeout=10,return_when=cf.FIRST_COMPLETED)
            for future in ready:
                vid,seed=pending.pop(future)
                try:r=future.result()
                except Exception as e:r=dict(config={'id':vid},error=repr(e))
                r['task_id']=f'{vid}_seed{seed}';r['seed']=seed;r['config']['id']=r['task_id'];rows.append(r)
                state['completed']=len(rows);good=[r for r in rows if 'score' in r];state['best']=max(good,key=lambda r:r['score']);write(state)
    state.update(status='completed',phase='R8f · screens and first combinations complete',current='Ready for review',message=f'Completed individual comparisons and gated combinations. {len(winners)} provisional development winners; no test selection.')
    write(state)
if __name__=='__main__':main()
