"""Direct pinned constructors and training-only transformations for stack_core."""
import collections,json
import numpy as np
import pandas as pd
from stack_core import array_hash,digest

def finite_list(values):return [float(x)if np.isfinite(x)else None for x in values]
def ridge_statistics(X):return X.mean(),X.std(ddof=1).replace(0,1.)
def ridge_transform(X,mean,std):return ((X-mean)/std).fillna(0.)

class Backend:
 def __init__(self,protocol):self.protocol=protocol;self.counts=collections.Counter()
 def constructor(self,family,seed):
  if family=='tabicl':
   from tabicl import TabICLRegressor
   kw={**self.protocol['tabicl'],'random_state':seed};model=TabICLRegressor(**kw)
  elif family=='ridge':
   from sklearn.linear_model import Ridge
   kw={k:self.protocol['ridge'][k]for k in ['alpha','solver']};model=Ridge(**kw)
  else:
   from xgboost import XGBRegressor
   assert family in ['selector','xgb_q25','residual_q25'];kw=dict(self.protocol['selector']['parameters'])if family=='selector'else{**self.protocol['xgb_q25'],'random_state':seed};model=XGBRegressor(**kw)
  assert all(model.get_params()[k]==value for k,value in kw.items())
  return model,kw
 def select(self,X,y,pids,stage):
  model,kw=self.constructor('selector',11);before=(array_hash(X),array_hash(y));model.fit(X,np.asarray(y).copy());assert before==(array_hash(X),array_hash(y));self.counts['selector']+=1
  booster=model.get_booster();config=json.loads(booster.save_config());assert config['learner']['generic_param']['device']=='cuda:0'and booster.num_boosted_rounds()==300 and booster.feature_names==list(X)
  importance=np.asarray(model.feature_importances_,dtype=float);assert importance.shape==(len(X.columns),)and np.isfinite(importance).all()
  ordered=[c for _,c in sorted(zip(importance,X.columns),reverse=True)];selected=ordered[:min(100,len(ordered))]
  audit={'stage':stage,'training_pid_hash':digest(pids),'training_matrix_hash':before[0],'training_target_hash':before[1],'parameters':kw,'selected_columns':selected,'importance':dict(zip(X.columns,importance.tolist())),'effective_constructor':config,'query_or_held_labels_seen':False}
  return selected,audit
 def fit(self,family,X,y,seed,pids,stage):
  assert family in ['xgb_q25','tabicl','ridge','residual_q25'];model,kw=self.constructor(family,seed);assert len(X)==len(y)==len(pids)and np.isfinite(y).all()and not np.isinf(np.asarray(X)).any()
  before=(array_hash(X),array_hash(y));audit={'stage':stage,'family':family,'seed':seed,'input_columns':list(X),'training_pid_hash':digest(pids),'training_matrix_hash':before[0],'training_target_hash':before[1],'parameters':kw,'query_labels_seen':False}
  mu=sd=None;fit_X=X
  if family=='ridge':
   mu,sd=ridge_statistics(X);fit_X=ridge_transform(X,mu,sd);assert np.isfinite(np.asarray(fit_X)).all();audit['preprocessing']={'training_mean':finite_list(mu),'training_sample_std_ddof1':finite_list(sd),'standardized_training_hash':array_hash(fit_X),'missing_standardized_value':0.,'fit_rows':len(X),'fit_PID_hash':digest(pids)}
  model.fit(fit_X,np.asarray(y).copy());assert before==(array_hash(X),array_hash(y));self.counts[family]+=1
  if family in ['xgb_q25','residual_q25']:
   booster=model.get_booster();config=json.loads(booster.save_config());learner=config['learner'];assert learner['generic_param']['device']=='cuda:0'and learner['objective']['name']=='reg:quantileerror'and booster.num_boosted_rounds()==800 and booster.feature_names==list(X)
   assert int(learner['generic_param']['seed'])==seed and int(learner['generic_param']['nthread'])==2;audit['effective_constructor']=config;audit['tree_count']=800
  return {'model':model,'family':family,'audit':audit,'mu':mu,'sd':sd}
 def predict(self,record,X):
  model=record['model'];family=record['family'];assert list(X)==record['audit']['input_columns'];query=X
  if family=='ridge':query=ridge_transform(X,record['mu'],record['sd']);assert np.isfinite(np.asarray(query)).all()
  raw=np.asarray(model.predict(query),dtype=float);assert raw.shape==(len(X),)and np.isfinite(raw).all();audit={**record['audit'],'query_matrix_hash':array_hash(X)}
  if family=='ridge':audit['standardized_query_hash']=array_hash(query)
  elif family=='tabicl':
   import torch
   modules={name:m for name,m in vars(model).items()if isinstance(m,torch.nn.Module)};devices=sorted({str(p.device)for m in modules.values()for p in m.parameters()});assert devices and all(d.startswith('cuda')for d in devices)
   gen=model.ensemble_generator_;audit['effective_constructor']=model.get_params(deep=False);audit['actual_devices']=devices;audit['effective_feature_count']=int(gen.n_features_in_);audit['effective_ensemble_count']=sum(len(v)for v in gen.ensemble_configs_.values());audit['requested_ensemble_count']=32
   assert audit['effective_ensemble_count']>0
  return raw,audit
