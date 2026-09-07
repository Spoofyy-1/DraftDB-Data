"""Four-worker immediate-refill queue. No benchmark answer access during fitting."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import concurrent.futures as cf,fcntl,json,subprocess,time
from verify import ROOT,sha,read,pins,validate,save_new
OUT=ROOT/'results'
def write(p,v):
 t=p.with_suffix('.tmp')
 with t.open('w') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 t.replace(p)
def run(t):
 folder=OUT/'jobs'/t['id'];folder.mkdir(exist_ok=True,parents=True)
 with (folder/'worker.log').open('ab') as log:subprocess.run(['bash',str(ROOT/'run_task_sandbox.sh'),t['id']],stdout=log,stderr=subprocess.STDOUT,check=True)
 p=folder/'result.json';r=read(p);proof=validate(r,t)
 return {'task_id':t['id'],'file':str(p.relative_to(OUT)),'sha256':sha(p),'verification':proof}
def main():
 OUT.mkdir(exist_ok=True);lock=(OUT/'queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 plan=pins();byid={t['id']:t for t in plan['tasks']};assert len(byid)==7
 done={};log=OUT/'completed.jsonl';started=time.monotonic();pending={}
 def append(e):
  with log.open('a') as f:f.write(json.dumps(e)+'\n');f.flush();os.fsync(f.fileno())
 if log.exists():
  raw=log.read_bytes();assert not raw or raw.endswith(b'\n'),'Partial completion tail requires explicit recovery'
  for line in raw.splitlines():
   e=json.loads(line);tid=e['task_id'];assert tid in byid and tid not in done
   assert e['file']==f'jobs/{tid}/result.json' and sha(OUT/e['file'])==e['sha256']
   validate(read(OUT/e['file']),byid[tid]);done[tid]=e
 for tid,t in byid.items():
  p=OUT/'jobs'/tid/'result.json'
  if tid not in done and p.exists():
   v=validate(read(p),t);e={'task_id':tid,'file':str(p.relative_to(OUT)),'sha256':sha(p),'verification':v,'recovered_immutable_file':True};append(e);done[tid]=e
 def snapshot(status):
  write(OUT/'state.json',{'phase':'Recovered fixed stack: 2019–2025 test','status':status,'updated':time.time(),'completed':len(done),'total':7,'active_workers':len(pending),'workers':4,'current':' | '.join(t['id'] for t in pending.values()),'model_fits_completed':26*len(done),'model_fits_registered':182,'elapsed_seconds':time.monotonic()-started,'error':None,'test_scores_read':(OUT/'test_result.json').exists(),'message':'Fixed archived weights; date-limited observed prefixes;127 reviewed inputs. Freeze all seven predictions before benchmark scoring.'})
 tasks=[t for t in plan['tasks'] if t['id'] not in done]
 with cf.ThreadPoolExecutor(max_workers=4) as pool:
  def refill():
   while tasks and len(pending)<4:
    t=tasks.pop(0);pending[pool.submit(run,t)]=t
  refill();snapshot('predicting')
  while pending:
   ready,_=cf.wait(pending,timeout=5,return_when=cf.FIRST_COMPLETED)
   for f in ready:
    t=pending.pop(f);e=f.result();append(e);done[t['id']]=e;print(json.dumps({'completed_year':t['year'],'completed':len(done)}),flush=True)
   refill();snapshot('predicting')
 pins();assert len(done)==7
 if not (OUT/'prediction_freeze.json').exists():
  save_new(OUT/'prediction_freeze.json',{'frozen_at':time.time(),'all_seven_predictions_complete_before_answers':True,'plan_sha256':sha(ROOT/'plan.json'),'scorer_sha256':sha(ROOT/'score_frozen.py'),'frozen_sha256':sha(ROOT/'frozen.json'),'tasks':done})
 snapshot('predictions_frozen_pending_scoring')
 subprocess.run(['/home/ubuntu/nba/.venv/bin/python',str(ROOT/'score_frozen.py')],check=True)
 pins();snapshot('completed')
 if not (OUT/'completion.json').exists():save_new(OUT/'completion.json',{'status':'completed','model_fits':182,'jobs':7,'prediction_freeze_sha256':sha(OUT/'prediction_freeze.json'),'test_result_sha256':sha(OUT/'test_result.json'),'elapsed_seconds':time.monotonic()-started})
if __name__=='__main__':
 try:main()
 except BaseException as e:
  OUT.mkdir(exist_ok=True);p=OUT/'state.json';s=read(p) if p.exists() else {};write(p,{**s,'status':'failed','error':repr(e),'active_workers':0,'updated':time.time()});raise
