"""Register the bounded coherent five-input ablation follow-up from completed A."""
from pathlib import Path
import json,hashlib,shutil,itertools
R=Path(__file__).resolve().parent;S=R.parent/'r9a';D=R/'a_reference';D.mkdir(exist_ok=True)
for n in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','references.json']:shutil.copyfile(S/n,D/n)
shutil.copytree(S/'x_reference',D/'x_reference',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(S/'queue_runtime.py',R/'queue_runtime.py')
ap=json.loads((S/'plan.json').read_text());summary_raw=(S/'results/matched_summary.json').read_bytes();summary=json.loads(summary_raw);proof=json.loads((S/'results/run_verification.json').read_text())
assert proof['passed'] and proof['records']==3810 and hashlib.sha256(summary_raw).hexdigest()==proof['summary']['sha256']
singles={r['columns'][0]:r for r in summary['ablations'] if len(r['columns'])==1};controls={r['column']:r for r in summary['permutation_controls']}
selected=[c for c in sorted(singles) if all(value>0 for result in [singles[c],controls[c]] for field in ['fold_deltas','seed_deltas'] for value in result[field].values())]
assert selected==['ctx_base_fta','ctx_base_ftm','ctx_base_ftr','ctx_base_mid_made','ctx_base_minutes_share']
subsets=[list(s) for size in [2,3,4,5] for s in itertools.combinations(selected,size)];deletions=[s for s in subsets if len(s)>=3]
reference_configs=[v for v in ap['variants'] if v['id']==ap['reference_id'] or (v.get('kind')=='delete' and set(v['columns'])<=set(selected))]
assert len(reference_configs)==16 and len(subsets)==26 and len(deletions)==16
p={key:ap[key] for key in ['diagnostic_only','no_confirmation_or_test_scoring','reference_id','folds','seeds','permutation_seeds','model_constructor','ordering_policy','columns','column_meanings','ordered_columns_by_fold']}
p.update(study='R9b bounded coherent five-input removals',reference_ids=[v['id'] for v in reference_configs],selected_columns=selected,subsets=subsets,variants=list(reference_configs),execution={**ap['execution'],'task_count':330},
selection={'source':'Completed R9a pre2019 development diagnostics only','rule':'Single deletion-minus-full AND matched permutation-minus-full strictly positive in every development fold mean and every model seed mean; take every qualifying column.','source_summary_sha256':hashlib.sha256(summary_raw).hexdigest(),'source_verification_sha256':hashlib.sha256((S/'results/run_verification.json').read_bytes()).hexdigest(),'selected_columns':selected,'no_further_exhaustive_pruning_without_new_data_or_confirmation':True},
controls={'deletion':'All16 subsets of the five registered columns of sizes3..5 are removed only after the unchanged47-column full X design is prepared; remaining order/values fixed. Width42..44 entails model dimension effects, not pure information deletion.',
'joint_permutation':'All26 subsets of sizes2..5 are shuffled as complete row vectors within role, draft cohort and exact per-row joint missingness pattern. Keeps width47, every player missing mask, cohort vector distribution and within-subset covariance/algebra. May break dependence with other predictors; sparse masks can be immovable. Three fixed permutation seeds with shared stream fifty:joint_input_ablation:<sorted columns>. Exploratory paired diagnostics, no significance claim.',
'comparison':'Report each deletion and joint-shuffle difference versus full model by fold and model seed; preserve controls individually and across three permutation seeds. No automatic promotion.'},reference_gate='All48 A full/single/double tasks must exactly replay complete input audits, raw/canonical predictions and scores before interpretation.')
for i,cols in enumerate(deletions):p['variants'].append({'id':f'drop5_{i:03d}','kind':'delete','columns':cols,'arm':'RR'})
for i,cols in enumerate(subsets):
 for seed in p['permutation_seeds']:p['variants'].append({'id':f'joint_{i:03d}_{seed}','kind':'permutation','columns':cols,'permutation_seed':seed,'arm':'PP'})
assert len(p['variants'])*3==330
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in D.rglob('*') if f.is_file()}
(R/'source_manifest.json').write_text(json.dumps({'files':files,'verified_scheduler_sha256':hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()},indent=2)+'\n')
# On the server only: materialize the48 existing raw references as a single frozen artifact.
if (S/'results/tasks').is_dir():
 refs=[json.loads((S/'results/tasks'/f"{v['id']}_seed{seed}.json").read_text()) for v in reference_configs for seed in p['seeds']]
 (R/'references.json').write_text(json.dumps({'records':refs,'source_completion_sha256':hashlib.sha256((S/'results/completion.json').read_bytes()).hexdigest()},indent=2)+'\n')
print({'selected_columns':selected,'references':48,'new_deletions':16,'joint_subsets':26,'tasks':330})
