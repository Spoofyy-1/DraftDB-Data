"""Frozen R9a queue, with unchanged benchmark-verified persistence/scheduler."""
import os
os.environ['OMP_NUM_THREADS']='3';os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import json,hashlib,time,sys,concurrent.futures as cf,multiprocessing as mp
import worker as A
import queue_runtime as Q
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def pool_factory(workers):return cf.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn'))
def verify_frozen():
    f=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in f['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    return f

def prepare():
    verify_frozen();p=A.load_plan();B=A.B;E,bp,g,folds=B._prepared();proof=[]
    deletes=[v for v in p['variants'] if v.get('kind')=='delete'];singles=[v for v in deletes if len(v['columns'])==1];doubles=[v for v in deletes if len(v['columns'])==2]
    checks=singles+[doubles[i] for i in [0,len(doubles)//2,len(doubles)-1]]+[v for v in p['variants'] if v.get('kind')=='permutation']
    for fold in folds:
        atr,ate,families,pair=A.full_design(fold);assert list(atr)==list(ate)==p['ordered_columns_by_fold'][str(fold['year'])]
        old=next(r for r in A.references()[0]['rows'] if r['season']==fold['year'])
        for seed in p['seeds']:
            ref=next(r for r in A.references()[seed]['rows'] if r['season']==fold['year'])
            assert ref['audit']['input_columns']==list(atr) and ref['audit']['families']==families and ref['audit']['pair_design']==pair
            for key,value in fold['audit'].items():assert ref['audit'][key]==value
        for v in checks:
            tr,te,_,_,audit=A.design(fold,v)
            expected=47-len(v['columns']) if v['kind']=='delete' else 47
            assert len(tr.columns)==len(te.columns)==expected
            if v['kind']=='permutation':
                for role in ['train','validation']:assert audit[role]['permutation']['original']==audit[role]['permutation']['permuted']
        proof.append({'year':fold['year'],'three_full_X_reference_input_audits_exact':True,'full_train_matrix_hash':B._matrix_hash(atr),'full_query_matrix_hash':B._matrix_hash(ate),'training_pid_hash':fold['audit']['training_pid_hash'],'query_pid_hash':fold['audit']['validation_pid_hash'],'labels_hash':fold['audit']['training_labels_hash'],'full_columns':list(atr),'design_checks':len(checks),'training_rows':len(atr),'query_rows':len(ate)})
    constructors=[]
    for seed in p['seeds']:
        for width in [45,46,47]:
            os.environ['SEED_SHIFT']=str(seed);_,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)[:width]));assert kwargs=={**p['model_constructor'],'random_state':seed};constructors.append({'width':width,'parameters':kwargs})
    Q.atomic_json(OUT/'preparation.json',{'passed':True,'models_fitted':0,'folds':proof,'constructors':constructors,'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()})
    print('R9a CPU preflight passed: exact full X inputs/labels/pids, deletion and same-mask/cohort permutation designs; no model fits.',flush=True)

def main():
    frozen=verify_frozen();p=A.load_plan();check=json.loads((OUT/'preparation.json').read_text());assert check['passed'] and check['frozen_manifest_sha256']==hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()
    registration={'plan':p,'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),'files':frozen['files']}
    path=OUT/'preregistered_plan.json'
    if path.exists():assert json.loads(path.read_text())==registration
    else:Q.atomic_json(path,registration)
    known={};started=time.time()
    def validate(entry):A.validate_entry(entry,p);known[entry['task_id']]=entry
    def event(kind,detail):
        if kind=='snapshot_end':
            path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R9a input deletion and permutation diagnostics',started=started,updated=time.time(),confirmation=None,test_result=None)
            for c in state['candidates']:
                record=known[c['task_id']];c['rows']=[{'season':r['season'],'stack':r['stack']} for r in record['rows']]
            real=[e for e in state['candidates'] if e['config'].get('kind')!='permutation']
            state['best']=max(real,key=lambda e:e['score']) if real and state['matched_summary']['interpretation_allowed'] else None
            state['active_workers']=0 if state['status']=='completed' else min(4,p['execution']['task_count']-state['completed'])
            state['current']=' | '.join(state['current']) if isinstance(state['current'],list) else state['current'];Q.atomic_json(path,state)
        elif kind=='persist_end':print(json.dumps({'completed_task':detail['task']}),flush=True)
    tasks=[(v['id'],s) for v in p['variants'] for s in p['seeds']]
    result=Q.run_queue(tasks,A.run_variant,[],OUT,validate,A.summarize_matched,pool_factory,workers=4,snapshot_seconds=3.,summary_seconds=20.,registration_hash=hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest(),event=event)
    assert result['completed_new']==3810
    Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':3810,'scheduler_counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'workers':4,'no_model_promotion':True})
if __name__=='__main__':
    try:
        if '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=OUT/'state.json';s=json.loads(path.read_text()) if path.exists() else {};Q.atomic_json(path,{**s,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error)});raise
