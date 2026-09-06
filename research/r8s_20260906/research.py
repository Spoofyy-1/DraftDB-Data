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
    state.update(status='running',phase='R8s · Combine and mock-rank combinations',total=len(tasks),completed=len(done),workers=workers,best=None,confirmation=None,test_result=None,message='Real statistics versus three matched shuffles; fixed base columns, missingness and dimensions. Test answers inaccessible.')
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
    state.update(status='completed',phase='R8s · Combine and mock-rank combinations completed',current='Queue complete',message='Matched feature controls complete. Judge real-minus-shuffled paired effects; no test-based selection.')
    write(state)

if __name__=='__main__':
    import sys
    if '--prepare-only' in sys.argv:
        from worker import _prepared, make_registered_model
        expected=json.loads((ROOT/'baseline_reference.json').read_text())
        fields=['base_columns_hash','training_pid_hash','validation_pid_hash','training_labels_hash','training_matrix_hash','validation_matrix_hash']
        checked=[]
        for backbone in expected:
            engine,plan,genes,folds=_prepared()
            for fold in folds:
                for key in fields:
                    assert fold['audit'][key]==expected[backbone][str(fold['year'])][key], (backbone,fold['year'],key)
                checked.append({'backbone':backbone,'year':fold['year']})
        (OUT/'baseline_preparation_check.json').write_text(json.dumps({'passed':True,'fields':fields,'folds':checked},indent=2))
        configurations=[]
        for seed in plan['seeds']:
            os.environ['SEED_SHIFT']=str(seed)
            _,parameters=make_registered_model(engine.cfg_of('tabicl',genes,list(folds[0]['btr'])))
            configurations.append({'seed':seed,'parameters':parameters})
        (OUT/'constructor_check.json').write_text(json.dumps({'passed':True,'fallback_permitted':False,'configurations':configurations},indent=2))
        print('R8s CPU preparation exactly matches R8n source-only baseline audit hashes.',flush=True)
    else:
        main()
