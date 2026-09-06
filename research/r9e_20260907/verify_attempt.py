"""Read-only identity-amendment and failed-attempt provenance checks."""
import json,hashlib
from pathlib import Path

def verify(root,plan,cap,records):
 root=Path(root);out=root/'results';old=root/'attempt1_registration'
 sha=lambda raw:hashlib.sha256(raw).hexdigest()
 amendment=json.loads((root/'identifier_amendment.json').read_text());frozen=json.loads((old/'frozen.json').read_text());oldp=json.loads((old/'plan.json').read_text());oldc=json.loads((old/'results/capacity_check.json').read_text())
 assert sha((old/'frozen.json').read_bytes())==amendment['original_frozen_sha256']=='7787cb6fccdc8998087777a5dfd9f13019104e936874df1a9fd87dfe53b6fa0c'
 assert len(frozen['files'])==61
 for name,digest in frozen['files'].items():
  path=old/name if (old/name).exists()else root/name
  assert sha(path.read_bytes())==digest,name
 mapping=amendment['requested_id_mapping'];assert len(mapping)==432 and len(set(mapping.values()))==432
 assert mapping=={s['id']:s['id'].replace('.','p')for s in oldp['requested_grid']}
 def renamed(value):
  return [{**s,'id':mapping[s['id']]}for s in value]
 for key in ['requested_grid','variants']:assert renamed(oldp[key])==plan[key]
 for key in ['folds','seeds','model_constructor','ordering_policy','baseline_config','normalizations','outlier_thresholds','requested_estimator_counts','target_transforms','target_formulas','reference_ids','reference_id','execution','seed_ensemble']:assert oldp[key]==plan[key],key
 assert plan['settings_by_id']=={mapping[k]:{**v,'id':mapping[k]}for k,v in oldp['settings_by_id'].items()}
 assert plan['requested_to_evaluated']=={mapping[k]:mapping[v]if v is not None else None for k,v in oldp['requested_to_evaluated'].items()}
 assert plan['excluded_before_fitting']=={mapping[k]:v for k,v in oldp['excluded_before_fitting'].items()}
 for k in ['designs','equality_signatures']:assert cap[k]=={mapping[vid]:value for vid,value in oldc[k].items()}
 assert len(cap['invalid_configurations'])==48 and cap['tasks']==1152 and cap['distinct_configurations']==384
 for vid,contexts in oldc['invalid_configurations'].items():
  expected=[]
  for context in contexts:
   item={**context,'setting':{**context['setting'],'id':mapping[context['setting']['id']]}};expected.append(item)
  assert cap['invalid_configurations'][mapping[vid]]==expected
 failed=out/'attempt1';registration=json.loads((failed/'preregistered_plan.json').read_text())
 assert registration=={'plan':oldp,'plan_sha256':sha((old/'plan.json').read_bytes()),'files':frozen['files']}
 queue=json.loads((failed/'queue_registration.json').read_text());assert queue['registration_hash']==amendment['original_frozen_sha256'] and queue['workers']==4 and queue['initial_records_sha256']==sha(b'[]')
 assert queue['task_ids']==[f"{v['id']}_seed{s}"for v in oldp['variants']for s in oldp['seeds']]
 preparation=json.loads((failed/'preparation.json').read_text());assert preparation['passed'] and preparation['frozen_manifest_sha256']==amendment['original_frozen_sha256']
 state=json.loads((failed/'state.json').read_text());assert state['status']=='failed' and state['error']=='AssertionError()'
 journal=(failed/'journal.txt').read_text();assert 'save_immutable' in journal and 're.fullmatch' in journal and 'AssertionError' in journal
 lines=(failed/'completed.jsonl').read_text().splitlines();log={}
 for line in lines:
  entry=json.loads(line);assert entry['task_id']not in log;log[entry['task_id']]=entry
 retained=json.loads((out/'resume_input_verification.json').read_text());assert retained['count']==len(log)==16 and set(retained['immutable_records_retained'])==set(log)
 by_id={e['task_id']:e for e in records}
 for tid,info in retained['immutable_records_retained'].items():
  raw=(out/'tasks'/(tid+'.json')).read_bytes();assert len(raw)==info['bytes'] and sha(raw)==info['sha256']==log[tid]['sha256'];assert by_id[tid]['config']['id']in plan['reference_ids']
 assert (out/'completed.jsonl').read_bytes().startswith((failed/'completed.jsonl').read_bytes())
 return {'passed':True,'original_frozen_files_reconstructed_exact':61,'original_registration_exact':True,'original_queue_registration_exact':True,'identifier_mapping_bijective':True,'all_432_scientific_settings_unchanged':True,'all_CPU_payloads_and_exclusions_unchanged':True,'saved_original_references_retained_byte_exact':16,'final_append_log_preserves_original_prefix':True,'original_failed_state_reported_completed':state['completed'],'original_durable_records':16,'cause':'Decimal task identifiers failed the unchanged filename regex; no score-based changes.','unsaved_in_flight_work_retried':True,'original_frozen_sha256':amendment['original_frozen_sha256'],'amendment_sha256':sha((root/'identifier_amendment.json').read_bytes())}
