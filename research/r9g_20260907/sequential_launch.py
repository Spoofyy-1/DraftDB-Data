"""Start frozen G once, only after F succeeds. Reads completion provenance, never candidate scores."""
from pathlib import Path
import json,hashlib,subprocess,time,sys
R=Path(__file__).resolve().parent;F=R.parent/'r9f';O=R/'results';F_UNIT='draftdb-r9f-20260907';G_UNIT='draftdb-r9g-20260907';F_SHA='1d3f47f8e1467636220c7907a549693664da033f984bcf54ce4ab2eab688f978'
def save(name,value):
 path=O/name;tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)
def frozen():
 payload=json.loads((R/'frozen.json').read_text())
 for name,digest in payload['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
 assert hashlib.sha256((F/'frozen.json').read_bytes()).hexdigest()==F_SHA
 return hashlib.sha256((R/'frozen.json').read_bytes()).hexdigest()
def gate(state,completion,unit):
 assert state.get('status')!='failed'and not state.get('error')and unit.get('ActiveState')!='failed'
 if unit.get('ActiveState')in ['active','activating','deactivating']or not completion:return False
 assert unit.get('ActiveState')=='inactive'and unit.get('Result')=='success'and unit.get('ExecMainStatus')=='0',unit
 assert completion['status']=='completed'and completion['tasks']==435 and completion['saved_blends_complete']
 assert state['status']=='completed'and state['completed']==435 and state['matched_summary']['reference_replays_passed']==3 and state['matched_summary']['interpretation_allowed']
 assert state['matched_summary']['completed_tasks']==435 and state['saved_blends']['all_endpoints_and_roundtrips_exact']
 return True

def main():
 digest=frozen();assert not (O/'sequential_launch.json').exists(),'Already launched; do not duplicate';started=time.time()
 save('queued.json',{'status':'queued','study':'r9g','tasks':1731,'blocked_on':F_UNIT,'frozen_sha256':digest,'F_frozen_sha256':F_SHA,'reads_candidate_scores':False,'updated':time.time()})
 while time.time()-started<10800:
  cp=F/'results/completion.json';sp=F/'results/state.json';state=json.loads(sp.read_text())if sp.exists()else{};completion=json.loads(cp.read_text())if cp.exists()else{}
  unit=dict(line.split('=',1)for line in subprocess.check_output(['systemctl','show',F_UNIT,'--property=ActiveState,Result,ExecMainStatus'],text=True).splitlines())
  if gate(state,completion,unit):break
  time.sleep(15)
 else:raise TimeoutError('F did not complete successfully within3h; G never started')
 assert frozen()==digest
 prep=json.loads((O/'CPU_preparation.json').read_text());assert prep['passed']and prep['frozen_manifest_sha256']==digest
 command=['sudo','-n','systemd-run','--unit='+G_UNIT,'--uid=ubuntu','--property=MemoryMax=150323855360','--property=CPUQuota=2200%','--property=RuntimeMaxSec=7200','--property=WorkingDirectory='+str(R),str(R/'run_registered.sh')]
 result=subprocess.run(command,check=True,text=True,capture_output=True)
 proof={'status':'launched','study':'r9g','tasks':1731,'unit':G_UNIT,'frozen_sha256':digest,'F_frozen_sha256':F_SHA,'F_success_gate':{'tasks':435,'exact_references':3,'saved_blends_complete':True,'unit':unit},'CPU_preflight_passed':True,'GPU_fixtures_pending_inside_unit':True,'launch_output':result.stdout+result.stderr,'updated':time.time()};save('sequential_launch.json',proof);save('queued.json',proof)
 queue={'current':proof,'queued':[]};path=R.parent/'research_queue.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(queue,indent=2)+'\n');tmp.replace(path)
 print(json.dumps(proof),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as error:
  save('queued.json',{'status':'failed','study':'r9g','error':repr(error),'updated':time.time()});raise
