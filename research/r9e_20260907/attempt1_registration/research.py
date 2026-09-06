"""Frozen R9e study using the unchanged benchmark-verified scheduler."""
import os
os.environ['OMP_NUM_THREADS']='3';os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import json,hashlib,time,sys,concurrent.futures as cf,multiprocessing as mp
import worker as X
import queue_runtime as Q
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'

def pool_factory(workers):return cf.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn'))

def verify_frozen():
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in frozen['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    return frozen

def prepare():
    verify_frozen();p=X.load_plan();cap=X.capacity();B=X.B;E,bp,g,folds=B._prepared();proof=[]
    import importlib.metadata
    for package,version in cap['library_versions'].items():assert importlib.metadata.version(package)==version
    for name,info in cap['sources'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==info['sha256']
    assert cap['tasks']==p['execution']['task_count'] and cap['requested_to_evaluated']==p['requested_to_evaluated']
    for fold in folds:
        atr,ate=X.design(fold)
        for seed in p['seeds']:
            old=next(r for r in X.D.references()[seed]['rows'] if r['season']==fold['year'])
            assert list(atr)==old['audit']['input_columns'] and [B._hash(k) for k in B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
            for key,value in fold['audit'].items():assert value==old['audit'][key]
        proof.append({'year':fold['year'],'all_source_label_pid_column_audits_exact':True,'train_hash':B._matrix_hash(atr),'query_hash':B._matrix_hash(ate),'columns':list(atr)})
    for fold in folds:
        for name in p['target_transforms']:
            _,target=X.transform_target(fold['yy'],name)
            for v in p['variants']:
                if v['target_transform']==name:
                    assert all(target==cap['designs'][v['id']][f"{fold['year']}:{seed}"]['training_target_transform'] for seed in p['seeds'])
    assert len(X.d_references())==18
    for v in p['variants']:
        for seed in p['seeds']:
            _,kwargs,effective=X.constructor(p['settings_by_id'][v['id']],seed)
            assert all(effective==cap['designs'][v['id']][f"{y}:{seed}"]['effective_constructor'] for y in p['folds'])
            json.dumps(kwargs,allow_nan=False);json.dumps(effective,allow_nan=False)
    Q.atomic_json(OUT/'preparation.json',{'passed':True,'models_fitted':0,'source_designs':proof,'requested_configurations':432,'distinct_configurations':len(p['variants']),'tasks':p['execution']['task_count'],'training_target_hashes_and_monotonicity_exact':True,'query_truth_not_used_for_transform_or_dedupe':True,'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()})
    print('R9e source/reference/constructor/CPU-payload integrity preflight passed; no model fits.',flush=True)

def main():
    frozen=verify_frozen();plan=X.load_plan();check=json.loads((OUT/'preparation.json').read_text());assert check['passed'] and check['frozen_manifest_sha256']==hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()
    registration={'plan':plan,'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),'files':frozen['files']}
    path=OUT/'preregistered_plan.json'
    if path.exists():assert json.loads(path.read_text())==registration
    else:Q.atomic_json(path,registration)
    known={};started=time.time()
    def validate(entry):X.validate_entry(entry,plan);known[entry['task_id']]=entry
    def event(kind,detail):
        if kind=='snapshot_end':
            path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R9e registered training-target and model settings',started=started,updated=time.time(),confirmation=None,test_result=None)
            for candidate in state['candidates']:
                record=known[candidate['task_id']];candidate['rows']=[{'season':r['season'],'stack':r['stack']} for r in record['rows']]
            real=[e for e in state['candidates'] if e['config'].get('arm','RR')=='RR']
            state['best']=max(real,key=lambda e:e['score']) if real and state['matched_summary']['interpretation_allowed'] else None
            state['active_workers']=0 if state['status']=='completed' else min(4,plan['execution']['task_count']-state['completed'])
            state['current']=' | '.join(state['current']) if isinstance(state['current'],list) else state['current']
            Q.atomic_json(path,state)
        elif kind=='persist_end':print(json.dumps({'completed_task':detail['task']}),flush=True)
    tasks=[(v['id'],s) for v in plan['variants'] for s in plan['seeds']]
    result=Q.run_queue(tasks,X.run_variant,[],OUT,validate,X.summarize_matched,pool_factory,workers=4,snapshot_seconds=3.,summary_seconds=20.,registration_hash=hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest(),event=event)
    assert result['completed_new']==plan['execution']['task_count']
    ensemble=X.seed_average(result['records']);Q.atomic_json(OUT/'seed_ensembles.json',ensemble)
    state=json.loads((OUT/'state.json').read_text());state['seed_averaged_diagnostic']=[{k:v for k,v in e.items() if k!='rows'} for e in ensemble['configurations']];Q.atomic_json(OUT/'state.json',state)
    Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':plan['execution']['task_count'],'scheduler_counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'workers':4,'no_model_promotion':True})

if __name__=='__main__':
    try:
        if '--capacity-only'in sys.argv:import capacity
        elif '--test-only'in sys.argv:import test_essential
        elif '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=OUT/'state.json';state=json.loads(path.read_text()) if path.exists() else {}
        Q.atomic_json(path,{**state,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error)})
        raise
