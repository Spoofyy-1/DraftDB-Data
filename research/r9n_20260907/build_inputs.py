"""Remote source reuse and CPU-only preprocessing admission; no predictive model fit."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,sys
import numpy as np
ROOT=Path(__file__).resolve().parent;M=ROOT.parent/'r9m';sys.path.insert(0,str(ROOT/'code'));import stack_core as C
import capacity

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,d):
 with p.open('x')as f:f.write(json.dumps(d,indent=2,allow_nan=False)+'\n')
def main():
 os.umask(0o077);p=read(ROOT/'code/protocol.json');assert sha(M/'frozen.json')==p['M_frozen_sha256']and sha(M/'code/protocol.json')==p['M_protocol_sha256']
 for f,h in read(M/'frozen.json')['files'].items():assert sha(M/f)==h,f
 for f,h in p['unchanged_source_files'].items():assert sha(ROOT/'code'/f)==sha(M/'code'/f)==h
 spec=importlib.util.spec_from_file_location('M_source_control_verifier',M/'reuse_controls.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);_,M_gate=mod.verify(M);assert M_gate['passed']
 complete=read(M/'results/completion.json');assert complete['status']=='completed'and complete['tasks']==24
 result_manifest=read(M/'results/result_manifest.json');assert sha(M/'results/result_manifest.json')==complete['result_manifest_sha256']and sha(M/'results/stack_diagnostics.json')==result_manifest['diagnostics_sha256']
 raw=(M/'results/completed.jsonl').read_bytes();assert raw.endswith(b'\n');rows=[json.loads(x)for x in raw.splitlines()];logged={r['task_id']:r for r in rows};assert len(logged)==len(rows)==24
 for d in ['inputs','source_inputs','source_refs','scoring','results']:(ROOT/d).mkdir(exist_ok=(d=='results'))
 (ROOT/'source_refs/records').mkdir();sources={};scoring={}
 for year in p['outer_years']:
  for panel in p['source_panels']:
   tid=f"{panel['id']}_y{year}";original=M/'inputs'/tid;im=read(original/'manifest.json');folder=ROOT/'source_inputs'/tid;folder.mkdir()
   assert im['columns']==panel['columns']and im['policy_id']==p['policy_id']and im['outer_year']==year
   for f,info in im['files'].items():assert sha(original/f)==info['sha256'];shutil.copyfile(original/f,folder/f)
   shutil.copyfile(original/'manifest.json',folder/'manifest.json');e=logged[tid];source=M/e['file'];assert sha(source)==e['sha256'];dest=ROOT/'source_refs/records'/f'{tid}.json';shutil.copyfile(source,dest)
   sources[tid]={'file':str(dest.relative_to(ROOT)),'sha256':sha(dest),'M_completed_entry':e,'M_input_manifest_sha256':sha(original/'manifest.json'),'M_input_manifest':im,'record_original_protocol_sha256':read(source)['protocol_sha256'],'record_original_input_manifest_sha256':read(source)['input_manifest_sha256']}
  src=M/'scoring'/f'{year}.npz';assert sha(src)==read(M/'plan.json')['scoring'][str(year)]['sha256'];dest=ROOT/'scoring'/f'{year}.npz';shutil.copyfile(src,dest);scoring[str(year)]={'sha256':sha(dest),'not_mounted_in_worker':True}
 for src,name in [(M/'frozen.json','M_frozen.json'),(M/'code/protocol.json','M_protocol.json'),(M/'results/completed.jsonl','M_completed.jsonl'),(M/'results/completion.json','M_completion.json'),(M/'source_refs/manifest.json','M_L_lineage.json')]:shutil.copyfile(src,ROOT/'source_refs'/name)
 diag_path=M/'results/stack_diagnostics.json';diag=read(diag_path);cross=[r for r in diag['cross_panel_prediction_details']if r['architecture']=='cross_0771'];same=[r for r in diag['prediction_details']if r['panel_id']=='f50_game_team'and r['architecture']=='stack_013'];assert len(cross)==len(same)==12
 save(ROOT/'source_refs/reference_recipes.json',{'M_diagnostics_sha256':sha(diag_path),'cross_0771':cross,'samepanel_stack_013':same})
 source_manifest={'M_frozen_sha256':sha(M/'frozen.json'),'M_protocol_sha256':sha(M/'code/protocol.json'),'M_runtime_sha256':sha(M/'code/runtime_support.json'),'M_completed_log_sha256':sha(M/'results/completed.jsonl'),'M_completion_sha256':sha(M/'results/completion.json'),'M_L_lineage_sha256':sha(M/'source_refs/manifest.json'),'M_source_gate':M_gate,'records':sources,'source_records_unchanged':True,'reference_recipes_sha256':sha(ROOT/'source_refs/reference_recipes.json')};save(ROOT/'source_refs/manifest.json',source_manifest)
 scan=capacity.scan(ROOT);save(ROOT/'results/preprocessing_scan.json',scan);mapping=scan['requested_to_evaluated'];baseline=p['baseline_profile_id'];active=[]
 for profile in p['profiles']:
  if profile['id']in mapping and mapping[profile['id']]==profile['id']:active.append(profile['id'])
 tasks=[]
 for pid in active:
  if pid==baseline:continue
  for year in p['outer_years']:
   tid=f'{pid}_y{year}';out=ROOT/'inputs'/tid;out.mkdir();source=ROOT/'source_inputs'/f'f50_game_team_y{year}';original=read(source/'manifest.json')
   for f in ['training.npz','inference.npz']:shutil.copyfile(source/f,out/f)
   m={**original,'task_id':tid,'profile_id':pid,'protocol_sha256':sha(ROOT/'code/protocol.json'),'preprocessing_designs':{str(s):scan['designs'][pid][f'{year}:{s}']for s in p['seeds']}}
   save(out/'manifest.json',m)
   with np.load(out/'training.npz',allow_pickle=False)as t,np.load(out/'inference.npz',allow_pickle=False)as q:nt,nq=len(t['pid']),len(q['pid'])
   tasks.append({'id':tid,'profile_id':pid,'panel_id':p['panel_id'],'policy_id':p['policy_id'],'outer_year':year,'input_manifest_sha256':sha(out/'manifest.json'),'training_rows':nt,'query_rows':nq})
 recipes=[];seen={}
 for original in p['stack_recipes']:
  if any(m['profile_id']is not None and m['profile_id']not in mapping for m in original['members']):continue
  r={**original,'members':[{**m,'profile_id':mapping[m['profile_id']]if m['profile_id']is not None else None}for m in original['members']]};key=json.dumps(r['members'],sort_keys=True,separators=(',',':'))
  if key in seen:recipes[seen[key]]['design_aliases']+=r['design_aliases']
  else:seen[key]=len(recipes);recipes.append(r)
 plan={'study':'R9N TabICL profile and fixed-family stack study','task_count':len(tasks),'tasks':tasks,'model_fits':3*len(tasks),'requested_new_model_jobs':66,'requested_new_model_fits':198,'reused_member_records':6,'active_profiles':active,'profile_mapping':mapping,'rejected_profiles':scan['rejected_profiles'],'baseline_profile_id':baseline,'outer_years':p['outer_years'],'seeds':p['seeds'],'protocol_sha256':sha(ROOT/'code/protocol.json'),'scoring':scoring,'stack_recipes':recipes,'stack_recipe_count':len(recipes),'reference_source_manifest_sha256':sha(ROOT/'source_refs/manifest.json'),'preprocessing_scan_sha256':sha(ROOT/'results/preprocessing_scan.json'),'workers':4,'target_percent':55,'full_pool_primary':True,'subset_secondary':True,'no_2019plus_scoring':True,'no_automatic_promotion':True}
 save(ROOT/'plan.json',plan);print(json.dumps({'new_jobs':len(tasks),'new_TabICL_fits':3*len(tasks),'active_profiles':len(active),'requested_profiles':23,'recipes':len(recipes),'rejected_profiles':scan['rejected_profiles'],'plan_sha256':sha(ROOT/'plan.json')}))
if __name__=='__main__':main()
