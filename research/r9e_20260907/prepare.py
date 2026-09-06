from pathlib import Path
import json,hashlib,shutil,itertools
R=Path(__file__).resolve().parent;S=R.parent/'r9d';D=R/'d_reference';D.mkdir(exist_ok=True)
for name in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','references.json']:shutil.copyfile(S/name,D/name)
shutil.copytree(S/'b_reference',D/'b_reference',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
(D/'results').mkdir(exist_ok=True);shutil.copyfile(S/'results/capacity_check.json',D/'results/capacity_check.json');shutil.copyfile(S/'queue_runtime.py',R/'queue_runtime.py')
dp=json.loads((S/'plan.json').read_text());norms=['none','power'];thresholds=[.5,.75,1,1.25,1.5,1.75,2,2.25,2.5];sizes=[16,32,64];transforms=['identity','ndtr','signed_log1p','asinh','tanh_half','tanh','clip1_5','clip2']
grid=[]
for norm,t,n,transform in itertools.product(norms,thresholds,sizes,transforms):
 vid=f'{norm}_o{t:g}_n{n}'+('' if transform=='identity' else '_'+transform)
 vid=vid.replace('.','p')
 if (norm,t,n,transform)==('none',2,32,'identity'):vid='drop5_001'
 grid.append({'id':vid,'norm_methods':norm,'outlier_threshold':t,'n_estimators':n,'target_transform':transform})
refs=['drop5_001','none_o2_n16','none_o2_n64','power_o2_n16','power_o2_n32','power_o2_n64'];grid.sort(key=lambda s:(s['id']not in refs,refs.index(s['id']) if s['id']in refs else 99))
p={k:dp[k] for k in ['diagnostic_only','no_confirmation_or_test_scoring','folds','seeds','model_constructor','ordering_policy','baseline_config','seed_ensemble']}
p.update(study='R9e frozen training-target distribution and clipping diagnostic',reference_id='drop5_001',reference_ids=refs,normalizations=norms,outlier_thresholds=thresholds,requested_estimator_counts=sizes,target_transforms=transforms,requested_grid=grid,settings_by_id={s['id']:s for s in grid},variants=[{'id':s['id'],'kind':'target_settings',**{k:v for k,v in s.items() if k!='id'}} for s in grid],execution={**dp['execution'],'task_count':1296},protocol='Fixed B44 input matrices and column order prepared before any training-target transform. Eight deterministic transformations use only frozen training yy; original WAR truth, sample universe, calendar, missing-label convention and evaluation unchanged. No query truth used in transformations or CPU-effective dedupe. Full requested grid and proven effective aliases frozen before fits.',reference_gate='18 identity/outlier2 reference fits (both norms, all3sizes, all3seeds) must exactly replay D raw/canonical predictions, scores and full audits modulo explicit target-transform metadata and registered configuration identity.',target_formulas={'identity':'y','ndtr':'scipy.special.ndtr(y)','signed_log1p':'sign(y)*log1p(abs(y))','asinh':'arcsinh(y)','tanh_half':'tanh(0.5*y)','tanh':'tanh(y)','clip1_5':'clip(y,-1.5,1.5)','clip2':'clip(y,-2,2)'},limitations='Reused pre2019 development diagnostic; current missing-label convention and retrospective source limitations remain. No source recertification, significance claim, model promotion or heldout access.')
assert len(grid)==432 and len({s['id']for s in grid})==432
(R/'plan.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest()for f in D.rglob('*') if f.is_file()};files['d_references.json']=hashlib.sha256((R/'d_references.json').read_bytes()).hexdigest()
(R/'source_manifest.json').write_text(json.dumps({'files':files,'verified_scheduler_sha256':hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()},indent=2)+'\n')
print('432 requested configurations,1296 fits;18 D reference gates.')
