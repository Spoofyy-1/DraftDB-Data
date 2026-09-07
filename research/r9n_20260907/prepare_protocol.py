"""Outcome-free declarative TabICL profile/view/weight registration."""
from pathlib import Path
import copy,hashlib,json
R=Path(__file__).resolve().parent;M=R.parent/'r9m';mp=json.loads((M/'protocol.json').read_text());G='f50_game_team'
profiles=[]
for norm,threshold,sizes in [('none',o,[16,32,64,128,256])for o in [.5,1.,2.,4.]]+[('power',2.,[64,128,256])]:
 for n in sizes:
  pid=f"{norm}_o{str(threshold).replace('.','p')}_n{n}";profiles.append({'id':pid,'norm_methods':norm,'outlier_threshold':threshold,'n_estimators':n})
base=next(p['id']for p in profiles if p['norm_methods']=='none'and p['outlier_threshold']==2 and p['n_estimators']==32)
recipes=[];seen={};aliases=0
for profile in profiles:
 for rp in ['base44',G]:
  for cp in ['base44',G]:
   for recipe in mp['architectures']:
    members=[]
    for m in recipe['members']:
     members.append({**m,'panel_id':G if m['family']=='tabicl'else cp if m['family']=='catboost'else rp,'profile_id':profile['id']if m['family']=='tabicl'else None})
    key=json.dumps(members,sort_keys=True,separators=(',',':'));alias={'profile_id':profile['id'],'R_panel':rp,'C_panel':cp,'same_panel_recipe':recipe['id']};aliases+=1
    if key in seen:recipes[seen[key]]['design_aliases'].append(alias)
    else:seen[key]=len(recipes);recipes.append({'id':f'profile_stack_{len(recipes):04d}','kind':'fixed_rank_weights','members':members,'weight_total':12,'design_aliases':[alias]})
assert len(profiles)==23 and len(recipes)==1723 and aliases==3496
p={'study':'R9N TabICL profiles on frozen127-column panel','status':'CPU registration awaiting source/preprocessing proof and root launch approval','outer_years':[2012,2013,2014],'seeds':[0,101,202],'policy_id':mp['policy_id'],'panel_id':G,'panels':[next(x for x in mp['panels']if x['id']==G)],'source_panels':[next(x for x in mp['panels']if x['id']==k)for k in ['base44',G]],'tabicl_base':mp['tabicl'],'ridge':mp['ridge'],'catboost':mp['catboost'],'profiles':profiles,'baseline_profile_id':base,'same_panel_architectures':mp['architectures'],'stack_recipes':recipes,'aggregation_modes':[0,101,202,'fixed_three_seed_family_rank_average'],'labels':mp['labels'],'M_protocol_sha256':hashlib.sha256((M/'protocol.json').read_bytes()).hexdigest(),'M_frozen_sha256':hashlib.sha256((M/'frozen.json').read_bytes()).hexdigest(),'unchanged_source_files':{f:hashlib.sha256((M/f).read_bytes()).hexdigest()for f in ['stack_core.py','runtime_support.json']},'computation':{'requested_profiles':23,'baseline_profiles_reused':1,'requested_new_profiles':22,'new_jobs_before_cpu_exclusions_or_exact_dedupe':66,'new_TabICL_fits_before_cpu_exclusions_or_exact_dedupe':198,'fits_per_new_job':3,'workers':4,'reused_original_member_jobs':6,'Ridge_or_CatBoost_new_fits':0},'prefit_admission':{'profile_settings':'Reject nonfinite or unsupported settings; no replacement or silent correction.','prepared_payload':'Training-only encoder, target standardizer, normalizer, clipping and permutation preparation; query values only transformed, no query outcomes. Reject a profile for every fold if any fold/seed payload is nonfinite or preparation fails; save exact reasons.','dedupe':'Only exact complete prepared payload/ensemble/row/column/target/constructor equivalence across all3folds/all3seeds. Preserve original requested counts and aliases. Never dedupe by effective member count alone or model scores.','baseline_failure':'Fail closed rather than remove the frozen control.'},'reference_gate':{'source_records':'Six immutable M base44/G member records, including original M->L base44 lineage, preserved without mutation; all input/label/order/runtime/settings/source-completion hashes must pass before fits.','model_refits':0,'exact_saved_prediction_recipes':[{'kind':'M_cross_panel','id':'cross_0771'},{'kind':'M_same_panel','panel_id':G,'id':'stack_013'}],'both_metrics_required':True,'before_candidate_fits':True},'selection':'Full-query mean ofall3folds/all3seeds is primary; observed mask secondary. Fixed-three-seed family rank average reported separately. Search scores are development diagnostics, not an unbiased holdout or goal claim.','limitations':mp['limitations']+['The127-column panel was selected from reused development results; this settings sweep is further development search.','No2019+ inputs/outcomes or2015+ confirmation scores; no automatic promotion.']}
(R/'protocol.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
for f in ['stack_core.py','runtime_support.json']:(R/f).write_bytes((M/f).read_bytes())
print(json.dumps({'profiles':23,'requested_jobs':66,'requested_fits':198,'declared_view_weight_designs':aliases,'distinct_recipes':1723,'baseline':base,'protocol_sha256':hashlib.sha256((R/'protocol.json').read_bytes()).hexdigest()}))
