from pathlib import Path
import json,hashlib,shutil,itertools
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8w'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
reg=json.loads((ROOT.parent/'r8x_registration/registration.json').read_text())
assert sha(SOURCE/'results/state.json')==reg['source_state_sha256']
state=json.loads((SOURCE/'results/state.json').read_text());assert state['status']=='completed' and state['completed']==603
stats=state['matched_summary']['statistics']
selected=sorted(r['id'] for r in stats if r['real_minus_baseline_context_only']>0 and min(r['fold_gains'].values())>0 and min(r['seed_gains'].values())>0)
assert selected==reg['selected_features'] and list(map(list,itertools.combinations(selected,2)))==reg['pairs']
source_plan=json.loads((SOURCE/'plan.json').read_text())
assert source_plan['seeds']==reg['seeds'] and source_plan['permutation_seeds']==reg['permutation_seeds']
for name in ['worker.py','legacy_kernel.py','plan.json','baseline_reference.json']:shutil.copyfile(SOURCE/name,ROOT/'base'/name)
shutil.copytree(SOURCE/'data',ROOT/'base/data',dirs_exist_ok=True)
refs=['baseline']+[f+'_real' for f in selected]
variants=[next(v for v in source_plan['variants'] if v['id']==vid) for vid in refs]
for i,pair in enumerate(reg['pairs']):
 variants.append({'id':f'pair{i:02d}_RR','pair':pair,'arm':'RR','permutation_seed':None,'background':'college_consensus'})
 for arm in ['RP','PR','PP']:
  for seed in reg['permutation_seeds']:variants.append({'id':f'pair{i:02d}_{arm}_{seed}','pair':pair,'arm':arm,'permutation_seed':seed,'background':'college_consensus'})
assert len(variants)*3==reg['task_count']==318
plan={'study':'R8x pair-complement screen','diagnostic_only':True,'no_confirmation_or_test_scoring':True,'registration':reg,
      'folds':source_plan['folds'],'seeds':reg['seeds'],'permutation_seeds':reg['permutation_seeds'],'variants':variants,
      'reference_ids':refs,'selected_features':selected,'pairs':reg['pairs'],'pair_slots':['slot_041','slot_042'],
      'model_constructor':source_plan['model_constructor'],'ordering_policy':source_plan['ordering_policy'],
      'source_filter':source_plan['source_filter'],'execution':{'task_count':318,'workers':4,'runtime_seconds':7200,'memory':'140G','cpu_quota':'2200%','snapshot_seconds':3,'summary_seconds':20},
      'controls':{'conditional_stream':'Unchanged W single-field stream: fifty:feature with role/cohort/own mask and permutation seed.','joint_stream':'fifty:pair_joint:<alphabeticA>:<alphabeticB>, whole row vectors within cohort/role/joint mask.',
      'preserved':'Every per-player field mask and cohort marginal; PP also preserves the pair joint distribution within mask/cohort.',
      'limitations':'RP/PR break cross-feature associations; PP uses a joint vector shuffle, so this is not a factorial independent-shuffle randomization test. Fixed-shape usability diagnostics after exploratory feature screening, not statistical significance.'}}
(ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
records=[r for r in state['candidates'] if r['config']['id']in refs];assert len(records)==18
reference={'state_sha256':reg['source_state_sha256'],'matched_summary':state['matched_summary'],'records':records}
(ROOT/'w_reference.json').write_text(json.dumps(reference,indent=2)+'\n')
shutil.copyfile(ROOT.parent/'r8queuebench/queue_runtime.py',ROOT/'queue_runtime.py')
manifest={'source':'Frozen unchanged W backbone/data package','source_state_sha256':reg['source_state_sha256'],'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'base').rglob('*')) if p.is_file() and '__pycache__'not in p.parts},'verified_scheduler_sha256':sha(ROOT/'queue_runtime.py')}
(ROOT/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'tasks':318,'reference_tasks':len(records),'pairs':len(reg['pairs']),'source_files':len(manifest['files']),'scheduler_workers':4}))
