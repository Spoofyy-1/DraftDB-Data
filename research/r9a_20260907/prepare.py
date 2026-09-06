"""Register schema-only ablation of the unchanged X pair06 design."""
from pathlib import Path
import hashlib,json,shutil,itertools
R=Path(__file__).resolve().parent;S=R.parent/'r8x';D=R/'x_reference';D.mkdir(exist_ok=True)
for name in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','w_reference.json']:shutil.copyfile(S/name,D/name)
shutil.copytree(S/'base',D/'base',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(S/'queue_runtime.py',R/'queue_runtime.py')
xp=json.loads((S/'plan.json').read_text());full=next(v for v in xp['variants'] if v['id']=='pair06_RR')
refs=[json.loads((S/'results/tasks'/f'pair06_RR_seed{seed}.json').read_text()) for seed in xp['seeds']]
columns=sorted(refs[0]['rows'][0]['audit']['input_columns']);assert len(columns)==47 and len(set(columns))==47
assert all(sorted(row['audit']['input_columns'])==columns for ref in refs for row in ref['rows'])
meanings={c:c for c in columns}
for slot,source in zip(['slot_037','slot_038','slot_039','slot_040'],refs[0]['rows'][0]['audit']['families']['consensus']['train']['features']):meanings[slot]=source
for slot,source in zip(xp['pair_slots'],full['pair']):meanings[slot]=source
p={'study':'R9a existing-input ablation','diagnostic_only':True,'no_confirmation_or_test_scoring':True,'reference_id':'pair06_RR','folds':xp['folds'],'seeds':xp['seeds'],'permutation_seeds':xp['permutation_seeds'],'model_constructor':xp['model_constructor'],'ordering_policy':xp['ordering_policy'],'columns':columns,'column_meanings':meanings,'ordered_columns_by_fold':{str(r['season']):r['audit']['input_columns'] for r in refs[0]['rows']},'variants':[full],
'execution':{'task_count':3810,'workers':4,'runtime_seconds':7200,'memory':'140G','cpu_quota':'2200%'},
'selection':'All47 actual predictor names shared across the unchanged X pair06 development designs, determined by schema only. No Z/Y/heldout scores determine columns, pairs or settings.',
'controls':{'deletion':'Every single and double column removal occurs only after the entire unchanged X input design is prepared. Remaining columns keep their original fold-specific order; no feature selector is rerun. Width falls to46/45, so deletion differences also include model dimension/representation effects and do not isolate causal information.',
'permutation':'Each one column is independently permuted within role, draft cohort and its exact own missingness mask. Width47 and all other values/order stay fixed. Three prespecified permutation seeds; stream fifty:registered_input:<column>. Controls may break algebra/correlation with other fields and are exploratory usability diagnostics, not significance tests.',
'comparison':'Report deletion-minus-full and permutation-minus-full by seed/fold; full-minus-permutation as a separate fixed-width diagnostic. Do not pool permutation seeds as independent observations. No automatic promotion.'},
'reference_gate':'All three full-model tasks must exactly replay X raw/canonical predictions, scores and complete input audits before interpretation.'}
for i,c in enumerate(columns):p['variants'].append({'id':f'drop_{i:03d}','kind':'delete','columns':[c],'arm':'RR'})
for (i,a),(j,b) in itertools.combinations(enumerate(columns),2):p['variants'].append({'id':f'drop_{i:03d}_{j:03d}','kind':'delete','columns':[a,b],'arm':'RR'})
for i,c in enumerate(columns):
 for seed in p['permutation_seeds']:p['variants'].append({'id':f'perm_{i:03d}_{seed}','kind':'permutation','columns':[c],'permutation_seed':seed,'arm':'PP'})
assert len(p['variants'])*3==3810
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n');(R/'references.json').write_text(json.dumps({'records':refs,'source_completion_sha256':hashlib.sha256((S/'results/completion.json').read_bytes()).hexdigest()},indent=2)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in D.rglob('*') if f.is_file()}
(R/'source_manifest.json').write_text(json.dumps({'files':files,'verified_scheduler_sha256':hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()},indent=2)+'\n')
print('Registered47 single removals,1081 double removals,141 permutation variants and3 exact references;3810 fits.')
