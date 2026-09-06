from pathlib import Path
import json,hashlib,shutil,itertools
R=Path(__file__).resolve().parent;X=R.parent/'r8x';W=R.parent/'r8w'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((W/'results/state.json').read_text());xp=json.loads((X/'plan.json').read_text());wp=json.loads((W/'plan.json').read_text())
selected=sorted(r['id'] for r in s['matched_summary']['statistics'] if r['paired_mean_gain']>0 and r['real_minus_baseline_context_only']>0);assert len(selected)==19
exclude={tuple(p) for p in xp['pairs']};pairs=[list(p) for p in itertools.combinations(selected,2) if p not in exclude];assert len(pairs)==161
refs=['baseline']+[f+'_real' for f in selected]+['pair06_RR'];variants=[next(v for v in (xp['variants'] if vid=='pair06_RR' else wp['variants']) if v['id']==vid) for vid in refs]
for i,pair in enumerate(pairs):
 for arm in ['RR','RP','PR','PP']:
  for seed in ([None] if arm=='RR' else xp['permutation_seeds']):variants.append({'id':f'zpair{i:03d}_{arm}'+(''if seed is None else f'_{seed}'),'pair':pair,'arm':arm,'permutation_seed':seed,'background':'college_consensus'})
p={**xp,'study':'R8z broader exploratory complement screen','selected_features':selected,'pairs':pairs,'reference_ids':refs,'variants':variants,'pair_prefix':'zpair','pair_digits':3}
p['registration']={'source':'R8w only; no R8y feedback','source_state_sha256':sha(W/'results/state.json'),'selection_rule':'All W fields with positive real-minus-control AND positive real-minus-baseline means','selected_features':selected,'pairs':pairs,'excluded_completed_X_pairs':xp['pairs'],'no_promotion_or_test':True};p['execution']={**xp['execution'],'task_count':len(variants)*3};assert p['execution']['task_count']==4893
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
for n in ['worker.py','queue_runtime.py','research.py','run_sandbox.sh']:shutil.copyfile(X/n,R/n)
shutil.copytree(X/'base',R/'base',dirs_exist_ok=True)
records=[e for e in s['candidates'] if e['config']['id']in refs];records +=[json.loads((X/'results/tasks'/f'pair06_RR_seed{seed}.json').read_text()) for seed in p['seeds']];assert len(records)==63
(R/'w_reference.json').write_text(json.dumps({'state_sha256':sha(W/'results/state.json'),'records':records},indent=2)+'\n')
(R/'source_manifest.json').write_text(json.dumps({'files':{str(f.relative_to(R)):sha(f) for f in (R/'base').rglob('*') if f.is_file() and '__pycache__'not in f.parts},'verified_scheduler_sha256':sha(R/'queue_runtime.py')},indent=2)+'\n')
print({'selected':19,'new_pairs':161,'reference_fits':63,'total_fits':4893})
