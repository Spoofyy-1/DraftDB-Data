"""Existing append-only scheduler; exact original B gate precedes new training policies."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,time,hashlib,concurrent.futures as cf,multiprocessing as mp
import worker as W
import queue_runtime as Q
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def pool(workers):return cf.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn'))
def main():
 p=W.plan();authorization=json.loads((ROOT/'launch_authorization.json').read_text());assert authorization['model_fits_authorized']and authorization['registered_plan_sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
 f=json.loads((ROOT/'frozen.json').read_text());fsha=hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest();tasks=[(v['id'],seed)for v in p['variants']for seed in p['seeds']];ids=[f'{v}_seed{s}'for v,s in tasks]
 registration={'plan':p,'plan_sha256':hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest(),'files':f['files']};path=OUT/'preregistered_plan.json'
 if path.exists():assert json.loads(path.read_text())==registration
 else:Q.atomic_json(path,registration)
 qreg={'registration_hash':fsha,'initial_records_sha256':Q.digest(b'[]'),'task_ids':ids,'workers':4,'snapshot_seconds':3.,'summary_seconds':20.};path=OUT/'queue_registration.json'
 if path.exists():assert json.loads(path.read_text())==qreg
 else:Q.atomic_json(path,qreg)
 directory=OUT/'tasks';directory.mkdir(exist_ok=True);known={}
 def validate(e):W.validate_entry(e);known[e['task_id']]=e
 existing=Q.load_completed(directory,OUT/'completed.jsonl',set(ids),validate)
 refs=[(v,s)for v,s in tasks if v=='drop5_001'and f'{v}_seed{s}'not in existing]
 if refs:
  Q.atomic_json(OUT/'state.json',{'status':'running','phase':'R9h exact original B references before new fits','completed':len(existing),'total':192,'active_workers':len(refs),'test_result':None,'confirmation':None,'candidates':[]})
  with pool(len(refs))as executor:
   futures=[executor.submit(W.run_variant,*t)for t in refs]
   for future in cf.as_completed(futures):
    e=future.result();validate(e);path,sha=Q.save_immutable(directory,e);Q.append_record(OUT/'completed.jsonl',e['task_id'],path,sha);existing[e['task_id']]=e
 assert W.summarize(list(existing.values()))['reference_replays_passed']==3
 Q.atomic_json(OUT/'reference_gate.json',{'passed':True,'original_B_references':3,'all_before_new_model_fits':True,'frozen_sha256':fsha})
 def event(kind,detail):
  if kind=='snapshot_end':
   path=OUT/'state.json';state=json.loads(path.read_text());state.update(phase='R9h observed-label training; both metrics are diagnostics',updated=time.time(),confirmation=None,test_result=None,active_workers=0 if state['status']=='completed'else min(4,192-state['completed']))
   for candidate in state['candidates']:
    e=known[candidate['task_id']];candidate.update(legacy_score=e['legacy_score'],observed_score=e['observed_score'],rows=[{'season':r['season'],'stack':r['stack'],'observed_stack':r['observed_mask_score']}for r in e['rows']])
   state['best']=None;state['current']=' | '.join(state['current']);Q.atomic_json(path,state)
  elif kind=='persist_end':print(json.dumps({'completed_task':detail['task']}),flush=True)
 result=Q.run_queue(tasks,W.run_variant,[],OUT,validate,W.summarize,pool,workers=4,snapshot_seconds=3.,summary_seconds=20.,registration_hash=fsha,event=event)
 assert result['completed_new']==192;Q.atomic_json(OUT/'completion.json',{'status':'completed','tasks':192,'elapsed_seconds':result['elapsed_seconds'],'reference_gate':True,'both_metrics_saved':True,'no_model_promotion':True})
if __name__=='__main__':
 try:main()
 except BaseException as error:
  path=OUT/'state.json';s=json.loads(path.read_text())if path.exists()else{};Q.atomic_json(path,{**s,'status':'failed','error':repr(error),'active_workers':0,'updated':time.time()});raise
