"""Four isolated new-panel jobs; six exact source controls imported without refitting."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import concurrent.futures as cf,fcntl,hashlib,json,subprocess,time
import postprocess,reuse_controls
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,x):
 temporary=p.with_suffix('.tmp')
 with temporary.open('w')as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 temporary.replace(p)
def verify_pins():
 a=read(ROOT/'launch_authorization.json');assert a['model_fits_authorized']and sha(ROOT/'plan.json')==a['plan_sha256']and sha(ROOT/'frozen.json')==a['frozen_sha256']
 for name,digest in read(ROOT/'frozen.json')['files'].items():assert sha(ROOT/name)==digest,name
 return a
def validate(r,task,source):
 assert r['task_id']==task['id']and r['outer_year']==task['outer_year']and r['panel_id']==task['panel_id']and r['policy_id']==task['policy_id']
 if task['kind']=='reused_L_control':assert r==source[task['id']];return
 assert task['kind']=='new_model_job'and r['input_manifest_sha256']==task['input_manifest_sha256']and r['protocol_sha256']==sha(ROOT/'code/protocol.json')
 assert r['fit_counts']=={'ridge_a30':1,'ridge_a300':1,'ridge_a3000':1,'tabicl':3,'catboost':3}and not r['query_outcome_labels_accessed']and not r['learned_weights']
 assert [s['seed']for s in r['seed_results']]==[0,101,202]
 for s in r['seed_results']:
  assert set(s['architectures'])=={x['id']for x in read(ROOT/'plan.json')['architectures']}and set(s['members'])=={'tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost'}
def run(task):
 assert task['kind']=='new_model_job';folder=OUT/'jobs'/task['id'];folder.mkdir(exist_ok=True,parents=True)
 with (folder/'worker.log').open('ab')as log:subprocess.run(['/usr/bin/bash',str(ROOT/'run_task_sandbox.sh'),task['id']],check=True,stdout=log,stderr=subprocess.STDOUT)
 path=folder/'result.json';r=read(path);validate(r,task,{})
 return r,{'task_id':task['id'],'file':str(path.relative_to(ROOT)),'sha256':sha(path),'kind':'new_model_job'}
def main():
 OUT.mkdir(exist_ok=True);lock=(OUT/'model_queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);auth=verify_pins()
 assert sha(OUT/'cpu_preflight.json')==auth['cpu_preflight_sha256']and read(OUT/'cpu_preflight.json')['passed']
 p=read(ROOT/'plan.json');assert len(p['tasks'])==24 and p['new_model_jobs']==18 and p['model_fits']==162
 imported,gate=reuse_controls.verify(ROOT);source={r['task_id']:r for r in imported};assert len(source)==6;write(OUT/'reference_gate.json',gate)
 byid={t['id']:t for t in p['tasks']};completed={};entries={};log_path=OUT/'completed.jsonl'
 def append(e):
  with log_path.open('a')as f:f.write(json.dumps(e,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
 if log_path.exists():
  raw=log_path.read_bytes();assert not raw or raw.endswith(b'\n'),'Partial completion-log tail requires explicit recovery'
  for line in raw.splitlines():
   e=json.loads(line);tid=e['task_id'];assert tid in byid and tid not in entries
   expected=f'source_refs/records/{tid}.json'if byid[tid]['kind']=='reused_L_control'else f'results/jobs/{tid}/result.json'
   assert e['file']==expected and e['kind']==byid[tid]['kind']and sha(ROOT/e['file'])==e['sha256'];r=read(ROOT/e['file']);validate(r,byid[tid],source);completed[tid]=r;entries[tid]=e
 for tid,r in source.items():
  if tid not in completed:
   path=ROOT/'source_refs/records'/f'{tid}.json';e={'task_id':tid,'file':str(path.relative_to(ROOT)),'sha256':sha(path),'kind':'reused_L_control','new_model_fits':0};append(e);completed[tid]=r;entries[tid]=e
 for tid,t in byid.items():
  path=OUT/'jobs'/tid/'result.json'
  if t['kind']=='new_model_job'and tid not in completed and path.exists():
   r=read(path);validate(r,t,source);e={'task_id':tid,'file':str(path.relative_to(ROOT)),'sha256':sha(path),'kind':'new_model_job','recovered_after_publish':True};append(e);completed[tid]=r;entries[tid]=e
 start=time.monotonic();pending={};summary=postprocess.summarize(list(completed.values()),ROOT)
 def snapshot(status='running'):
  compact={k:v for k,v in summary.items()if k not in ['prediction_details','cross_panel_prediction_details']};eligible=[b for b in [compact['best_actual_multifamily_stack'],compact.get('best_cross_panel_actual_stack')]if b and b['multi_family_every_fold_seed']];best=max(eligible,key=lambda b:b['full']['mean_score'])if eligible else None;nnew=sum(byid[k]['kind']=='new_model_job'for k in completed)
  state={**compact,'status':status,'updated':time.time(),'completed':len(completed),'total':24,'phase':'R9M feature combinations and cross-panel fixed family stacks','current':' | '.join(t['id']for t in pending.values()),'workers':4,'active_workers':len(pending),'candidates':[],'message':'Six exact L control records reused; 18 new isolated jobs. Fixed cross-panel weights use saved predictions only.','new_jobs_completed':nnew,'model_fits_completed':9*nnew,'model_fits_registered':162,'reused_control_records':6,'reused_original_model_fits':54,'elapsed_seconds':time.monotonic()-start,'no_model_promotion':True,'test_result':None,'confirmation':None}
  if best:state['best_configuration']={'id':best['architecture'],'score':best['full']['mean_score'],'seeds':3,'kind':'fixed_family_stack','panel_id':best['panel_id']}
  write(OUT/'state.json',state)
 tasks=[t for t in p['tasks']if t['kind']=='new_model_job'and t['id']not in completed]
 with cf.ThreadPoolExecutor(max_workers=4)as pool:
  def refill():
   while tasks and len(pending)<4:
    t=tasks.pop(0);pending[pool.submit(run,t)]=t
  refill();snapshot()
  while pending:
   ready,_=cf.wait(pending,timeout=5,return_when=cf.FIRST_COMPLETED)
   for future in ready:
    task=pending.pop(future);r,e=future.result();append(e);completed[task['id']]=r;entries[task['id']]=e;print(json.dumps({'completed':task['id'],'count':len(completed)}),flush=True)
   refill()
   if ready:summary=postprocess.summarize(list(completed.values()),ROOT)
   snapshot()
 assert len(completed)==24 and summary['scored_prediction_records']==4128 and summary['cross_panel_scored_prediction_records']==11400
 verify_pins();reuse_controls.verify(ROOT);write(OUT/'stack_diagnostics.json',summary);write(OUT/'result_manifest.json',{'tasks':entries,'diagnostics_sha256':sha(OUT/'stack_diagnostics.json'),'new_model_fits':162,'reused_original_model_fits':54,'scoring_records':4128,'cross_panel_scoring_records':11400,'no_2019_plus_scoring':True});snapshot('completed')
 write(OUT/'completion.json',{'status':'completed','tasks':24,'new_model_jobs':18,'new_model_fits':162,'reused_control_records':6,'reused_original_model_fits':54,'all_inputs_unchanged':True,'no_model_promotion':True,'result_manifest_sha256':sha(OUT/'result_manifest.json')})
if __name__=='__main__':
 try:main()
 except BaseException as e:
  OUT.mkdir(exist_ok=True);p=OUT/'state.json';old=read(p)if p.exists()else{};write(p,{**old,'status':'failed','error':repr(e),'active_workers':0,'updated':time.time()});raise
