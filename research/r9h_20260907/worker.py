"""Frozen observed-label policies; full queries and both prespecified scores."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,hashlib,importlib.util,time,copy,math
import numpy as np
ROOT=Path(__file__).resolve().parent;REF=Path('/reference');DATA=ROOT/'data'
spec=importlib.util.spec_from_file_location('r9h_G_reference',REF/'worker.py');G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G);B=G.B;D=G.D
_PLAN=None;_PAYLOADS={};_ENV=None

def digest(raw):return hashlib.sha256(raw).hexdigest()
def values_hash(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0.,0.,a);mask=np.isnan(a);a=np.where(mask,0.,a);return digest(json.dumps(list(a.shape),sort_keys=True,separators=(',',':')).encode()+mask.tobytes()+a.tobytes())
def plan():
 global _PLAN
 if _PLAN is None:
  f=json.loads((ROOT/'frozen.json').read_text())
  for name,sha in f['files'].items():assert digest((ROOT/name).read_bytes())==sha,name
  p=json.loads((ROOT/'plan.json').read_text());assert digest((ROOT/'plan.json').read_bytes())=='2a761d59bdf75adc60e33a8ea0a586b1b98a9a4aa37ffd62fb5728ac67b07e08'
  m=json.loads((ROOT/'source_manifest.json').read_text());assert digest((REF/'frozen.json').read_bytes())==m['reference_frozen_sha256']
  for name,sha in m['reference_files'].items():assert digest((REF/name).read_bytes())==sha,name
  assert p['execution']['task_count']==192 and len(p['canonical_payloads'])==21 and p['no_model_promotion'];_PLAN=p
 return _PLAN

def environment():
 global _ENV
 if _ENV is None:
  support=json.loads((ROOT/'runtime_support.json').read_text())
  for path,info in support['sources'].items():assert digest(Path(path).read_bytes())==info['sha256']
  _ENV=support
 return _ENV

def payload(pid,year):
 key=(pid,year)
 if key not in _PAYLOADS:
  import pandas as pd
  p=plan();item=next(x for x in p['canonical_payloads']if x['id']==pid);a=next(x for x in item['folds']if x['year']==year);q=p['queries'][str(year)]
  with np.load(DATA/f'{pid}_{year}.npz',allow_pickle=False)as f:tr={k:f[k].copy()for k in f.files}
  with np.load(DATA/f'query_{year}.npz',allow_pickle=False)as f:te={k:f[k].copy()for k in f.files}
  assert values_hash(tr['X'])==a['matrix_hash']and values_hash(tr['y'])==a['target_hash']and values_hash(te['X'])==q['matrix_hash']and values_hash(te['legacy_truth'])==q['legacy_truth_hash']
  assert digest(te['observed_truth_mask'].tobytes())==q['observed_mask_hash']and te['pid'].tolist()==q['query_pids']and tr['pid'].tolist()==a['training_pids']
  assert np.isfinite(tr['y']).all()and not np.isinf(tr['X']).any()and not set(tr['pid'])&set(te['pid'])
  atr=pd.DataFrame(tr['X'],columns=p['columns']);ate=pd.DataFrame(te['X'],columns=p['columns']);_PAYLOADS[key]=(atr,ate,tr,te,a,q)
 return _PAYLOADS[key]

def constructor(profile,seed):
 p=plan();cfg=p['profiles'][profile];params={**cfg['parameters'],('random_state'if cfg['model']=='TabICLRegressor'else'random_seed'):seed}
 if cfg['model']=='TabICLRegressor':
  from tabicl import TabICLRegressor
  model=TabICLRegressor(**params)
 else:
  from catboost import CatBoostRegressor
  model=CatBoostRegressor(**params)
 actual=model.get_params();assert all(actual[k]==v for k,v in params.items());return model,params

def cuda_proof(model,profile):
 p=plan();cfg=p['profiles'][profile]
 if cfg['model']=='CatBoostRegressor':
  actual=model.get_all_params();assert actual['task_type']=='GPU'and model.tree_count_==200
  for k in ['depth','learning_rate','l2_leaf_reg','bagging_temperature','nan_mode','loss_function','iterations']:
   v=cfg['parameters'][k]
   if isinstance(v,str):assert actual[k]==v
   else:assert np.isclose(actual[k],v,rtol=2e-7,atol=1e-9)
  return {'actual_device':'GPU','tree_count':200,'effective_constructor':actual}
 import torch
 modules={k:v for k,v in vars(model).items()if isinstance(v,torch.nn.Module)}
 devices=sorted({str(x.device)for m in modules.values()for x in m.parameters()});assert devices and all(x.startswith('cuda')for x in devices),(list(vars(model)),devices)
 generator=model.ensemble_generator_;count=sum(len(v)for v in generator.ensemble_configs_.values())
 return {'actual_devices':devices,'module_attributes':sorted(modules),'effective_estimators':count,'ensemble_config_hash':D.h(generator.ensemble_configs_),'feature_permutation_hash':D.h(generator.feature_shuffles_),'effective_features':int(generator.n_features_in_),'effective_constructor':model.get_params(deep=False)}

def score_record(row,te):
 pred=np.asarray([x['score']for x in row['predictions']]);assert [x['pid']for x in row['predictions']]==te['pid'].tolist();mask=te['observed_truth_mask'];assert mask.any()
 row['legacy_full_query_score']=B.rho(pred,te['legacy_truth']);row['observed_mask_score']=B.rho(pred[mask],te['legacy_truth'][mask]);row['observed_mask_rows']=int(mask.sum());row['stack']=row['legacy_full_query_score'];return row

def run_variant(vid,seed):
 p=plan();v=next(x for x in p['variants']if x['id']==vid);assert seed in p['seeds'];started=time.time()
 if v['kind']=='original_B_exact_reference':
  old=D.run_variant(vid,seed);entry=copy.deepcopy(old);entry['original_reference_config']=entry['config'];entry['config']=v
  for row in entry['rows']:
   with np.load(DATA/f"query_{row['season']}.npz",allow_pickle=False)as q:te={k:q[k]for k in q.files}
   score_record(row,te)
  entry['legacy_score']=old['score'];entry['observed_score']=float(np.mean([r['observed_mask_score']for r in entry['rows']]));return entry
 env=environment();rows=[]
 for year in p['folds']:
  atr,ate,tr,te,a,q=payload(v['payload_id'],year);model,kwargs=constructor(v['profile'],seed);before=values_hash(tr['y']);model.fit(atr,tr['y'].copy());assert values_hash(tr['y'])==before
  raw=np.asarray(model.predict(ate),dtype=float);assert raw.shape==(len(ate),)and np.isfinite(raw).all();native=cuda_proof(model,v['profile']);pred,ties=B._canonical_predictions(ate,raw,te['pid'].tolist())
  audit={'input_columns':p['columns'],'training_matrix_hash':a['matrix_hash'],'validation_matrix_hash':q['matrix_hash'],'training_labels_hash':a['target_hash'],'training_pid_hash':a['pid_hash'],'validation_pid_hash':q['pid_hash'],'training_max_draft_year':a['training_max_cohort'],'max_label_season':a['max_label_season'],'registered_model_parameters':kwargs,'canonical_prediction_ties':ties,'source_fact_hash':a['source_fact_hash'],'source_fact_rows':a['source_fact_rows'],'observed_mask_hash':q['observed_mask_hash'],'no_unknown_training_labels':True}
  row={'season':year,'cutoff':year-1,'k':q['horizon'],'n':len(ate),'ntrain':len(atr),'audit':audit,'model_design':native,'predictions':[{'pid':pid,'score':float(y),'raw_score':float(z)}for pid,y,z in zip(te['pid'],pred,raw)]};rows.append(score_record(row,te))
 legacy=float(np.mean([r['legacy_full_query_score']for r in rows]));observed=float(np.mean([r['observed_mask_score']for r in rows]))
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':legacy,'legacy_score':legacy,'observed_score':observed,'seconds':round(time.time()-started,2),'environment':env,'diagnostic_only':True,'score_display_policy':'score is legacy full-query diagnostic; observed_score is always reported separately'}

def validate_entry(e):
 p=plan();v=next(x for x in p['variants']if x['id']==e['config']['id']);assert e['config']==v and e['seed']in p['seeds']and e['task_id']==f"{v['id']}_seed{e['seed']}"and not e.get('error')
 assert [r['season']for r in e['rows']]==p['folds']and e['score']==e['legacy_score'];assert np.isclose(e['score'],np.mean([r['legacy_full_query_score']for r in e['rows']]),rtol=0,atol=1e-15)and np.isclose(e['observed_score'],np.mean([r['observed_mask_score']for r in e['rows']]),rtol=0,atol=1e-15)
 if v['kind']=='original_B_exact_reference':
  original={**e,'config':e['original_reference_config']};D.validate_entry(original)
 for row in e['rows']:
  with np.load(DATA/f"query_{row['season']}.npz",allow_pickle=False)as f:te={k:f[k]for k in f.files}
  computed=score_record(copy.deepcopy(row),te);assert all(computed[k]==row[k]for k in ['stack','legacy_full_query_score','observed_mask_score','observed_mask_rows']);B._validate_tie_record(row)
  if v['kind']!='original_B_exact_reference':
   atr,ate,tr,_,a,q=payload(v['payload_id'],row['season']);assert row['audit']['training_labels_hash']==a['target_hash']and row['audit']['input_columns']==p['columns']and row['audit']['max_label_season']<=row['cutoff']and row['audit']['training_max_draft_year']<=row['season']-1
   assert row['audit']['canonical_prediction_ties']['row_vector_hashes']==[B._hash(k)for k in B._exact_vector_keys(ate)]
   cfg=p['profiles'][v['profile']];expected={**cfg['parameters'],('random_state'if cfg['model']=='TabICLRegressor'else'random_seed'):e['seed']};assert row['audit']['registered_model_parameters']==expected
   d=row['model_design']
   if cfg['model']=='TabICLRegressor':assert d['actual_devices']and all(x.startswith('cuda')for x in d['actual_devices'])and d['effective_estimators']>0
   else:assert d['actual_device']=='GPU'and d['tree_count']==200 and d['effective_constructor']['random_seed']==e['seed']
 if v['kind']!='original_B_exact_reference':assert e['environment']==environment()

def summarize(entries):
 p=plan();tasks={}
 for e in entries:
  validate_entry(e);key=(e['config']['id'],e['seed']);assert key not in tasks;tasks[key]=e
 refs=[tasks.get(('drop5_001',seed))for seed in p['seeds']];done=sum(x is not None for x in refs);common={'completed_tasks':len(tasks),'expected_tasks':192,'reference_replays_passed':done,'interpretation_allowed':done==3,'diagnostic_only':True,'automatic_promotion':False,'metric_labels':{'score':'legacy full query with zero-filled unknown truth','observed_score':'fixed observed-truth mask; survivor-selection caveat'},'configurations':[]}
 if done<3:return common
 for v in p['variants'][1:]:
  if not all((v['id'],seed)in tasks for seed in p['seeds']):continue
  paired=[{'seed':seed,'season':row['season'],'legacy_score':row['legacy_full_query_score'],'observed_score':row['observed_mask_score'],'legacy_delta':row['legacy_full_query_score']-base['legacy_full_query_score'],'observed_delta':row['observed_mask_score']-base['observed_mask_score']}for seed in p['seeds']for row,base in zip(tasks[(v['id'],seed)]['rows'],tasks[('drop5_001',seed)]['rows'])]
  item={'id':v['id'],'config':v,'paired_rows':paired}
  for metric in ['legacy','observed']:
   item[metric]={'mean_score':float(np.mean([r[metric+'_score']for r in paired])),'mean_delta':float(np.mean([r[metric+'_delta']for r in paired])),'fold_deltas':{str(y):float(np.mean([r[metric+'_delta']for r in paired if r['season']==y]))for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r[metric+'_delta']for r in paired if r['seed']==s]))for s in p['seeds']}}
  common['configurations'].append(item)
 return common
