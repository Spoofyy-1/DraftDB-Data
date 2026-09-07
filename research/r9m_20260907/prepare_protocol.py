"""Declare R9M solely from frozen L schema/model recipes and source panel inventory."""
import copy,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent;L=R.parent/'r9l';d=copy.deepcopy(json.loads((L/'protocol.json').read_text()));inventory=json.loads((R.parent/'stack_broadening/panel_manifest.json').read_text())
assert hashlib.sha256((L/'protocol.json').read_bytes()).hexdigest()=='b5a08f448582931158da52dbf37136e47d5b555f9596866210013b4a5aa2a282'
families={name:[c for c in inventory['added_columns']if c.startswith(prefix)]for name,prefix in [('f50','f50_'),('combine','vcmb_'),('team','tctx_'),('game','cgd_')]}
choices=[('base44',[]),('add_f50',['f50']),('f50_combine',['f50','combine']),('f50_team',['f50','team']),('f50_game',['f50','game']),('f50_combine_team',['f50','combine','team']),('f50_game_team',['f50','game','team']),('f50_combine_game_team',['f50','combine','game','team'])]
panels=[]
for pid,fs in choices:
 columns=d['original_H44_columns']+sorted(c for f in fs for c in families[f]);panels.append({'id':pid,'families_added':fs,'columns':columns,'width':len(columns)})
for panel in panels[:2]:assert panel==next(p for p in d['panels']if p['id']==panel['id'])
cross=[];lookup={};raw_designs=0
for candidate,_ in choices[2:]:
 for tpanel in ['add_f50',candidate]:
  for rpanel in ['base44',candidate]:
   for cpanel in ['base44',candidate]:
    for r in d['architectures']:
     raw_designs+=1;members=[]
     for m in r['members']:
      panel=tpanel if m['family']=='tabicl'else cpanel if m['family']=='catboost'else rpanel
      members.append({**m,'panel_id':panel})
     key=json.dumps(members,sort_keys=True,separators=(',',':'))
     provenance={'candidate':candidate,'T_panel':tpanel,'R_panel':rpanel,'C_panel':cpanel,'same_panel_recipe':r['id']}
     if key in lookup:cross[lookup[key]]['design_aliases'].append(provenance)
     else:
      lookup[key]=len(cross);cross.append({'id':f'cross_{len(cross):04d}','kind':'fixed_rank_weights','members':members,'weight_total':12,'design_aliases':[provenance]})
d.update(study='R9M F50 complementary panels and fixed cross-panel family stacks',status='Frozen proposal awaiting parent CPU review and launch approval',panels=panels)
d['L_protocol_sha256']=hashlib.sha256((L/'protocol.json').read_bytes()).hexdigest();d['unchanged_L_model_files']={f:hashlib.sha256((L/f).read_bytes()).hexdigest()for f in ['worker.py','model_backend.py','stack_core.py','runtime_support.json']}
d['computation']={'task_records':24,'tasks':24,'new_model_jobs':18,'reused_control_records':6,'fits_per_new_task':9,'new_model_fits':162,'reused_original_model_fits':54,'Ridge_fits_per_new_task':3,'TabICL_fits_per_new_task':3,'CatBoost_fits_per_new_task':3,'feature_selector_fits':0}
d['L_frozen_sha256']=hashlib.sha256((L/'frozen.json').read_bytes()).hexdigest()
d['reference_gate']={'control_panels':['base44','add_f50'],'reused_immutable_control_jobs':6,'remaining_new_panel_jobs':18,'all_member_families':['tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost'],'all_seeds':[0,101,202],'exact_raw_and_canonical_member_vectors':True,'exact_source_input_target_cohort_order_runtime_and_parameter_hashes':True,'before_new_panel_fits':True,'before_interpretation':True,'control_model_refits':0,'source_record_mutation':False,'reuse_provenance':'Root separately pins and verifies six original L raw records, completed-log record hashes and task-map, complete/source freeze plus all per-job input/label/query/order/model/runtime hashes; original records remain unchanged. New M metadata is stored beside them, not inside source records.','mismatch_policy':'Fail closed; no tolerance and no score-dependent retry.'}
d['cross_panel_stacks']={'candidate_panels':[x[0]for x in choices[2:]],'T_views':['add_f50','matching_candidate'],'R_and_C_views':['base44','matching_candidate'],'pre_dedup_designs':raw_designs,'distinct_recipes':len(cross),'recipes':cross,'deduplication':'Exact positive-weight family/panel/weight tuples before fitting; zero-weight absent member views do not create new recipes. No prediction/outcome-based deduplication.','aggregation_modes':[0,101,202,'fixed_three_seed_family_rank_average'],'no_additional_fits':True,'learned_weights':False,'tie_policy':'Validate equality in groups defined by the union of actual participating panel predictor vectors; never re-average already tied final scores.','reporting':'Same-seed nine fold/seed scores primary, fixed-three-seed family rank averaging separately; standalone endpoints distinct from multi-family stacks. Full-query metric primary and frozen observed mask secondary; no model promotion.'}
d['selection']='Pre2019 development-only full-query mean over all three folds and three seeds. Compare same recipes against base44 and add_f50; report every fold/seed mean. Cross-panel grid is prespecified search, not an unbiased validation estimate or learned stack.'
d['limitations']+=['Cross-panel view and weight search reuse the same development folds; final best recipe is a search diagnostic, not a certified goal result.']
(R/'protocol.json').write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
for f in ['worker.py','model_backend.py','stack_core.py','runtime_support.json','test_worker.py']:(R/f).write_bytes((L/f).read_bytes())
print(json.dumps({'panels':[(p['id'],p['width'])for p in panels],'task_records':24,'new_jobs':18,'new_fits':162,'reused_control_records':6,'same_panel_recipes':len(d['architectures']),'cross_designs_before_dedup':raw_designs,'cross_recipes':len(cross),'protocol_sha256':hashlib.sha256((R/'protocol.json').read_bytes()).hexdigest()}))
