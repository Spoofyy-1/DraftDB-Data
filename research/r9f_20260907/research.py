"""Frozen R9f study using the unchanged benchmark-verified scheduler."""
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
    verify_frozen();import preflight;preflight.prepare(gpu_fixture=False)
    Q.atomic_json(OUT/'preparation.json',{'passed':True,'registered_tasks':X.load_plan()['execution']['task_count'],'model_fits':0,'frozen_manifest_sha256':hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()})

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
            path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R9f CatBoost GPU fixed checkpoints',started=started,updated=time.time(),confirmation=None,test_result=None)
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
    state=json.loads((OUT/'state.json').read_text());state.update(status='postprocessing',phase='R9f registered saved-prediction blends',active_workers=0,current='All model fits complete; computing fixed saved-prediction blends.')
    Q.atomic_json(OUT/'state.json',state)
    import postprocess
    blends=postprocess.process(result['records'],OUT)
    state=json.loads((OUT/'state.json').read_text());state.update(status='completed',phase='R9f complete',current='',saved_blends=blends);Q.atomic_json(OUT/'state.json',state)
    Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':plan['execution']['task_count'],'scheduler_counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'workers':4,'no_model_promotion':True,'saved_blends_complete':True})

if __name__=='__main__':
    try:
        if '--gpu-fixture'in sys.argv:import preflight;preflight.prepare(gpu_fixture=True)
        elif '--prepare-only'in sys.argv:prepare()
        else:main()
    except BaseException as error:
        path=OUT/'state.json';state=json.loads(path.read_text()) if path.exists() else {}
        Q.atomic_json(path,{**state,'status':'failed','active_workers':0,'updated':time.time(),'error':repr(error)})
        raise
