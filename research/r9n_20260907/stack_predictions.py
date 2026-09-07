"""Outcome-free fixed-profile/view/weight arithmetic; no model fitting or learned weights."""
import numpy as np
import stack_core as C
G='f50_game_team'

def source_member(sources,year,family,panel,mode):
 r=sources[(panel,year)];seeds=r['seed_results']
 if isinstance(mode,int):entry=next(s for s in seeds if s['seed']==mode)['members'][family];value=np.asarray(entry['canonical_predictions'])
 elif family.startswith('ridge_'):value=np.asarray(seeds[0]['members'][family]['canonical_predictions']);assert all(np.array_equal(value,s['members'][family]['canonical_predictions'])for s in seeds)
 else:value=np.sum([C.doubled_ranks(s['members'][family]['canonical_predictions'])for s in seeds],axis=0,dtype=np.int64)/(6*len(r['query_pids']))
 keys=seeds[0]['members'][family]['tie_audit']['input_vector_hashes'];assert all(s['members'][family]['tie_audit']['input_vector_hashes']==keys for s in seeds)
 return value,keys

def validate_job(r,task,manifest,protocol):
 assert r['runtime']['support_sha256']==protocol['unchanged_source_files']['runtime_support.json']and r['namespace_proof']['passed']is True
 assert r['task_id']==task['id']and r['profile_id']==task['profile_id']and r['outer_year']==task['outer_year']and r['panel_id']==G and r['policy_id']==protocol['policy_id']
 assert r['columns']==protocol['panels'][0]['columns']and r['label_audit']==manifest['label_audit']and r['input_manifest_sha256']==task['input_manifest_sha256']and r['protocol_sha256']==manifest['protocol_sha256']and r['fit_counts']=={'tabicl':3}and not r['query_outcome_labels_accessed']
 assert [m['seed']for m in r['members']]==protocol['seeds']
 for m in r['members']:
  expected=manifest['preprocessing_designs'][str(m['seed'])];a=m['model_audit'];assert a['parameters']==expected['parameters']and a['effective_constructor']==expected['effective_constructor']and a['generator']==expected['generator']and a['preprocessing_design_hash']==C.digest(expected)
  assert a['training_matrix_hash']==r['training_matrix_hash']==expected['original_training_matrix_hash']and a['query_matrix_hash']==r['query_matrix_hash']==expected['original_query_matrix_hash']and a['training_target_hash']==r['target_hash']==expected['original_target_hash']
  assert a['training_pid_hash']==C.digest(r['training_pids'])and a['input_columns']==r['columns']and a['actual_devices']and all(d.startswith('cuda')for d in a['actual_devices'])
  assert len(m['raw_predictions'])==len(m['canonical_predictions'])==len(r['query_pids'])and np.isfinite(m['raw_predictions']).all()and np.isfinite(m['canonical_predictions']).all()
  assert m['tie_audit']['raw_hash']==C.array_hash(m['raw_predictions'])and m['tie_audit']['canonical_hash']==C.array_hash(m['canonical_predictions'])

def assemble(sources,jobs,recipes,protocol):
 bykey={(r['profile_id'],r['outer_year']):r for r in jobs};assert len(bykey)==len(jobs);cache={};rows=[]
 ready={protocol['baseline_profile_id']}|{pid for pid,_ in bykey if all((pid,y)in bykey for y in protocol['outer_years'])}
 for r in jobs:
  base=sources[(G,r['outer_year'])];assert all(r[k]==base[k]for k in ['query_pids','training_pids','target_hash','label_audit','policy_id'])
 for recipe in recipes:
  if any(m['profile_id']is not None and m['profile_id']not in ready for m in recipe['members']):continue
  assert recipe['weight_total']==12 and sum(m['units']for m in recipe['members'])==12 and all(type(m['units'])is int and m['units']>0 for m in recipe['members'])
  for year in protocol['outer_years']:
   pids=sources[(G,year)]['query_pids'];n=len(pids)
   for mode in protocol['aggregation_modes']:
    total=np.zeros(n,dtype=np.int64);vectors=[]
    for m in recipe['members']:
     key=(m['profile_id'],m['family'],m['panel_id'],year,mode)
     if key not in cache:
      if m['family']!='tabicl'or m['profile_id']==protocol['baseline_profile_id']:value,keys=source_member(sources,year,m['family'],m['panel_id'],mode)
      else:
       job=bykey[(m['profile_id'],year)];members=job['members']
       if isinstance(mode,int):value=np.asarray(next(v for v in members if v['seed']==mode)['canonical_predictions'])
       else:value=np.sum([C.doubled_ranks(v['canonical_predictions'])for v in members],axis=0,dtype=np.int64)/(6*n)
       keys=members[0]['tie_audit']['input_vector_hashes'];assert all(v['tie_audit']['input_vector_hashes']==keys for v in members)
      assert len(value)==len(keys)==n and np.isfinite(value).all();cache[key]=(C.doubled_ranks(value),keys)
     rank,keys=cache[key];total+=rank*m['units'];vectors.append(keys)
    prediction=total/(24*n);seen={}
    for k,v in zip(zip(*vectors),prediction):
     if k in seen:assert seen[k]==v
     else:seen[k]=v
    rows.append({'architecture':recipe['id'],'year':year,'seed':mode,'query_pids':pids,'prediction':prediction.tolist(),'multi_family_stack':len({m['family'].split('_a')[0]for m in recipe['members']})>=2,'prediction_hash':C.array_hash(prediction),'union_input_vector_key_hash':C.digest([list(x)for x in zip(*vectors)])})
 return rows
