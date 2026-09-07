"""Pinned J TabICL/Ridge and one prespecified GPU CatBoost profile. No scorer."""
import collections,json
import numpy as np
from stack_core import array_hash,digest
class Backend:
 def __init__(self,protocol):self.protocol=protocol;self.counts=collections.Counter()
 def constructor(self,family,seed):
  if family.startswith('ridge_a'):
   from sklearn.pipeline import Pipeline
   from sklearn.impute import SimpleImputer
   from sklearn.preprocessing import StandardScaler
   from sklearn.linear_model import Ridge
   alpha=int(family.removeprefix('ridge_a'));assert alpha in self.protocol['ridge']['alphas']and seed==0
   p=self.protocol['ridge'];kw={'alpha':alpha,'solver':p['solver']}
   model=Pipeline([('imputer',SimpleImputer(**p['imputer'])),('scaler',StandardScaler(**p['scaler'])),('regressor',Ridge(**kw))]);assert all(model.named_steps['regressor'].get_params()[k]==v for k,v in kw.items())
  elif family=='tabicl':
   from tabicl import TabICLRegressor
   assert seed in self.protocol['seeds'];kw={**self.protocol['tabicl'],'random_state':seed};model=TabICLRegressor(**kw);assert all(model.get_params()[k]==v for k,v in kw.items())
  else:
   from catboost import CatBoostRegressor
   assert family=='catboost'and seed in self.protocol['seeds'];kw={**self.protocol['catboost']['parameters'],'random_seed':seed};model=CatBoostRegressor(**kw);assert model.get_params()==kw
  return model,kw
 def preprocessing(self,model,X,query):
  im=model.named_steps['imputer'];sc=model.named_steps['scaler'];x=im.transform(X);q=im.transform(query);raw=np.asarray(X)
  med=np.array([np.median(c[np.isfinite(c)])if np.isfinite(c).any()else 0. for c in raw.T]);assert np.array_equal(med,im.statistics_)
  indicators=np.flatnonzero(np.isnan(raw).any(axis=0));assert np.array_equal(indicators,im.indicator_.features_)
  for frame,name in [(X,'training'),(query,'query')]:
   a=np.asarray(frame);expected=np.concatenate([np.where(np.isnan(a),med,a),np.isnan(a[:,indicators])],axis=1)
   assert np.array_equal(im.transform(frame),expected)
  assert int(sc.n_samples_seen_)==len(X)and np.allclose(sc.mean_,x.mean(axis=0),rtol=1e-12,atol=1e-12)and np.allclose(sc.var_,x.var(axis=0),rtol=1e-12,atol=1e-12)
  return {'median':im.statistics_.tolist(),'indicator_columns':im.indicator_.features_.tolist(),'scaler_mean':sc.mean_.tolist(),'scaler_scale':sc.scale_.tolist(),'scaler_var':sc.var_.tolist(),'training_rows_seen':int(sc.n_samples_seen_),'imputed_training_hash':array_hash(x),'imputed_query_hash':array_hash(q),'transformed_training_hash':array_hash(sc.transform(x)),'transformed_query_hash':array_hash(sc.transform(q))}
 def fit_predict(self,family,X,y,query,seed,pids):
  model,kw=self.constructor(family,seed);assert list(X)==list(query)and len(X)==len(y)==len(pids)and np.isfinite(y).all()
  before=(array_hash(X),array_hash(y),array_hash(query));model.fit(X,np.asarray(y).copy());self.counts[family]+=1
  assert before==(array_hash(X),array_hash(y),array_hash(query))
  audit={'family':family,'seed':seed,'input_columns':list(X),'training_pid_hash':digest(pids),'training_matrix_hash':before[0],'training_target_hash':before[1],'query_matrix_hash':before[2],'parameters':kw,'query_or_validation_labels_seen':False,'eval_set_supplied':False,'early_stopping':False}
  if family=='catboost':
   end=self.protocol['catboost']['checkpoint'];assert isinstance(end,int)and 0<end<=model.tree_count_==kw['iterations']
   effective=model.get_all_params();assert effective['task_type']=='GPU'and effective['random_seed']==seed and model.feature_names_==list(X)and set(model.get_evals_result())<= {'learn'}
   for key in ['iterations','loss_function','depth','learning_rate','l2_leaf_reg','bagging_temperature','nan_mode','bootstrap_type','boosting_type','random_strength','use_best_model']:
    v=kw[key]
    if isinstance(v,(int,float))and not isinstance(v,bool):assert np.isclose(effective[key],v,rtol=2e-7,atol=1e-9)
    else:assert effective[key]==v
   raw=model.predict(query,ntree_end=end,thread_count=2);audit.update(effective_constructor=effective,actual_device='GPU',tree_count=model.tree_count_,checkpoint=end)
  else:raw=model.predict(query)
  raw=np.asarray(raw,dtype=float);assert raw.shape==(len(query),)and np.isfinite(raw).all()
  if family.startswith('ridge_'):audit.update(preprocessing=self.preprocessing(model,X,query),effective_constructor=kw,actual_device='CPU')
  elif family=='tabicl':
   import torch
   modules=[m for m in vars(model).values()if isinstance(m,torch.nn.Module)];devices=sorted({str(p.device)for m in modules for p in m.parameters()});assert devices and all(d.startswith('cuda')for d in devices)
   gen=model.ensemble_generator_;audit.update(effective_constructor=model.get_params(deep=False),actual_devices=devices,effective_feature_count=int(gen.n_features_in_),effective_ensemble_count=sum(len(v)for v in gen.ensemble_configs_.values()),requested_ensemble_count=32)
   assert audit['effective_ensemble_count']>0
  return raw,audit
