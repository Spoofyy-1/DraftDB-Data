from pathlib import Path
import json,hashlib,shutil,itertools
R=Path(__file__).resolve().parent;S=R.parent/'r9b';D=R/'b_reference';D.mkdir(exist_ok=True)
for n in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','references.json']:shutil.copyfile(S/n,D/n)
shutil.copytree(S/'a_reference',D/'a_reference',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(S/'queue_runtime.py',R/'queue_runtime.py')
# C's frozen reference artifact contains the original B baseline records, not C predictions or inputs.
ref=json.loads((R.parent/'r9c/references.json').read_text());assert ref['source']=='r9b' and len(ref['records'])==3 and all(e['config']['id']=='drop5_001' for e in ref['records']);(R/'references.json').write_text(json.dumps(ref,indent=2)+'\n')
bp=json.loads((S/'plan.json').read_text());base=ref['records'][0]['config'];norms=['none','power','quantile','quantile_rtdl','robust'];thresholds=[2,3,5,'disabled'];sizes=[16,32,64]
settings=[]
for norm,t,n in itertools.product(norms,thresholds,sizes):
 vid=f'{norm}_o{t}_n{n}'
 if (norm,t,n)==('none',2,32):vid=base['id']
 settings.append({'id':vid,'norm_methods':norm,'outlier_threshold':t,'n_estimators':n})
settings.sort(key=lambda s:s['id']!=base['id'])
p={k:bp[k] for k in ['diagnostic_only','no_confirmation_or_test_scoring','folds','seeds','model_constructor','ordering_policy']}
p.update(study='R9d TabICL settings diagnostic',reference_id=base['id'],baseline_config=base,normalizations=norms,outlier_thresholds=thresholds,requested_estimator_counts=sizes,requested_grid=settings,settings_by_id={s['id']:s for s in settings},variants=[base if s['id']==base['id'] else {'id':s['id'],'kind':'model_settings',**{k:v for k,v in s.items() if k!='id'}} for s in settings],execution={**bp['execution'],'task_count':180},
protocol='Only named normalization, outlier threshold and estimator count vary on unchanged B drop5_00144-column inputs. CPU-only constructor/ensemble/permutation/view equality across all folds and seeds may deduplicate configurations before fits; no scores used. No test/confirmation or new sources.',
reference_gate='Three none/outlier2/n32 baseline runs must exactly reproduce original B raw/canonical predictions, scores and complete audits before interpretation.',
seed_ensemble={'seeds':bp['seeds'],'weights':[1/3]*3,'method':'For each configuration/fold/PID, arithmetic mean of all three saved canonical predictions using math.fsum divided by3, then development Spearman. Never choose or reweight seeds. Retain individual model runs and separate averaged predictions/score artifact.','selection':'Diagnostic only; no automatic promotion or significance claim.'})
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in D.rglob('*') if f.is_file()}
(R/'source_manifest.json').write_text(json.dumps({'files':files,'verified_scheduler_sha256':hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()},indent=2)+'\n')
print('Registered60 requested configurations,180 seed fits before CPU deduplication.')
