"""One isolated year at a time; actual completion progress, no evaluation scoring."""
from pathlib import Path
import fcntl,hashlib,json,subprocess,time
ROOT=Path('/home/ubuntu/nba/handoff/r9test');OUT=ROOT/'results';CODE=ROOT/'code';YEARS=list(range(2019,2026))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def unit(year):return f'draftdb-r9test-{year}-20260907'
def state(year):
 result=subprocess.run(['systemctl','show',unit(year),'-p','ActiveState','-p','Result','-p','ExecMainStatus','-p','InvocationID'],capture_output=True,text=True);return dict(line.split('=',1)for line in result.stdout.strip().splitlines()if'='in line)
def completed():
 done=[]
 for year in YEARS:
  root=OUT/str(year);p=root/'completion.json'
  if not p.exists():continue
  c=json.loads(p.read_text());assert c['year']==year and c['seeds']==[0,101,202]and c['scoring_performed']is False;assert sha(root/'predictions.json')==c['predictions_sha256']and sha(root/'predictions.csv')==c['predictions_csv_sha256'];done.append(year)
 return done
def progress(status,phase,year=None,**extra):
 done=completed();save(OUT/'progress.json',{'status':status,'phase':phase,'completed':len(done),'total':7,'updated':time.time(),'currentlyear':year,'completed_years':done,'scores_available':False,**extra})
def main():
 OUT.mkdir(exist_ok=True);lock=(OUT/'year_queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 approval=json.loads((CODE/'approval.json').read_text());frozen=json.loads((CODE/'frozen.json').read_text());recipe=json.loads((CODE/'recipe.json').read_text());assert approval['approved']and approval['reference_gate_passed']and approval['frozen_code_sha256']==sha(CODE/'frozen.json')and approval['recipe_sha256']==sha(CODE/'recipe.json')and approval['scoring_policy_sha256']==recipe['scoring_policy_sha256'];assert approval['year_orchestrator_sha256']==sha(Path(__file__))
 for name,digest in frozen['files'].items():assert sha(CODE/name)==digest
 for name,digest in frozen['launchers'].items():assert sha(ROOT/name)==digest
 assert set(approval['year_manifest_sha256'])==set(map(str,YEARS))
 for year in YEARS:
  mp=ROOT/'bundles'/str(year)/'manifest.json';assert sha(mp)==approval['year_manifest_sha256'][str(year)]==frozen['year_manifest_sha256'][str(year)];m=json.loads(mp.read_text())
  for name,meta in m['files'].items():assert sha(mp.parent/name)==meta['sha256']
 assert json.loads((OUT/'reference/reference_gate.json').read_text())['passed']
 progress('running','Frozen inputs approved; predicting one cohort at a time')
 for year in YEARS:
  if year in completed():continue
  assert not any(state(y).get('ActiveState')in['active','activating']for y in YEARS if y!=year),'Another year is active'
  st=state(year)
  if st.get('ActiveState')not in['active','activating']:
   assert st.get('Result')in[None,'success']and st.get('ExecMainStatus')in[None,'0'],'Previous failed year requires explicit review'
   free=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip().splitlines()[0])
   if free<20480:
    progress('waiting_for_gpu_memory','Need20GiB free; I remains unchanged',year,free_GPU_MiB=free);print('Insufficient GPU memory; root may authorize bounded I pause.',flush=True);return
   command=['sudo','-n','systemd-run','--unit='+unit(year),'--uid=ubuntu','--property=MemoryMax=25769803776','--property=CPUQuota=200%','--property=RuntimeMaxSec=1800','--property=WorkingDirectory='+str(ROOT),'/bin/bash',str(ROOT/'run_year_sandbox.sh'),str(year)];subprocess.run(command,check=True)
  progress('running','Predicting frozen cohort; no scores read',year)
  while state(year).get('ActiveState')in['active','activating']:time.sleep(2)
  st=state(year);assert st.get('Result')=='success'and st.get('ExecMainStatus')=='0'and year in completed(),(year,st)
  progress('running','Cohort predictions complete; retained raw seed audits',year);print(json.dumps({'year':year,'completed':len(completed()),'total':7,'no_scores_read':True}),flush=True)
 assert completed()==YEARS;progress('completed','All seven predictions ready for independent freeze verification; no scores read');save(OUT/'prediction_queue_completion.json',{'completed_years':YEARS,'all7_complete':True,'no_test_answers_or_scores_read':True,'updated':time.time()})
if __name__=='__main__':
 try:main()
 except BaseException as error:
  progress('failed','Prediction queue stopped; preserve all outputs',error=repr(error));raise
