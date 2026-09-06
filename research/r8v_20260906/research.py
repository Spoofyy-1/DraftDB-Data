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
    tasks=[(t['variant'],t['seed']) for t in plan['tasks']]
    state=json.loads((OUT/'state.json').read_text()) if (OUT/'state.json').exists() else dict(started=time.time(),candidates=[])
    done={r['task_id'] for r in state['candidates']}
    todo=[t for t in tasks if f'{t[0]}_seed{t[1]}' not in done]
    workers=int(os.environ.get('R8_WORKERS','4'))
    state.update(status='running',phase='R8v · Fixed model-family comparison',total=len(tasks),completed=len(done),workers=workers,best=None,confirmation=None,test_result=None,message='Registered TabICL, Ridge, ExtraTrees and CPU XGBoost comparisons on two fixed inputs. Interpretation waits for exact reference replays; test answers inaccessible.')
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
            state['best']=max(good,key=lambda r:r['score']) if good and state.get('matched_summary',{}).get('interpretation_allowed') else None
            state['elapsed_seconds']=round(time.time()-state['started'],1)
            state['experiments_per_minute']=round(state['completed']*60/max(1,state['elapsed_seconds']),2)
            write(state)
    state.update(status='completed',phase='R8v · Fixed model-family comparison completed',current='Queue complete',message='Registered model comparisons complete. Review fold and seed scores against the replayed references; no blends, promotion or test-based selection.')
    write(state)

if __name__=='__main__':
    import sys
    if '--prepare-only' in sys.argv:
        from worker import _prepared, _design, _matrix_hash, _hash, make_registered_model
        import importlib.util
        import numpy as np
        reference=json.loads((ROOT/'baseline_reference.json').read_text())
        for name,digest in reference['source_data_hashes'].items():
            assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest, name
        spec=importlib.util.spec_from_file_location('r8u_frozen_reference',ROOT/'r8u_reference/worker.py')
        U=importlib.util.module_from_spec(spec);spec.loader.exec_module(U)
        _,uplan,_,ufolds=U._prepared()
        engine,plan,genes,folds=_prepared()
        audits=[]
        for fold,ufold in zip(folds,ufolds):
            for background,sg in plan['backgrounds'].items():
                ref=next(r for r in reference['references'] if r['background']==background and r['seed']==0)
                expected=next(r['audit'] for r in ref['rows'] if r['season']==fold['year'])
                uv=next(v for v in uplan['variants'] if v['id']==('vmb_position_sg_real' if sg else 'baseline'))
                vv=next(v for v in plan['variants'] if v['id']==background+'_tabicl32')
                atr,ate,families=_design(fold,vv,plan);utr,ute,ufamilies=U._design(ufold,uv,uplan)
                merged={**fold['audit'],'input_columns':list(atr),'raw_feature_count':len(atr.columns),'training_nonconstant_columns':int((atr.nunique()>1).sum())}
                for key in ['ordered_base_columns','base_columns_hash','training_pid_hash','validation_pid_hash','training_labels_hash','training_matrix_hash','validation_matrix_hash','source_selection_hash','ordering_policy_hash','input_columns','raw_feature_count','training_nonconstant_columns']:
                    assert merged[key]==expected[key],(fold['year'],background,key)
                assert families==expected['families']==ufamilies
                assert _matrix_hash(atr)==U._matrix_hash(utr) and _matrix_hash(ate)==U._matrix_hash(ute)
                assert [_hash(key) for key in U._exact_vector_keys(ate)]==expected['canonical_prediction_ties']['row_vector_hashes']
                audits.append({'year':fold['year'],'background':background,'completed_R8u_hashes_exact':True,
                    'full_training_matrix_hash':_matrix_hash(atr),'full_validation_matrix_hash':_matrix_hash(ate),'audit':merged})
        constructors=[]
        for model_id,spec in plan['models'].items():
            for seed in spec['seeds']:
                _,parameters=make_registered_model(spec,seed)
                constructors.append({'model_id':model_id,'seed':seed,'parameters':parameters})
        from cpu_tests import run_cpu_tests
        cpu_tests=run_cpu_tests(plan)
        check={'passed':True,'exact_completed_R8u_inputs_match':True,'folds':audits,'constructor_checks':constructors,'cpu_tests':cpu_tests,
               'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),
               'worker_sha256':hashlib.sha256((ROOT/'worker.py').read_bytes()).hexdigest(),'gpu_predictor_calls':0,'fallback_permitted':False}
        (OUT/'baseline_preparation_check.json').write_text(json.dumps(check,indent=2))
        print('R8v exact R8u inputs verified for both backgrounds; constructors and training-only preprocessing tests passed.',flush=True)
    else:
        check=json.loads((OUT/'baseline_preparation_check.json').read_text())
        assert check['passed'] and check['exact_completed_R8u_inputs_match']
        assert check['plan_sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
        assert check['worker_sha256']==hashlib.sha256((ROOT/'worker.py').read_bytes()).hexdigest()
        main()
