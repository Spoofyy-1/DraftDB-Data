"""Isolated model-free replay of every registered profile payload and source recipe gate."""
from pathlib import Path
import concurrent.futures as cf,hashlib,json,subprocess,time
import postprocess
ROOT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=json.loads((ROOT/'plan.json').read_text());assert len(p['tasks'])==p['task_count']<=66 and p['model_fits']==3*p['task_count'];_,gate=postprocess.reference_gate(ROOT)
 results=[]
 def one(t):
  subprocess.run(['/usr/bin/bash',str(ROOT/'run_task_sandbox.sh'),t['id'],'preflight'],check=True,capture_output=True,text=True)
  path=ROOT/'results/jobs'/t['id']/'preflight.json';r=json.loads(path.read_text());assert r['passed']and r['preflight_only']and r['model_fits']==0 and r['namespace_proof']['passed']and r['input_manifest_sha256']==t['input_manifest_sha256']and r['profile_id']==t['profile_id']
  assert r['training_rows']==t['training_rows']and r['query_rows']==t['query_rows'];return {'task_id':t['id'],'sha256':sha(path),'preprocessing_design_hash':r['preprocessing_design_hash']}
 with cf.ThreadPoolExecutor(max_workers=2)as pool:
  for r in pool.map(one,p['tasks']):results.append(r);print(json.dumps({'CPU_preflight':r['task_id'],'passed':True}),flush=True)
 tests=[]
 for name in ['test_n.py']:
  result=subprocess.run(['/home/ubuntu/nba/.venv/bin/python',str(ROOT/name)],check=True,capture_output=True,text=True);tests.append({'file':name,'sha256':sha(ROOT/name),'output':result.stdout+result.stderr})
 support=json.loads((ROOT/'code/runtime_support.json').read_text());count=0
 for section in ['sources','checkpoint_files']:
  for path,info in support[section].items():
   mapped=path.replace('/opt/venv/','/home/ubuntu/nba/.venv/',1).replace('/models/hub/','/home/ubuntu/.cache/huggingface/hub/',1);assert sha(Path(mapped))==(info['sha256']if isinstance(info,dict)else info);count+=1
 proof={'passed':True,'model_fits':0,'tasks_checked':len(results),'tasks':results,'tests':tests,'runtime_sources_checked':count,'reference_gate':gate,'protocol_sha256':sha(ROOT/'code/protocol.json'),'plan_sha256':sha(ROOT/'plan.json'),'preprocessing_scan_sha256':sha(ROOT/'results/preprocessing_scan.json'),'finished':time.time(),'scoring_files_mounted_in_worker':False}
 with (ROOT/'results/cpu_preflight.json').open('x')as f:f.write(json.dumps(proof,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:v for k,v in proof.items()if k not in ['tasks','tests']}))
if __name__=='__main__':main()
