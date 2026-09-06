"""Frozen identical-task scheduler benchmark, never a model-selection study."""
import os
os.environ['OMP_NUM_THREADS']='3';os.environ['OPENBLAS_NUM_THREADS']='3'
from pathlib import Path
import sys,json,hashlib,time,concurrent.futures as cf,multiprocessing as mp
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'model'))
import worker as W
import queue_runtime as Q


def run_one(vid,seed):
    r=W.run_variant(vid,seed);r['task_id']=f'{vid}_seed{seed}';r['seed']=seed;return r


def pool_factory(workers):return cf.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn'))


def exact_reference(record,reference):
    assert 'error' not in record,record.get('error')
    assert record['config']==reference['config'] and record['seed']==reference['seed']
    assert record['score']==reference['score'],('Score changed',record['task_id'])
    assert len(record['rows'])==len(reference['rows'])
    for a,b in zip(record['rows'],reference['rows']):
        assert a['season']==b['season'] and a['stack']==b['stack'] and a['predictions']==b['predictions'],('Predictions changed',record['task_id'],a['season'])
        assert a['audit']==b['audit'],('Input/constructor/tie audit changed',record['task_id'],a['season'])
    return True


def run_old(tasks,initial,source_state,out,validate,workers,progress):
    out.mkdir(exist_ok=True);state={**source_state,'candidates':list(initial),'completed':len(initial),'status':'running'}
    todo=list(tasks);pending={};started=time.perf_counter();counts={'snapshots':0,'summaries':0}
    def write():
        state['updated']=time.time();state['matched_summary']=W.summarize_matched(state['candidates']);counts['summaries']+=1
        tmp=out/'state.tmp';tmp.write_text(json.dumps(state,indent=2,allow_nan=False));tmp.replace(out/'state.json');counts['snapshots']+=1
    write()
    with pool_factory(workers) as pool:
        while todo or pending:
            while todo and len(pending)<workers:
                task=todo.pop(0);pending[pool.submit(run_one,*task)]=task
            state['current']=' | '.join(f'{v} seed{s}' for v,s in pending.values());write()
            ready,_=cf.wait(pending,timeout=10,return_when=cf.FIRST_COMPLETED)
            for future in ready:
                task=pending.pop(future);record=future.result();validate(record);state['candidates'].append(record);state['completed']+=1;progress(state['completed']-len(initial))
            good=[r for r in state['candidates'] if 'score'in r and 'permuted'not in r['config'].get('arms',{}).values()]
            state['best']=max(good,key=lambda r:r['score']) if good and state['matched_summary'].get('interpretation_allowed') else None
            state['elapsed_seconds']=time.perf_counter()-started;write()
    state.update(status='completed',current='Queue complete');write()
    return {'elapsed_seconds':time.perf_counter()-started,'completed_new':len(tasks),'records':state['candidates'],'counts':counts}


def prepare():
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in frozen['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    state=json.loads((ROOT/'reference_state.json').read_text());refs={e['task_id']:e for e in state['candidates']}
    plan=json.loads((ROOT/'plan.json').read_text());E,model_plan,g,folds=W._prepared();checks=[]
    for vid,seed in plan['tasks']:
        config=next(v for v in model_plan['variants'] if v['id']==vid)
        ref=refs[f'{vid}_seed{seed}']
        for fold,expected in zip(folds,ref['rows']):
            atr,ate,families=W._design(fold,config,model_plan)
            for key,value in fold['audit'].items():assert value==expected['audit'][key],(vid,seed,fold['year'],key)
            assert families==expected['audit']['families'] and list(atr)==expected['audit']['input_columns']
            assert [W._hash(key) for key in W._exact_vector_keys(ate)]==expected['audit']['canonical_prediction_ties']['row_vector_hashes']
        checks.append({'task':f'{vid}_seed{seed}','all_input_label_id_column_audits_exact':True})
    configurations=[]
    for seed in model_plan['seeds']:
        os.environ['SEED_SHIFT']=str(seed);_,kwargs=W.make_registered_model(E.cfg_of('tabicl',g,list(atr)))
        configurations.append(kwargs)
    result={'passed':True,'models_fitted':0,'tasks':checks,'constructors':configurations,
            'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()}
    Q.atomic_json(ROOT/'results/preparation.json',result);print('All24 tasks exactly match frozen W CPU input/label/id/column/audits; no predictor fit.',flush=True)


def main():
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in frozen['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    preparation=json.loads((ROOT/'results/preparation.json').read_text())
    assert preparation['passed'] and preparation['frozen_manifest_sha256']==hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()
    plan=json.loads((ROOT/'plan.json').read_text());state=json.loads((ROOT/'reference_state.json').read_text())
    assert state['status']=='completed' and state['completed']==603 and all('error'not in e for e in state['candidates'])
    tasks=[tuple(t) for t in plan['tasks']];ids={f'{v}_seed{s}' for v,s in tasks}
    reference={e['task_id']:e for e in state['candidates']}
    assert len(ids)==24 and ids<=set(reference)
    initial=[e for e in state['candidates'] if e['task_id']not in ids];assert len(initial)==579
    def validate(record):
        assert record['task_id'] in ids;exact_reference(record,reference[record['task_id']])
    results=[]
    for arm_index,arm in enumerate(plan['arms']):
        def progress(n):
            Q.atomic_json(ROOT/'results/progress.json',{'status':'running','phase':arm['id'],'completed':arm_index*24+n,'total':72,'phase_completed':n,'phase_total':24,'active_workers':min(arm['workers'],24-n),'updated':time.time(),'model_selection':False})
        progress(0)
        persisted=[0]
        def event(kind,detail):
            if kind=='persist_end':persisted[0]+=1;progress(persisted[0])
        out=ROOT/'results'/arm['id'];assert not out.exists(),'Fresh benchmark arms required'
        start=time.perf_counter()
        if arm['scheduler']=='old':r=run_old(tasks,initial,state,out,validate,arm['workers'],progress)
        else:r=Q.run_queue(tasks,run_one,initial,out,validate,W.summarize_matched,pool_factory,workers=arm['workers'],snapshot_seconds=3.,summary_seconds=20.,registration_hash=hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),event=event)
        queue_seconds=time.perf_counter()-start
        progress(24)
        actual={e['task_id']:e for e in r['records'] if e['task_id']in ids};assert set(actual)==ids
        for tid,entry in actual.items():exact_reference(entry,reference[tid])
        summary=W.summarize_matched(r['records']);assert summary==state['matched_summary']
        item={'arm':arm,'elapsed_seconds':queue_seconds,'scheduler_internal_seconds':r['elapsed_seconds'],'replays':len(actual),'trials_per_minute':len(actual)*60/queue_seconds,
              'all_raw_canonical_scores_and_audits_exact':True,'full_summary_exact':True,'counts':r['counts'],
              'compact_or_full_state_bytes':(out/'state.json').stat().st_size,'duration_including_postcheck':time.perf_counter()-start,
              'task_seconds':[actual[tid]['seconds'] for tid in sorted(actual)]}
        results.append(item);Q.atomic_json(ROOT/'results'/'timing.json',{'status':'running','arms':results,'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()})
        print(json.dumps({k:v for k,v in item.items() if k!='task_seconds'}),flush=True)
    Q.atomic_json(ROOT/'results/progress.json',{'status':'completed','phase':'complete','completed':72,'total':72,'active_workers':0,'updated':time.time(),'model_selection':False})
    Q.atomic_json(ROOT/'results'/'timing.json',{'status':'completed','arms':results,'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),'no_model_selection':True,'replays':72})

if __name__=='__main__':
    try:
        if '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=ROOT/'results/progress.json'
        prior=json.loads(path.read_text()) if path.exists() else {}
        Q.atomic_json(path,{**prior,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error),'model_selection':False})
        raise
