"""Outcome-free postfit member/view blending. Root separately verifies sources and scores."""
import numpy as np
import stack_core as C
FAMILIES=['tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost']
def record_map(records,protocol):
 panels={p['id']:p for p in protocol['panels']};out={}
 assert len(records)==24
 for r in records:
  key=(r['panel_id'],r['outer_year']);assert key not in out and key[0]in panels and key[1]in protocol['outer_years']
  assert r['columns']==panels[key[0]]['columns']and r['policy_id']==protocol['policy_id']and r['query_outcome_labels_accessed']is False
  assert [s['seed']for s in r['seed_results']]==protocol['seeds']
  n=len(r['query_pids']);assert n>0 and len(set(r['query_pids']))==n
  for seed in r['seed_results']:
   assert list(seed['members'])==FAMILIES
   for family,m in seed['members'].items():
    pred=np.asarray(m['canonical_predictions'],dtype=float);raw=np.asarray(m['raw_predictions'],dtype=float)
    assert pred.shape==raw.shape==(n,)and np.isfinite(pred).all()and np.isfinite(raw).all()
    audit=m['tie_audit'];assert audit['canonical_hash']==C.array_hash(pred)and audit['raw_hash']==C.array_hash(raw)and len(audit['input_vector_hashes'])==n
    assert m['model_audit']['input_columns']==r['columns']and m['model_audit']['training_pid_hash']==C.digest(r['training_pids'])and m['model_audit']['training_target_hash']==r['target_hash']
  out[key]=r
 assert set(out)=={(pid,y)for pid in panels for y in protocol['outer_years']}
 for year in protocol['outer_years']:
  base=out[('base44',year)]
  for pid in panels:
   r=out[(pid,year)]
   assert all(r[k]==base[k]for k in ['query_pids','training_pids','policy_id','target_hash','label_audit'])
 return out

def member_value(record,family,mode):
 if isinstance(mode,int):seed=next(s for s in record['seed_results']if s['seed']==mode);return np.asarray(seed['members'][family]['canonical_predictions'],dtype=float)
 assert mode=='fixed_three_seed_family_rank_average'
 seeds=record['seed_results']
 if family.startswith('ridge_'):
  a=np.asarray(seeds[0]['members'][family]['canonical_predictions']);assert all(np.array_equal(a,s['members'][family]['canonical_predictions'])for s in seeds)
 else:a=np.sum([C.doubled_ranks(s['members'][family]['canonical_predictions'])for s in seeds],axis=0,dtype=np.int64)/(6*len(record['query_pids']))
 assert np.array_equal(a,record['fixed_three_seed_family_rank_average']['members'][family]);return a

def assemble(records,protocol,reuse_gate):
 """No outcome values/masks accepted; source gate is supplied by the independent root verifier."""
 assert reuse_gate['passed']is True and reuse_gate['reused_records']==6 and reuse_gate['new_control_fits']==0 and reuse_gate['source_records_unchanged']is True
 assert reuse_gate['L_frozen_sha256']==protocol['L_frozen_sha256']and reuse_gate['source_record_hash_manifest_sha256']and reuse_gate['source_completed_log_sha256']
 source=record_map(records,protocol);results=[];cache={};recipes=protocol['cross_panel_stacks']['recipes'];assert len(recipes)==protocol['cross_panel_stacks']['distinct_recipes']==950
 for year in protocol['outer_years']:
  pids=source[('base44',year)]['query_pids'];n=len(pids)
  for mode in protocol['cross_panel_stacks']['aggregation_modes']:
   for recipe in recipes:
    assert recipe['weight_total']==12 and sum(m['units']for m in recipe['members'])==12 and all(m['units']>0 for m in recipe['members'])
    numerator=np.zeros(n,dtype=np.int64);vector_keys=[]
    for m in recipe['members']:
     r=source[(m['panel_id'],year)];family=m['family'];key=(m['panel_id'],year,mode,family)
     if key not in cache:
      keys=r['seed_results'][0]['members'][family]['tie_audit']['input_vector_hashes'];assert all(s['members'][family]['tie_audit']['input_vector_hashes']==keys for s in r['seed_results']);cache[key]=(C.doubled_ranks(member_value(r,family,mode)),keys)
     ranked,keys=cache[key];numerator+=m['units']*ranked;vector_keys.append(keys)
    prediction=numerator/(24*n);groups={}
    for key,value in zip(zip(*vector_keys),prediction):
     if key in groups:assert groups[key]==value,'Cross-panel union-input duplicate tie mismatch'
     else:groups[key]=value
    families={m['family'].split('_a')[0]for m in recipe['members']}
    results.append({'architecture':recipe['id'],'year':year,'seed':mode,'query_pids':pids,'prediction':prediction.tolist(),'prediction_hash':C.array_hash(prediction),'multi_family_stack':len(families)>=2,'participating_views':sorted({m['panel_id']for m in recipe['members']}),'union_input_vector_key_hash':C.digest([list(x)for x in zip(*vector_keys)]),'fixed_weights':True,'query_outcome_labels_accessed':False})
 assert len(results)==950*3*4
 return {'reuse_gate':reuse_gate,'cross_panel_prediction_records':results,'recipe_count':950,'prediction_records':len(results),'additional_model_fits':0,'learned_weights':False}
