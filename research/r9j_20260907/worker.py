"""Fixed H matrices, observed targets and model-family members for R9j stacks."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,hashlib,importlib.util,copy,time
import numpy as np
ROOT=Path(__file__).resolve().parent;HR=Path('/h_reference')
spec=importlib.util.spec_from_file_location('r9j_frozen_H',HR/'worker.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H);B=H.B
_PLAN=None;_REF=None
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def plan():
 global _PLAN
 if _PLAN is None:
  f=json.loads((ROOT/'frozen.json').read_text())
  for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
  p=json.loads((ROOT/'plan.json').read_text());m=json.loads((ROOT/'source_manifest.json').read_text())
  assert p['execution']['task_count']==len(p['tasks'])==48 and len(p['payloads'])==3 and p['stacks']['weight_fit'].startswith('none')
  assert sha(HR/'frozen.json')==m['H_frozen_sha256'];H.plan();H.environment()
  for name,digest in m['H_files'].items():assert sha(HR/name)==digest
  for name,info in m['H_reference_files'].items():assert sha(HR/name)==info['sha256']
  support=json.loads((ROOT/'runtime_support.json').read_text())
  for name,info in support['sources'].items():assert sha(Path(name))==info['sha256']
  _PLAN=p
 return _PLAN
def refs():
 global _REF
 if _REF is None:_REF={(e['config']['id'],e['seed']):e for e in json.loads((ROOT/'references.json').read_text())['records']};assert len(_REF)==12
 return _REF
def setting(v):return next(s for s in plan()['settings']if s['id']==v['setting_id'])
def parameters(v,seed):
 s=setting(v);assert seed in s['seeds'];return {**s['parameters'],**({}if s['family']=='ridge'else{('random_seed'if s['family']=='catboost'else'random_state'):seed})}
def make_model(v,seed):
 s=setting(v);kw=parameters(v,seed)
 if s['family']=='ridge':
  from sklearn.pipeline import Pipeline
  from sklearn.impute import SimpleImputer
  from sklearn.preprocessing import StandardScaler
  from sklearn.linear_model import Ridge
  model=Pipeline([('imputer',SimpleImputer(**s['preprocessing']['imputer'])),('scaler',StandardScaler(**s['preprocessing']['scaler'])),('regressor',Ridge(**kw))]);assert all(model.named_steps['regressor'].get_params()[k]==x for k,x in kw.items())
 elif s['family']=='xgb':
  from xgboost import XGBRegressor
  model=XGBRegressor(**kw);assert all(model.get_params()[k]==x for k,x in kw.items())
 else:
  from catboost import CatBoostRegressor
  model=CatBoostRegressor(**kw);assert model.get_params()==kw
 return model,kw
def fit_native(model,atr,yy):
 before=(H.values_hash(atr),H.values_hash(yy));model.fit(atr,yy.copy());assert before==(H.values_hash(atr),H.values_hash(yy))
def preprocessing(model,atr,ate):
 im=model.named_steps['imputer'];sc=model.named_steps['scaler'];x=im.transform(atr);q=im.transform(ate)
 return {'median':im.statistics_.tolist(),'indicator_columns':im.indicator_.features_.tolist(),'scaler_mean':sc.mean_.tolist(),'scaler_scale':sc.scale_.tolist(),'scaler_var':sc.var_.tolist(),'training_rows_seen':int(sc.n_samples_seen_),'imputed_training_hash':H.values_hash(x),'imputed_query_hash':H.values_hash(q),'transformed_training_hash':H.values_hash(sc.transform(x)),'transformed_query_hash':H.values_hash(sc.transform(q))}
def validate_preprocessing(a,atr,ate):
 x=np.asarray(atr);q=np.asarray(ate);expected=np.array([np.median(c[np.isfinite(c)])if np.isfinite(c).any()else 0. for c in x.T]);assert np.array_equal(expected,a['median'])
 indicators=np.flatnonzero(np.isnan(x).any(axis=0));assert indicators.tolist()==a['indicator_columns']
 transformed=[]
 for frame,name in [(x,'training'),(q,'query')]:
  z=np.concatenate([np.where(np.isnan(frame),expected,frame),np.isnan(frame[:,indicators])],axis=1)
  assert H.values_hash(z)==a[f'imputed_{name}_hash'];transformed.append(z)
 assert a['training_rows_seen']==len(x)and np.allclose(a['scaler_mean'],transformed[0].mean(axis=0),rtol=1e-12,atol=1e-12)and np.allclose(a['scaler_var'],transformed[0].var(axis=0),rtol=1e-12,atol=1e-12)
 mean=np.asarray(a['scaler_mean']);scale=np.asarray(a['scaler_scale']);assert np.isfinite(scale).all()and (scale>0).all()
 for z,name in zip(transformed,['training','query']):assert H.values_hash((z-mean)/scale)==a[f'transformed_{name}_hash']
def validate_effective(a,s,kw):
 family=s['family']
 if family=='xgb':
  assert a['device']=='cuda:0'and a['trees']==600 and a['feature_count']==44
  c=a['config']['learner'];assert c['generic_param']['device']=='cuda:0'and c['objective']['name']=='reg:squarederror'
  t=c['gradient_booster']['tree_train_param']
  for key,saved in [('max_depth','max_depth'),('min_child_weight','min_child_weight'),('reg_lambda','lambda'),('learning_rate','eta'),('subsample','subsample'),('colsample_bytree','colsample_bytree')]:assert np.isclose(float(t[saved]),kw[key],rtol=2e-7,atol=1e-9)
  assert int(c['generic_param']['seed'])==kw['random_state']and int(c['generic_param']['nthread'])==2 and c['gradient_booster']['gbtree_train_param']['tree_method']=='hist'
 elif family=='catboost':
  assert a['device']=='GPU'and a['trees']==600 and a['feature_names']==plan()['columns']and set(a['evaluation_sets'])<= {'learn'}
  c=a['constructor'];assert c['random_seed']==kw['random_seed']and c['task_type']=='GPU'
  for key in ['iterations','loss_function','depth','learning_rate','l2_leaf_reg','bagging_temperature','nan_mode','bootstrap_type','boosting_type','random_strength','use_best_model']:
   value=kw[key]
   if isinstance(value,(int,float))and not isinstance(value,bool):assert np.isclose(c[key],value,rtol=2e-7,atol=1e-9)
   else:assert c[key]==value
 else:assert a['device']=='CPU'and a['constructor']==kw
def predict_at(model,ate,s,checkpoint):
 assert checkpoint in s['checkpoints']
 if s['family']=='catboost':assert 0<checkpoint<=model.tree_count_;raw=model.predict(ate,ntree_end=checkpoint,thread_count=2)
 elif s['family']=='xgb':assert checkpoint==600;raw=model.predict(ate,iteration_range=(0,600))
 else:assert checkpoint is None;raw=model.predict(ate)
 raw=np.asarray(raw,dtype=float);assert raw.shape==(len(ate),)and np.isfinite(raw).all();return raw
def run_variant(vid,seed):
 p=plan();v=next(x for x in p['variants']if x['id']==vid);assert {'variant':vid,'seed':seed}in p['tasks'];started=time.time()
 if v['kind']!='stack_member_candidate':
  old=H.run_variant(v['H_variant_id'],seed);return {**old,'config':v,'task_id':f'{vid}_seed{seed}','original_H_config':old['config'],'original_H_task_id':old['task_id']}
 s=setting(v);rows=[]
 for year in p['folds']:
  atr,ate,tr,te,a,q=H.payload(v['payload_id'],year);model,kw=make_model(v,seed);fit_native(model,atr,tr['y'])
  if s['family']=='ridge':native={'device':'CPU','constructor':kw,'preprocessing':preprocessing(model,atr,ate)};validate_preprocessing(native['preprocessing'],atr,ate)
  elif s['family']=='xgb':
   booster=model.get_booster();config=json.loads(booster.save_config());native={'device':config['learner']['generic_param']['device'],'trees':booster.num_boosted_rounds(),'feature_count':booster.num_features(),'config':config};assert booster.feature_names==p['columns']
  else:native={'device':model.get_all_params()['task_type'],'trees':model.tree_count_,'feature_names':model.feature_names_,'constructor':model.get_all_params(),'evaluation_sets':list(model.get_evals_result())}
  validate_effective(native,s,kw);anchor=next(r for r in refs()[(v['matched_anchor_variant'],seed)]['rows']if r['season']==year);audit=copy.deepcopy(anchor['audit']);audit.pop('canonical_prediction_ties');audit['registered_model_parameters']=kw;checkpoints=[]
  for end in s['checkpoints']:
   raw=predict_at(model,ate,s,end);pred,ties=B._canonical_predictions(ate,raw,te['pid'].tolist());cp={'checkpoint':end,'predictions':[{'pid':pid,'score':float(x),'raw_score':float(y)}for pid,x,y in zip(te['pid'],pred,raw)],'canonical_prediction_ties':ties};checkpoints.append(H.score_record(cp,te))
  last=checkpoints[-1];rows.append({'season':year,'cutoff':year-1,'k':q['horizon'],'n':len(ate),'ntrain':len(atr),'audit':audit,'model_design':native,'checkpoints':checkpoints,'stack':last['stack'],'legacy_full_query_score':last['legacy_full_query_score'],'observed_mask_score':last['observed_mask_score']})
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack']for r in rows])),'legacy_score':float(np.mean([r['stack']for r in rows])),'observed_score':float(np.mean([r['observed_mask_score']for r in rows])),'seconds':round(time.time()-started,2),'environment':H.environment(),'diagnostic_only':True}
def validate_entry(e):
 p=plan();v=next(x for x in p['variants']if x['id']==e['config']['id']);seed=e['seed'];assert e['config']==v and {'variant':v['id'],'seed':seed}in p['tasks']and e['task_id']==f"{v['id']}_seed{seed}"and not e.get('error')
 if v['kind']!='stack_member_candidate':
  old={k:val for k,val in e.items()if k not in ['original_H_config','original_H_task_id']};old['config']=e['original_H_config'];old['task_id']=e['original_H_task_id'];H.validate_entry(old);reference=refs()[(v['H_variant_id'],seed)];assert {k:x for k,x in old.items()if k!='seconds'}=={k:x for k,x in reference.items()if k!='seconds'};return
 s=setting(v);kw=parameters(v,seed);assert [r['season']for r in e['rows']]==p['folds']and e['environment']==H.environment()and e['diagnostic_only']
 for row in e['rows']:
  atr,ate,tr,te,a,q=H.payload(v['payload_id'],row['season']);anchor=next(r for r in refs()[(v['matched_anchor_variant'],seed)]['rows']if r['season']==row['season']);audit=copy.deepcopy(anchor['audit']);audit.pop('canonical_prediction_ties');audit['registered_model_parameters']=kw
  assert row['audit']==audit and row['cutoff']==row['season']-1 and row['ntrain']==len(atr)and row['n']==len(ate)and a['max_label_season']<=row['cutoff'];validate_effective(row['model_design'],s,kw)
  if s['family']=='ridge':validate_preprocessing(row['model_design']['preprocessing'],atr,ate)
  assert [c['checkpoint']for c in row['checkpoints']]==s['checkpoints']
  for cp in row['checkpoints']:
   calculated=H.score_record(copy.deepcopy(cp),te);assert all(cp[k]==calculated[k]for k in ['stack','legacy_full_query_score','observed_mask_score','observed_mask_rows']);assert cp['canonical_prediction_ties']['row_vector_hashes']==anchor['audit']['canonical_prediction_ties']['row_vector_hashes'];B._validate_tie_record({**row,'predictions':cp['predictions'],'audit':{**row['audit'],'canonical_prediction_ties':cp['canonical_prediction_ties']}})
  assert all(row[k]==row['checkpoints'][-1][k]for k in ['stack','legacy_full_query_score','observed_mask_score'])
 assert e['score']==e['legacy_score']==float(np.mean([r['stack']for r in e['rows']]))and e['observed_score']==float(np.mean([r['observed_mask_score']for r in e['rows']]))
def summarize(entries):
 p=plan();tasks={}
 for e in entries:validate_entry(e);assert e['task_id']not in tasks;tasks[e['task_id']]=e
 refs_n=sum(e['config']['kind']!='stack_member_candidate'for e in entries)
 out={'completed_tasks':len(tasks),'expected_tasks':48,'reference_replays_passed':refs_n,'reference_replays_expected':12,'interpretation_allowed':refs_n==12,'diagnostic_only':True,'automatic_promotion':False,'configurations':[]}
 if refs_n<12:return out
 for v in p['variants']:
  if v['kind']!='stack_member_candidate':continue
  seedlist=setting(v)['seeds'];group=[tasks.get(f"{v['id']}_seed{s}")for s in seedlist]
  if all(group):out['configurations'].append({'id':v['id'],'seeds':seedlist,'legacy_mean':float(np.mean([e['legacy_score']for e in group])),'observed_mean':float(np.mean([e['observed_score']for e in group]))})
 return out
