"""Four immediate-refill isolated TabICL jobs; frozen controls never refitted."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import concurrent.futures as cf,fcntl,hashlib,json,subprocess,time,sys
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';sys.path.insert(0,str(ROOT/'code'))
import postprocess,stack_predictions as S

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,x):
 temporary=p.with_suffix('.tmp')
 with temporary.open('w')as f:json.dump(x,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 temporary.replace(p)
def pins():
 a=read(ROOT/'launch_authorization.json');assert a['model_fits_authorized']and sha(ROOT/'plan.json')==a['plan_sha256']and sha(ROOT/'frozen.json')==a['frozen_sha256']
 for f,h in read(ROOT/'frozen.json')['files'].items():assert sha(ROOT/f)==h,f
 return a
def validate(r,t):
 m=read(ROOT/'inputs'/t['id']/'manifest.json');assert sha(ROOT/'inputs'/t['id']/'manifest.json')==t['input_manifest_sha256'];S.validate_job(r,t,m,read(ROOT/'code/protocol.json'))
def run(t):
 folder=OUT/'jobs'/t['id'];folder.mkdir(exist_ok=True,parents=True)
 with (folder/'worker.log').open('ab')as log:subprocess.run(['/usr/bin/bash',str(ROOT/'run_task_sandbox.sh'),t['id']],check=True,stdout=log,stderr=subprocess.STDOUT)
 path=folder/'result.json';r=read(path);validate(r,t);return r,{'task_id':t['id'],'file':str(path.relative_to(OUT)),'sha256':sha(path)}
def main():
 OUT.mkdir(exist_ok=True);lock=(OUT/'model_queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);a=pins();assert sha(OUT/'cpu_preflight.json')==a['cpu_preflight_sha256']and read(OUT/'cpu_preflight.json')['passed']
 p=read(ROOT/'plan.json');assert p['task_count']==len(p['tasks'])and p['model_fits']==3*len(p['tasks'])and len(p['tasks'])<=66
 _,gate=postprocess.reference_gate(ROOT);write(OUT/'reference_gate.json',gate);byid={t['id']:t for t in p['tasks']};completed={};entries={};logpath=OUT/'completed.jsonl'
 def append(e):
  with logpath.open('a')as f:f.write(json.dumps(e,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
 if logpath.exists():
  raw=logpath.read_bytes();assert not raw or raw.endswith(b'\n'),'Partial log tail requires explicit recovery'
  for line in raw.splitlines():
   e=json.loads(line);tid=e['task_id'];assert tid in byid and tid not in entries and e['file']==f'jobs/{tid}/result.json'and sha(OUT/e['file'])==e['sha256'];r=read(OUT/e['file']);validate(r,byid[tid]);completed[tid]=r;entries[tid]=e
 for tid,t in byid.items():
  path=OUT/'jobs'/tid/'result.json'
  if tid not in completed and path.exists():
   r=read(path);validate(r,t);e={'task_id':tid,'file':str(path.relative_to(OUT)),'sha256':sha(path),'recovered_after_publish':True};append(e);completed[tid]=r;entries[tid]=e
 started=time.monotonic();pending={};summary=postprocess.summarize(list(completed.values()),ROOT);last_summary=time.monotonic()
 def snapshot(status='running'):
  compact={k:v for k,v in summary.items()if k!='prediction_details'};best=compact['best_actual_multifamily_stack'];state={**compact,'status':status,'updated':time.time(),'completed':len(completed),'total':p['task_count'],'phase':'R9N TabICL profiles and fixed model-family stacks','current':' | '.join(t['id']for t in pending.values()),'workers':4,'active_workers':len(pending),'candidates':[],'message':'Only TabICL profiles are fitted; all Ridge/CatBoost and baseline predictions are reused with exact source and recipe gates.','model_fits_completed':3*len(completed),'model_fits_registered':p['model_fits'],'requested_model_fits':198,'reused_member_records':6,'elapsed_seconds':time.monotonic()-started,'no_model_promotion':True,'test_result':None,'confirmation':None}
  if best:state['best_configuration']={'id':best['architecture'],'score':best['full']['mean_score'],'seeds':3,'kind':'fixed_family_stack','profile_id':best['profile_id'],'panel_id':best['panel_id']}
  write(OUT/'state.json',state)
 tasks=[t for t in p['tasks']if t['id']not in completed]
 with cf.ThreadPoolExecutor(max_workers=4)as pool:
  def refill():
   while tasks and len(pending)<4:
    t=tasks.pop(0);pending[pool.submit(run,t)]=t
  refill();snapshot()
  while pending:
   ready,_=cf.wait(pending,timeout=5,return_when=cf.FIRST_COMPLETED)
   for future in ready:
    t=pending.pop(future);r,e=future.result();append(e);completed[t['id']]=r;entries[t['id']]=e;print(json.dumps({'completed':t['id'],'count':len(completed)}),flush=True)
   refill()
   if ready and (not pending or time.monotonic()-last_summary>=30):summary=postprocess.summarize(list(completed.values()),ROOT);last_summary=time.monotonic()
   snapshot()
 summary=postprocess.summarize(list(completed.values()),ROOT);assert len(completed)==p['task_count']and summary['scored_prediction_records']==p['stack_recipe_count']*12
 pins();write(OUT/'stack_diagnostics.json',summary);write(OUT/'result_manifest.json',{'tasks':entries,'diagnostics_sha256':sha(OUT/'stack_diagnostics.json'),'new_TabICL_fits':p['model_fits'],'reused_member_records':6,'recipe_prediction_records':summary['scored_prediction_records'],'no_2019_plus_scoring':True});snapshot('completed');write(OUT/'completion.json',{'status':'completed','tasks':len(completed),'new_TabICL_fits':p['model_fits'],'reused_member_records':6,'all_inputs_unchanged':True,'no_model_promotion':True,'result_manifest_sha256':sha(OUT/'result_manifest.json')})
if __name__=='__main__':
 try:main()
 except BaseException as e:
  OUT.mkdir(exist_ok=True);p=OUT/'state.json';old=read(p)if p.exists()else{};write(p,{**old,'status':'failed','error':repr(e),'active_workers':0,'updated':time.time()});raise
