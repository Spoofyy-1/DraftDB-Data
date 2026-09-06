"""Freeze the registered baseline rule and approved35-column diagnostic study."""
from pathlib import Path
import hashlib,json,shutil,csv
R=Path(__file__).resolve().parent;A=R.parent/'r9a';B=R.parent/'r9b';D=R/'b_reference';D.mkdir(exist_ok=True)
for n in ['worker.py','plan.json','source_manifest.json','queue_runtime.py','references.json']:shutil.copyfile(B/n,D/n)
shutil.copytree(B/'a_reference',D/'a_reference',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(B/'queue_runtime.py',R/'queue_runtime.py')
choices=[];source_pins={}
for name,source in [('r9a',A),('r9b',B)]:
 raw=(source/'results/matched_summary.json').read_bytes();summary=json.loads(raw);proof=json.loads((source/'results/run_verification.json').read_text())
 assert proof['passed'] and hashlib.sha256(raw).hexdigest()==proof['summary']['sha256']
 source_pins[name]={'summary_sha256':hashlib.sha256(raw).hexdigest(),'verification_sha256':hashlib.sha256((source/'results/run_verification.json').read_bytes()).hexdigest()}
 for item in summary['ablations']:
  if all(v>0 for key in ['fold_deltas','seed_deltas'] for v in item[key].values()):choices.append({'source':name,**item})
# Deterministic lexical source/id tie-break affects only exactly tied means.
selected=sorted(choices,key=lambda r:(-r['real_mean'],r['source'],r['id']))[0] if choices else {'source':'r9a','id':'pair06_RR','columns':[]}
source=R.parent/selected['source'];source_plan=json.loads((source/'plan.json').read_text());config=next(v for v in source_plan['variants'] if v['id']==selected['id'])
bp=json.loads((B/'plan.json').read_text());header=next(csv.reader((R/'data/candidate_inputs.csv').open()));features=header[2:];assert header[:2]==['pid','draft_year'] and len(features)==35
family={'game':[c for c in features if c.startswith('cgd_')],'team':[c for c in features if c.startswith('tctx_')],'all':features};assert list(map(len,family.values()))==[15,20,35]
overlap=json.loads((R/'data/source_overlap.json').read_text());representations=[r['candidate'] for r in overlap['algebraic_or_direct_comparisons'] if r['equal_within_1e_minus12']==r['paired_observed_rows']];assert len(representations)==8
p={key:bp[key] for key in ['diagnostic_only','no_confirmation_or_test_scoring','folds','seeds','permutation_seeds','model_constructor','ordering_policy']}
p.update(study='R9c approved college game/team diagnostic',baseline={'source':selected['source'],'id':selected['id'],'config':config,'removed_columns':selected['columns'],'selection_result':selected,'rule':'Highest development mean across completed A and B deletions with strictly positive differences versus full X in every fold mean and every model seed mean; otherwise full X. Exact ties use source then id lexical order.','source_hashes':source_pins},reference_id=config['id'],features=features,families=family,algebraic_representation_features=representations,
source_admission=json.loads((R/'diagnostic_admission.json').read_text()),source_schema=header,source_rows=1458,study_rows=1428,
slot_policy='All single features use identical slot_043. Each family appends slots from slot_043 onward in frozen eligible source order; real/control columns, width, base values and missing masks match within fold.',eligibility={'minimum_observed_training_rows':5,'minimum_unique_training_values':2,'validation_used_for_selection':False},
controls={'single':'Same-role/cohort/own-mask value shuffles, three prespecified permutation seeds. All single real/control arms share one slot.',
'family':'Whole selected family vectors shuffled within role/cohort/exact joint missingness pattern; preserve masks, joint vector distribution and within-family algebra/covariance. May break dependence with the baseline. Sparse strata can be immovable.',
'interpretation':'Report real-minus-shuffled paired by model seed/fold and actual real-minus-baseline separately. Added width can change behavior without information; neither width changes nor three permutation seeds establish significance. Eight GP/shooting fields are alternative representations of existing observations, including any removed baseline fields. No source certification, automatic promotion, test or confirmation.'},reference_gate='Three selected-baseline full raw/canonical predictions, scores and complete input audits must match before interpretation.',groups=[],variants=[config],execution={**bp['execution'],'task_count':459})
for i,c in enumerate(features):p['groups'].append({'id':f'single_{i:03d}','kind':'single','features':[c],'algebraic_representation':c in representations})
for name,cols in family.items():p['groups'].append({'id':'family_'+name,'kind':'family','features':cols,'algebraic_representation_features':[c for c in cols if c in representations]})
for group in p['groups']:
 for arm,seed in [('real',None)]+[('permuted',s) for s in p['permutation_seeds']]:
  p['variants'].append({'id':group['id']+('_real' if arm=='real' else f'_perm_{seed}'),'group':group['id'],'kind':group['kind'],'features':group['features'],'arm':'RR' if arm=='real' else 'PP','permutation_seed':seed})
assert len(p['variants'])*3==459
(R/'plan.json').write_text(json.dumps(p,indent=2)+'\n')
files={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for folder in [D,R/'data'] for f in folder.rglob('*') if f.is_file()}
(R/'source_manifest.json').write_text(json.dumps({'files':files,'verified_scheduler_sha256':hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()},indent=2)+'\n')
if (source/'results/tasks').is_dir():
 refs=[json.loads((source/'results/tasks'/f"{config['id']}_seed{s}.json").read_text()) for s in p['seeds']]
 (R/'references.json').write_text(json.dumps({'records':refs,'source':selected['source'],'source_completion_sha256':hashlib.sha256((source/'results/completion.json').read_bytes()).hexdigest()},indent=2)+'\n')
print({'baseline_source':selected['source'],'baseline_id':selected['id'],'removed':selected['columns'],'eligible_deletion_candidates':len(choices),'tasks':459,'representations':representations})
