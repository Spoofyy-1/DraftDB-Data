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
    frozen=json.loads((ROOT/'prototype_manifest.json').read_text())
    for name,expected in frozen['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, ('Frozen study file changed',name)
    registration=OUT/'preregistered_plan.json'
    if registration.exists():
        assert json.loads(registration.read_text())['sha256']==digest
        assert json.loads(registration.read_text())['code_and_bundle_hashes']==frozen['files']
    else:
        registration.write_text(json.dumps(dict(plan=plan,sha256=digest,code_and_bundle_hashes=frozen['files'],created=time.time()),indent=2))
    tasks=[(v['id'],seed) for v in plan['variants'] for seed in plan['seeds']]
    state=json.loads((OUT/'state.json').read_text()) if (OUT/'state.json').exists() else dict(started=time.time(),candidates=[])
    done={r['task_id'] for r in state['candidates']}
    todo=[t for t in tasks if f'{t[0]}_seed{t[1]}' not in done]
    workers=int(os.environ.get('R8_WORKERS','4'))
    state.update(status='running',phase='R8u · Individual dated biography fields',total=len(tasks),completed=len(done),workers=workers,best=None,confirmation=None,test_result=None,message='Real statistics versus three matched shuffles; fixed base columns, missingness and dimensions. Test answers inaccessible.')
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
    state.update(status='completed',phase='R8u · Individual dated biography fields completed',current='Queue complete',message='Matched feature controls complete. Judge real-minus-shuffled paired effects; no test-based selection.')
    write(state)

if __name__=='__main__':
    import sys
    if '--prepare-only' in sys.argv:
        from worker import _prepared, _design, _matrix_hash, _hash, make_registered_model
        import importlib.util
        reference=json.loads((ROOT/'baseline_reference.json').read_text())
        for name,digest in reference['source_data_hashes'].items():
            assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest, name
        spec=importlib.util.spec_from_file_location('r8t_frozen_reference',ROOT/'r8t_reference/worker.py')
        T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
        _,tplan,_,tfolds=T._prepared()
        engine,plan,genes,folds=_prepared()
        audits=[]
        for fold,tfold in zip(folds,tfolds):
            year=fold['year'];expected=next(f for f in reference['folds'] if f['year']==year)
            tvariant=next(v for v in tplan['variants'] if v['id']=='college_consensus_baseline')
            variant=next(v for v in plan['variants'] if v['id']=='baseline')
            atr,ate,families=_design(fold,variant,plan)
            ttr,tte,tfamilies=T._design(tfold,tvariant,tplan)
            merged={**fold['audit'],'input_columns':list(atr),'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum())}
            for key,value in expected['audit'].items(): assert merged[key]==value, (year,key)
            assert families['consensus']==expected['consensus']==tfamilies['consensus']
            assert _matrix_hash(atr)==T._matrix_hash(ttr) and _matrix_hash(ate)==T._matrix_hash(tte)
            assert [_hash(key) for key in T._exact_vector_keys(ate)]==expected['query_vector_hashes']
            assert len(atr.columns)==45 and list(atr)==list(ttr)==list(ate)==list(tte)
            audits.append({'year':year,'all_completed_R8t_hashes_match':True,'full_training_matrix_hash':_matrix_hash(atr),
                           'full_validation_matrix_hash':_matrix_hash(ate),'audit':merged,'fixed_consensus':families['consensus']})
        configurations=[]
        for seed in plan['seeds']:
            os.environ['SEED_SHIFT']=str(seed)
            _,parameters=make_registered_model(engine.cfg_of('tabicl',genes,list(folds[0]['btr'])))
            configurations.append({'seed':seed,'parameters':parameters})
        check={'passed':True,'exact_completed_R8t_baseline_match':True,'folds':audits,'constructor_checks':configurations,
               'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),
               'worker_sha256':hashlib.sha256((ROOT/'worker.py').read_bytes()).hexdigest(),
               'predictor_calls':0,'fallback_permitted':False}
        (OUT/'baseline_preparation_check.json').write_text(json.dumps(check,indent=2))
        print('R8u exact completed R8t baseline/component/full-matrix/label/identity/column hashes verified; no GPU prediction.',flush=True)
    else:
        check=json.loads((OUT/'baseline_preparation_check.json').read_text())
        assert check['passed'] and check['exact_completed_R8t_baseline_match']
        assert check['plan_sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
        assert check['worker_sha256']==hashlib.sha256((ROOT/'worker.py').read_bytes()).hexdigest()
        main()
