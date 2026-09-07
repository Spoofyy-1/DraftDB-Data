"""Root-only six-record M/L provenance and exact numeric-input reuse gate."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'code'));import stack_core as C

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def verify(root=ROOT):
 root=Path(root);plan=read(root/'plan.json');protocol=read(root/'code/protocol.json');src=root/'source_refs';assert sha(src/'manifest.json')==plan['reference_source_manifest_sha256'];m=read(src/'manifest.json');mf=read(src/'M_frozen.json')['files']
 assert sha(src/'M_frozen.json')==m['M_frozen_sha256']==protocol['M_frozen_sha256']and sha(src/'M_protocol.json')==m['M_protocol_sha256']==protocol['M_protocol_sha256']
 assert sha(src/'M_completed.jsonl')==m['M_completed_log_sha256']and sha(src/'M_completion.json')==m['M_completion_sha256']and sha(src/'M_L_lineage.json')==m['M_L_lineage_sha256']
 assert read(src/'M_completion.json')['status']=='completed'and read(src/'M_completion.json')['tasks']==24 and m['M_source_gate']['passed']and m['source_records_unchanged']
 assert m['M_runtime_sha256']==sha(root/'code/runtime_support.json')==protocol['unchanged_source_files']['runtime_support.json']
 for f,h in protocol['unchanged_source_files'].items():assert sha(root/'code'/f)==h
 mp=read(src/'M_protocol.json')
 for key in ['ridge','catboost','labels','policy_id','outer_years','seeds']:assert protocol[key]==mp[key]
 assert protocol['tabicl_base']==mp['tabicl'];raw=(src/'M_completed.jsonl').read_bytes();assert raw.endswith(b'\n');lines=[json.loads(x)for x in raw.splitlines()];log={x['task_id']:x for x in lines};assert len(log)==len(lines)==24
 lineage=read(src/'M_L_lineage.json');records={};hashes={};checks=0
 for tid,info in m['records'].items():
  path=root/info['file'];assert sha(path)==info['sha256']==log[tid]['sha256']and info['M_completed_entry']==log[tid];r=read(path);folder=root/'source_inputs'/tid;im=read(folder/'manifest.json')
  assert sha(folder/'manifest.json')==info['M_input_manifest_sha256']==mf[f'inputs/{tid}/manifest.json']and im==info['M_input_manifest']
  expected_panel=next(p for p in protocol['source_panels']if p['id']==r['panel_id']);assert r['task_id']==tid and r['columns']==im['columns']==expected_panel['columns']and r['policy_id']==im['policy_id']==protocol['policy_id']and r['outer_year']==im['outer_year']
  if log[tid]['kind']=='reused_L_control':
   old=lineage['control_records'][tid];assert old['sha256']==info['sha256']and old['source_input_manifest_sha256']==r['input_manifest_sha256']and r['protocol_sha256']==lineage['L_protocol_sha256']
   assert {k:v for k,v in old['source_input_manifest'].items()if k!='protocol_sha256'}=={k:v for k,v in im.items()if k!='protocol_sha256'}
  else:assert log[tid]['kind']=='new_model_job'and r['protocol_sha256']==protocol['M_protocol_sha256']and r['input_manifest_sha256']==info['M_input_manifest_sha256']
  assert r['runtime']['support_sha256']==m['M_runtime_sha256']and r['label_audit']==im['label_audit']and not r['query_outcome_labels_accessed']
  for f,i in im['files'].items():assert sha(folder/f)==i['sha256']==mf[f'inputs/{tid}/{f}']
  with np.load(folder/'training.npz',allow_pickle=False)as t,np.load(folder/'inference.npz',allow_pickle=False)as q:
   a=im['label_audit'];assert t['pid'].tolist()==r['training_pids']and q['pid'].tolist()==r['query_pids']and not set(t['pid'])&set(q['pid'])and t['draft_year'].min()>=2008 and t['draft_year'].max()<r['outer_year']and np.all(t['prefix_length']==1)
   assert np.array_equal(C.gaussian_target(t['label_value'],t['draft_year']),t['y'])and C.array_hash(t['label_value'])==a['label_value_hash']and C.array_hash(t['y'])==a['target_hash']==r['target_hash']and C.digest(t['pid'].tolist())==a['training_pid_hash']
   assert a['max_actual_label_season']<=r['outer_year']-1 and a['all_labels_finite_observed']and not a['missing_training_labels_zero_filled']and C.array_hash(t['X'])==r['training_matrix_hash']and C.array_hash(q['X'])==r['query_matrix_hash']
   assert [s['seed']for s in r['seed_results']]==protocol['seeds']
   for s in r['seed_results']:
    assert set(s['members'])=={'tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost'}
    for family,member in s['members'].items():
     audit=member['model_audit'];kw={**protocol['tabicl_base'],'random_state':s['seed']}if family=='tabicl'else {**protocol['catboost']['parameters'],'random_seed':s['seed']}if family=='catboost'else {'alpha':int(family.removeprefix('ridge_a')),'solver':protocol['ridge']['solver']}
     assert audit['parameters']==kw and audit['input_columns']==r['columns']and audit['training_pid_hash']==a['training_pid_hash']and audit['training_matrix_hash']==r['training_matrix_hash']and audit['training_target_hash']==r['target_hash']and audit['query_matrix_hash']==r['query_matrix_hash']
     pred,ties=C.canonicalize(q['X'],member['raw_predictions'],r['query_pids']);assert np.array_equal(pred,member['canonical_predictions'])and ties==member['tie_audit'];checks+=1
  records[(r['panel_id'],r['outer_year'])]=r;hashes[tid]=info['sha256']
 assert len(records)==6 and checks==90
 for y in protocol['outer_years']:
  a=records[('base44',y)];b=records[('f50_game_team',y)];assert all(a[k]==b[k]for k in ['training_pids','query_pids','target_hash','label_audit','policy_id'])
 assert sha(src/'reference_recipes.json')==m['reference_recipes_sha256']
 return records,{'passed':True,'reused_records':6,'new_control_fits':0,'exact_member_fold_seed_vectors':90,'source_records_unchanged':True,'M_frozen_sha256':protocol['M_frozen_sha256'],'source_record_hash_manifest_sha256':C.digest(hashes),'source_completed_log_sha256':m['M_completed_log_sha256']}
