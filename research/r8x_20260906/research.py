"""Frozen X study using the unchanged benchmark-verified scheduler."""
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
    frozen=verify_frozen();plan=X.load_plan();B=X.B;E,bp,g,folds=B._prepared()
    refs=json.loads((ROOT/'w_reference.json').read_text())['records'];proof=[]
    for fold in folds:
        expected=next(r for e in refs if e['config']['id']=='baseline' for r in e['rows'] if r['season']==fold['year'])
        for key,value in fold['audit'].items():assert value==expected['audit'][key],(fold['year'],key)
        for vid in plan['reference_ids']:
            v=next(v for v in bp['variants'] if v['id']==vid);atr,ate,families=B._design(fold,v,bp)
            row=next(r for e in refs if e['config']['id']==vid for r in e['rows'] if r['season']==fold['year'])
            assert families==row['audit']['families'] and list(atr)==row['audit']['input_columns']
            assert [B._hash(k) for k in B._exact_vector_keys(ate)]==row['audit']['canonical_prediction_ties']['row_vector_hashes']
        for variant in [v for v in plan['variants'] if 'pair'in v and (v['arm']=='RR' or (v['arm']=='PP' and v['permutation_seed']==9317))]:
            atr,ate,_,pa=X.design_pair(fold,variant,plan,bp);assert atr.shape[1]==47
        proof.append({'year':fold['year'],'base_input_label_id_column_audits_exact':True,'reference_designs':6,'pair_RR_and_PP_designs':20,'training_rows':len(fold['tr']),'query_rows':len(fold['te'])})
    configurations=[]
    for seed in plan['seeds']:
        os.environ['SEED_SHIFT']=str(seed);_,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)));configurations.append(kwargs)
    Q.atomic_json(OUT/'preparation.json',{'passed':True,'models_fitted':0,'folds':proof,'constructors':configurations,'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()})
    print('X CPU source/label/input/reference/column audits and pair widths passed; no predictor fit.',flush=True)

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
            path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R8x pair complements',started=started,updated=time.time(),confirmation=None,test_result=None)
            for candidate in state['candidates']:
                record=known[candidate['task_id']];candidate['rows']=[{'season':r['season'],'stack':r['stack']} for r in record['rows']]
            real=[e for e in state['candidates'] if e['config'].get('arm','RR')=='RR']
            state['best']=max(real,key=lambda e:e['score']) if real and state['matched_summary']['interpretation_allowed'] else None
            state['active_workers']=0 if state['status']=='completed' else min(4,318-state['completed'])
            state['current']=' | '.join(state['current']) if isinstance(state['current'],list) else state['current']
            Q.atomic_json(path,state)
        elif kind=='persist_end':print(json.dumps({'completed_task':detail['task']}),flush=True)
    tasks=[(v['id'],s) for v in plan['variants'] for s in plan['seeds']]
    result=Q.run_queue(tasks,X.run_variant,[],OUT,validate,X.summarize_matched,pool_factory,workers=4,snapshot_seconds=3.,summary_seconds=20.,registration_hash=hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest(),event=event)
    assert result['completed_new']==318
    Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':318,'scheduler_counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'workers':4,'no_model_promotion':True})

if __name__=='__main__':
    try:
        if '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=OUT/'state.json';state=json.loads(path.read_text()) if path.exists() else {}
        Q.atomic_json(path,{**state,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error)})
        raise
