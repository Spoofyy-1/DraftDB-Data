"""Resumable, bounded parallel development queue. Only parent writes progress."""
import os
os.environ['OMP_NUM_THREADS']='3'
os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import concurrent.futures as cf
import multiprocessing as mp
import json,time,hashlib
from worker import run_variant, summarize_matched

def is_control(config):
    arms=config.get('arms',[])
    return config.get('arm')=='permuted' or 'permuted' in (arms.values() if isinstance(arms,dict) else arms)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
def write(state):
    state['updated']=time.time()
    state['matched_summary']=summarize_matched(state.get('candidates',[]))
    tmp=OUT/'state.tmp'
    tmp.write_text(json.dumps(state,indent=2,allow_nan=False))
    tmp.replace(OUT/'state.json')

def main():
    plan=json.loads((ROOT/'plan.json').read_text())
    digest=hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
    registration=OUT/'preregistered_plan.json'
    if registration.exists():
        assert json.loads(registration.read_text())['sha256']==digest
    else:
        registration.write_text(json.dumps(dict(plan=plan,sha256=digest,created=time.time()),indent=2))
    tasks=[(v['id'],seed) for v in plan['variants'] for seed in plan['seeds']]
    state=json.loads((OUT/'state.json').read_text()) if (OUT/'state.json').exists() else dict(started=time.time(),candidates=[])
    done={r['task_id'] for r in state['candidates']}
    todo=[t for t in tasks if f'{t[0]}_seed{t[1]}' not in done]
    workers=int(os.environ.get('R8_WORKERS','4'))
    state.update(status='running',phase='R8t · Archived profiles across four backgrounds',total=len(tasks),completed=len(done),workers=workers,best=None,confirmation=None,test_result=None,message='Real statistics versus three matched shuffles; fixed base columns, missingness and dimensions. Test answers inaccessible.')
    write(state)
    with cf.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn')) as pool:
        pending={}
        while todo or pending:
            while todo and len(pending)<workers:
                task=todo.pop(0);pending[pool.submit(run_variant,*task)]=task
            state['current']=' | '.join(f'{v} seed{s}' for v,s in pending.values())
            write(state)
            ready,_=cf.wait(pending,timeout=10,return_when=cf.FIRST_COMPLETED)
            for future in ready:
                vid,seed=pending.pop(future)
                try:r=future.result()
                except Exception as e:r=dict(config={'id':vid},error=repr(e))
                r['task_id']=f'{vid}_seed{seed}'
                r['seed']=seed
                state['candidates'].append(r);state['completed']+=1
                print(json.dumps(dict(task=r['task_id'],score=r.get('score'),error=r.get('error'),completed=state['completed'])),flush=True)
            good=[r for r in state['candidates'] if 'score' in r and not is_control(r.get('config',{}))]
            state['best']=max(good,key=lambda r:r['score']) if good else None
            state['elapsed_seconds']=round(time.time()-state['started'],1)
            state['experiments_per_minute']=round(state['completed']*60/max(1,state['elapsed_seconds']),2)
            write(state)
    state.update(status='completed',phase='R8t · Archived profiles across four backgrounds completed',current='Queue complete',message='Matched feature controls complete. Judge real-minus-shuffled paired effects; no test-based selection.')
    write(state)

if __name__=='__main__':
    import sys
    if '--prepare-only' in sys.argv:
        from worker import _prepared, make_registered_model, _canonical_rows
        import pandas as pd
        source_reference=json.loads((ROOT/'baseline_source_reference.json').read_text())
        for name,digest in source_reference.items():
            assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest, name
        engine,plan,genes,folds=_prepared()
        audits=[]
        for fold in folds:
            assert fold['tr'].pid.tolist()==_canonical_rows(fold['tr']).pid.tolist()
            assert fold['te'].pid.tolist()==_canonical_rows(fold['te']).pid.tolist()
            assert set(fold['btr'])==set(plan['baseline_source_variant']['context_features'])
            assert fold['audit']['max_label_season']<=fold['year']-1
            audits.append({'year':fold['year'],'audit':fold['audit']})
        configurations=[]
        for seed in plan['seeds']:
            os.environ['SEED_SHIFT']=str(seed)
            _,parameters=make_registered_model(engine.cfg_of('tabicl',genes,list(folds[0]['btr'])))
            configurations.append({'seed':seed,'parameters':parameters})
        (OUT/'baseline_preparation_check.json').write_text(json.dumps({'passed':True,'new_canonical_order_baseline':True,'baseline_source_hashes_unchanged':source_reference,'folds':audits,'constructor_checks':configurations,'fallback_permitted':False},indent=2))
        print('R8t source hashes unchanged; canonical baseline and registered model constructors verified.',flush=True)
    else:
        main()
