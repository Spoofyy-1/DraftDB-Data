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
    verify_frozen();plan=X.load_plan();B=X.B;E,bp,g,folds=B._prepared();refs=X.reference_records();proof=[]
    for fold in folds:
        baseline=next(r for r in refs[('baseline',0)]['rows'] if r['season']==fold['year'])
        for key,value in fold['audit'].items():assert value==baseline['audit'][key],(fold['year'],key)
        assert all(f in fold['source_columns']['fifty'] for f in plan['selected_features'])
        for vid in plan['reference_ids']:
            expected=next(r for r in refs[(vid,0)]['rows'] if r['season']==fold['year'])
            if vid=='pair06_RR':
                F=X.frozen_x();fp=F.load_plan();v=next(v for v in fp['variants'] if v['id']==vid);atr,ate,families,pa=F.design_pair(fold,v,fp,bp);assert pa==expected['audit']['pair_design']
            else:
                v=next(v for v in bp['variants'] if v['id']==vid);atr,ate,families=B._design(fold,v,bp)
            assert families==expected['audit']['families'] and list(atr)==expected['audit']['input_columns']
            assert [B._hash(k) for k in B._exact_vector_keys(ate)]==expected['audit']['canonical_prediction_ties']['row_vector_hashes']
        representative=[plan['pairs'][i] for i in [0,len(plan['pairs'])//2,len(plan['pairs'])-1]]
        for v in plan['variants']:
            if v.get('pair')in representative and (v['arm']=='RR' or v['permutation_seed']==9317):
                atr,ate,f,pa=X.design_pair(fold,v,plan,bp);assert atr.shape[1]==47
        proof.append({'year':fold['year'],'reference_designs_exact':21,'all19_fields_training_eligible':True,'representative_pair_arms':12,'training_rows':len(fold['tr']),'query_rows':len(fold['te'])})
    constructors=[]
    for seed in plan['seeds']:
        os.environ['SEED_SHIFT']=str(seed);_,kwargs=B.make_registered_model(E.cfg_of('tabicl',g,list(atr)));constructors.append(kwargs)
    Q.atomic_json(OUT/'preparation.json',{'passed':True,'models_fitted':0,'folds':proof,'constructors':constructors,'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()})
    print('Z exact reference/input/label/column and representative control designs passed; no prediction.',flush=True)

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
            path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R8z broader pair screen',started=started,updated=time.time(),confirmation=None,test_result=None)
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
    Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':plan['execution']['task_count'],'scheduler_counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'workers':4,'no_model_promotion':True})

if __name__=='__main__':
    try:
        if '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=OUT/'state.json';state=json.loads(path.read_text()) if path.exists() else {}
        Q.atomic_json(path,{**state,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error)})
        raise
