"""Root-only exact L control provenance gate; source records are never rewritten."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'code'));import stack_core as C

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def verify(root=ROOT):
 root=Path(root);p=read(root/'plan.json');protocol=read(root/'code/protocol.json');src=root/'source_refs';assert sha(src/'manifest.json')==p['reference_source_manifest_sha256'];m=read(src/'manifest.json')
 assert m['L_frozen_sha256']==sha(src/'L_frozen.json')==protocol['L_frozen_sha256']and sha(src/'L_completed.jsonl')==m['source_completed_log_sha256']and sha(src/'L_completion.json')==m['source_completion_sha256']
 assert read(src/'L_completion.json')['status']=='completed'and read(src/'L_completion.json')['tasks']==24
 lines=(src/'L_completed.jsonl').read_bytes();assert lines.endswith(b'\n');logged=[json.loads(x)for x in lines.splitlines()];logmap={x['task_id']:x for x in logged};assert len(logmap)==len(logged)==24
 assert m['L_protocol_sha256']==protocol['L_protocol_sha256']and m['L_runtime_sha256']==sha(root/'code/runtime_support.json')and m['source_records_unchanged']and m['control_model_refits']==0
 for f,h in protocol['unchanged_L_model_files'].items():assert sha(root/'code'/f)==h
 frozen=read(src/'L_frozen.json')['files'];assert frozen['code/protocol.json']==m['L_protocol_sha256']and frozen['code/runtime_support.json']==m['L_runtime_sha256']
 records=[];maphash={};checked=0
 tasks=[t for t in p['tasks']if t['kind']=='reused_L_control'];assert len(tasks)==len(m['control_records'])==6
 for task in tasks:
  tid=task['id'];s=m['control_records'][tid];path=root/s['file'];assert sha(path)==s['sha256']==logmap[tid]['sha256']and s['source_completed_entry']==logmap[tid]
  r=read(path);assert s['source_input_manifest_sha256']==frozen[f'inputs/{tid}/manifest.json']
  original=s['source_input_manifest'];new=read(root/'inputs'/tid/'manifest.json');assert {k:v for k,v in original.items()if k!='protocol_sha256'}=={k:v for k,v in new.items()if k!='protocol_sha256'}
  assert original['protocol_sha256']==protocol['L_protocol_sha256']and new['protocol_sha256']==sha(root/'code/protocol.json')and sha(root/'inputs'/tid/'manifest.json')==task['input_manifest_sha256']
  assert r['fit_counts']=={'ridge_a30':1,'ridge_a300':1,'ridge_a3000':1,'tabicl':3,'catboost':3}
  assert r['input_manifest_sha256']==s['source_input_manifest_sha256']and r['protocol_sha256']==protocol['L_protocol_sha256']and r['runtime']['support_sha256']==m['L_runtime_sha256']
  assert r['task_id']==tid and r['outer_year']==task['outer_year']and r['panel_id']==task['panel_id']and r['policy_id']==task['policy_id']and r['label_audit']==new['label_audit']and r['columns']==new['columns']
  a=new['label_audit'];assert a['max_actual_label_season']<=task['outer_year']-1 and a['all_labels_finite_observed']and not a['missing_training_labels_zero_filled']
  for f,i in new['files'].items():assert sha(root/'inputs'/tid/f)==i['sha256']==original['files'][f]['sha256']
  with np.load(root/'inputs'/tid/'training.npz',allow_pickle=False)as t,np.load(root/'inputs'/tid/'inference.npz',allow_pickle=False)as q:
   assert t['pid'].tolist()==r['training_pids']and q['pid'].tolist()==r['query_pids']and not set(t['pid'])&set(q['pid'])and t['draft_year'].max()<task['outer_year']
   assert C.array_hash(t['X'])==r['training_matrix_hash']and C.array_hash(q['X'])==r['query_matrix_hash']and C.array_hash(t['y'])==r['target_hash']==a['target_hash']
   assert np.array_equal(C.gaussian_target(t['label_value'],t['draft_year']),t['y'])
   assert C.array_hash(t['label_value'])==a['label_value_hash']and C.digest(t['pid'].tolist())==a['training_pid_hash']and np.all(t['prefix_length']==1)
   assert [e['seed']for e in r['seed_results']]==protocol['seeds']
   for e in r['seed_results']:
    for family,member in e['members'].items():
     audit=member['model_audit'];expected={**protocol['tabicl'],'random_state':e['seed']}if family=='tabicl'else {**protocol['catboost']['parameters'],'random_seed':e['seed']}if family=='catboost'else {'alpha':int(family.removeprefix('ridge_a')),'solver':protocol['ridge']['solver']}
     assert audit['parameters']==expected and audit['training_matrix_hash']==r['training_matrix_hash']and audit['training_target_hash']==r['target_hash']and audit['query_matrix_hash']==r['query_matrix_hash']and audit['training_pid_hash']==a['training_pid_hash']and audit['input_columns']==new['columns']
     pred,ties=C.canonicalize(q['X'],member['raw_predictions'],r['query_pids']);assert np.array_equal(pred,member['canonical_predictions'])and ties==member['tie_audit'];checked+=1
  maphash[tid]=s['sha256'];records.append(r)
 assert checked==90
 gate={'passed':True,'reused_records':6,'new_control_fits':0,'reused_original_model_fits':54,'source_records_unchanged':True,'exact_member_fold_seed_vectors':checked,'L_frozen_sha256':m['L_frozen_sha256'],'source_record_hash_manifest_sha256':C.digest(maphash),'source_completed_log_sha256':m['source_completed_log_sha256'],'source_manifest_sha256':sha(src/'manifest.json'),'before_new_panel_fits':True}
 return records,gate
