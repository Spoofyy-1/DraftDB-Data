"""Training-only TabICL preprocessing fingerprints; no predictive model fit or score."""
import hashlib,json,math,warnings
import numpy as np
import stack_core as C

def finite_json(value):
 if isinstance(value,dict):return {k:finite_json(v)for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [finite_json(v)for v in value]
 if isinstance(value,np.ndarray):return finite_json(value.tolist())
 if isinstance(value,np.generic):return finite_json(value.item())
 if isinstance(value,float)and not math.isfinite(value):raise ValueError('Nonfinite configuration/preprocessing value')
 json.dumps(value,allow_nan=False);return value

def parameters(profile,seed,protocol):
 finite_json(profile);assert set(profile)=={'id','norm_methods','outlier_threshold','n_estimators'}and seed in protocol['seeds']
 assert profile['norm_methods']in ['none','power']and type(profile['n_estimators'])is int and profile['n_estimators']in [16,32,64,128,256]
 assert type(profile['outlier_threshold'])in [int,float]and profile['outlier_threshold']in [.5,1.,2.,4.]
 return {**protocol['tabicl_base'],**{k:profile[k]for k in ['norm_methods','outlier_threshold','n_estimators']},'random_state':seed}
def constructor(profile,seed,protocol):
 from tabicl import TabICLRegressor
 kw=parameters(profile,seed,protocol);model=TabICLRegressor(**kw);actual=finite_json(model.get_params(deep=False));assert all(actual[k]==v for k,v in kw.items());return model,kw,actual

def fingerprint(generator,query):
 views=generator.transform(query,mode='both');h=hashlib.sha256();shapes=[]
 for method,arrays in views.items():
  h.update(method.encode())
  for a in arrays:
   a=np.asarray(a)
   if not np.isfinite(a).all():raise ValueError('Nonfinite prepared model tensor')
   h.update(str(a.shape).encode());h.update(str(a.dtype).encode());h.update(a.tobytes());shapes.append({'method':method,'shape':list(a.shape),'dtype':str(a.dtype)})
 return {'effective_estimators':sum(len(v)for v in generator.ensemble_configs_.values()),'effective_features':int(generator.n_features_in_),'ensemble_config_hash':C.digest(finite_json(generator.ensemble_configs_)),'feature_permutation_hash':C.digest(finite_json(generator.feature_shuffles_)),'ordered_methods':list(views),'transformed_views_hash':h.hexdigest(),'prepared_tensor_shapes':shapes}

def prepare(X,target,query,profile,seed,protocol,pids,query_pids):
 from sklearn.preprocessing import StandardScaler
 from sklearn.utils.validation import validate_data
 from tabicl._sklearn.preprocessing import EnsembleGenerator,TransformToNumerical
 model,kw,actual=constructor(profile,seed,protocol)
 # This is the installed TabICL fit preprocessing order, without model.fit or predict.
 a,y=validate_data(model,X.astype(float),target,dtype=None,skip_check_array=True);q=validate_data(model,query.astype(float),reset=False,dtype=None,skip_check_array=True)
 y=np.asarray(y,dtype=np.float32);assert np.isfinite(y).all();ys=StandardScaler().fit_transform(y.reshape(-1,1)).flatten();assert np.isfinite(ys).all()
 encoder=TransformToNumerical(verbose=False)
 with warnings.catch_warnings(record=True)as logged:
  warnings.simplefilter('always');a=encoder.fit_transform(a);q=encoder.transform(q)
  generator=EnsembleGenerator(classification=False,n_estimators=actual['n_estimators'],norm_methods=actual['norm_methods'],feat_shuffle_method=actual['feat_shuffle_method'],outlier_threshold=actual['outlier_threshold'],random_state=seed)
  generator.fit(a,ys);fp=fingerprint(generator,q)
 return {'profile_id':profile['id'],'seed':seed,'training_pid_hash':C.digest(pids),'query_pid_hash':C.digest(query_pids),'parameters':kw,'effective_constructor':actual,'generator':fp,'original_training_matrix_hash':C.array_hash(X),'original_query_matrix_hash':C.array_hash(query),'original_target_hash':C.array_hash(target),'encoder_training_matrix_hash':C.array_hash(a),'encoder_query_matrix_hash':C.array_hash(q),'standardized_float32_target_hash':C.array_hash(ys),'columns':list(X),'warnings':[str(w.message)for w in logged],'model_fits':0,'GPU_predictions':0,'query_outcomes_seen':False}
def equality_signature(designs):
 items={}
 for key,d in designs.items():
  v={k:x for k,x in d.items()if k not in ['profile_id','warnings','parameters','effective_constructor']};v['effective_constructor']={k:x for k,x in d['effective_constructor'].items()if k!='n_estimators'};items[key]=v
 return C.digest(items)
