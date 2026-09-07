"""Runtime-only sequential gate. No I scores are used; one timeout resume maximum."""
from pathlib import Path
import json,hashlib,subprocess,time,fcntl,os
ROOT=Path('/home/ubuntu/nba/handoff/r9j');I=ROOT.parent/'r9i';H=ROOT.parent/'r9h';OUT=ROOT/'results'
ORIGINAL='draftdb-r9i-20260907';RESUME='draftdb-r9i-resume1-20260907';J='draftdb-r9j-20260907'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):
 raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
def state(unit):
 r=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','Result','-p','MainPID','-p','ControlGroup','-p','InvocationID'],check=True,text=True,capture_output=True)
 return dict(line.split('=',1)for line in r.stdout.splitlines()if'='in line)
def validate_pins(a):
 assert sha(ROOT/'plan.json')==a['registered_plan_sha256']and sha(ROOT/'frozen.json')==a['frozen_sha256']
 for name,digest in read(ROOT/'frozen.json')['files'].items():assert sha(ROOT/name)==digest
 for folder,key,count in [(I,'I_frozen_sha256',15),(H,'H_frozen_sha256',81)]:
  assert sha(folder/'frozen.json')==a[key];f=read(folder/'frozen.json');assert len(f['files'])==count
  for name,digest in f['files'].items():assert sha(folder/name)==digest
def idle(unit):
 s=state(unit);assert s['ActiveState']in['inactive','failed']and s['MainPID']=='0'
 if s.get('ControlGroup'):
  folder=Path('/sys/fs/cgroup')/s['ControlGroup'].lstrip('/')
  if folder.exists():assert not any(p.read_text().strip()for p in folder.rglob('cgroup.procs'))
 return s
def durable_checkpoint():
 plan=read(I/'plan.json');allowed={f"{v['id']}_seed{s}"for v in plan['variants']for s in plan['seeds']};log=I/'results/completed.jsonl';raw=log.read_bytes();assert not raw or raw.endswith(b'\n');seen={}
 for line in raw.splitlines():
  e=json.loads(line);tid=e['task_id'];assert tid in allowed and tid not in seen and e['file']==tid+'.json'
  path=I/'results/tasks'/f'{tid}.json';assert sha(path)==e['sha256'];seen[tid]=e['sha256']
 actual={p.stem for p in (I/'results/tasks').glob('*.json')};assert set(seen)<=actual<=allowed;orphans=sorted(actual-set(seen));all_hashes=dict(seen)
 for tid in orphans:
  path=I/'results/tasks'/f'{tid}.json';assert read(path)['task_id']==tid;all_hashes[tid]=sha(path)
 return {'count':len(all_hashes),'logged_count':len(seen),'orphan_records_for_existing_Q_recovery':orphans,'log_bytes':len(raw),'log_sha256':hashlib.sha256(raw).hexdigest(),'task_map_sha256':hashlib.sha256(json.dumps(all_hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'record_hashes':all_hashes}
def run_unit(unit,script):
 subprocess.run(['sudo','-n','systemd-run','--unit',unit,'--property=RuntimeMaxSec=7200','--property=MemoryMax=140G','--property=CPUQuota=2200%','--property=KillMode=control-group','--property=WorkingDirectory='+str(script.parent),'--uid=ubuntu','--gid=ubuntu','/usr/bin/bash',str(script)],check=True)
def ready():
 path=I/'results/completion.json'
 if not path.exists():return False
 done=read(path);assert done['status']=='completed'and done['tasks']==336 and done['reference_gate']and done['saved_blends_complete']
 gate=read(I/'results/reference_gate.json');assert gate['passed']and gate['exact_references']==12
 progress=read(I/'results/postprocess_progress.json');assert progress['status']=='completed'and progress['recipes']==14256
 manifest=read(I/'results/blend_manifest.json');assert manifest['recipes']==14256 and manifest['all_endpoints_and_roundtrips_exact']
 for item in manifest['chunks']:assert sha(I/'results'/item['file'])==item['sha256']
 checkpoint=durable_checkpoint();assert checkpoint['count']==checkpoint['logged_count']==336
 recovery=OUT/'I_runtime_recovery.json'
 if recovery.exists():
  original=read(recovery)['checkpoint'];log=(I/'results/completed.jsonl').read_bytes();assert hashlib.sha256(log[:original['log_bytes']]).hexdigest()==original['log_sha256']
  assert all(checkpoint['record_hashes'][tid]==digest for tid,digest in original['record_hashes'].items())
 return {'completion_sha256':sha(path),'reference_gate_sha256':sha(I/'results/reference_gate.json'),'blend_manifest_sha256':sha(I/'results/blend_manifest.json'),'durable_checkpoint':checkpoint}
def main():
 OUT.mkdir(exist_ok=True);lock=(OUT/'sequential_queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 a=read(ROOT/'launch_authorization.json');assert a['model_fits_authorized']and a['queue_enabled']and a['one_runtime_only_I_timeout_resume_authorized'];validate_pins(a);assert read(OUT/'runtime_preflight.json')['passed']
 start=time.time();recovery=OUT/'I_runtime_recovery.json';launched=OUT/'sequential_launch.json'
 if launched.exists():assert read(launched)['J_unit']==J;return
 while time.time()-start<21600:
  unit=RESUME if recovery.exists()else ORIGINAL;s=state(unit)
  if s['ActiveState']in['active','activating','deactivating']:
   write(OUT/'queue_progress.json',{'status':'waiting','waiting_for':unit,'updated':time.time(),'J_models_started':False});time.sleep(30);continue
  idle(unit);proof=ready()
  if proof:
   assert s['Result']=='success';validate_pins(a);assert not (OUT/'state.json').exists()
   run_unit(J,ROOT/'run_sandbox.sh');write(launched,{'J_unit':J,'started_at':time.time(),'I_success_unit':unit,'I_readiness_proof':proof,'authorization_sha256':sha(ROOT/'launch_authorization.json'),'J_frozen_sha256':sha(ROOT/'frozen.json'),'no_I_scores_used':True});write(OUT/'queue_progress.json',{'status':'launched','unit':J,'updated':time.time()});return
  if unit==ORIGINAL and s['Result']=='timeout'and not recovery.exists():
   validate_pins(a);assert not (I/'results/completion.json').exists();idle(ORIGINAL);checkpoint=durable_checkpoint();assert state(RESUME).get('ActiveState')=='inactive'
   record={'reason':'Original I runtime cap; no science/code/data changes','original_unit':ORIGINAL,'original_state':s,'checkpoint':checkpoint,'I_frozen_sha256':sha(I/'frozen.json'),'H_frozen_sha256':sha(H/'frozen.json'),'resume_unit':RESUME,'resume_script':str(I/'run_sandbox.sh'),'workers':4,'runtime_seconds':7200,'memory_GiB':140,'CPU_quota_percent':2200,'created':time.time(),'one_attempt_only':True}
   with recovery.open('x')as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
   run_unit(RESUME,I/'run_sandbox.sh');continue
  raise RuntimeError(f'I did not finish cleanly; no retry authorized: {unit} {s}')
 raise TimeoutError('Sequential queue exceeded six-hour bound')
if __name__=='__main__':
 try:main()
 except BaseException as error:write(OUT/'queue_progress.json',{'status':'failed','error':repr(error),'updated':time.time(),'J_models_started':False});raise
