"""Only the declared TabICL profile varies; checkpoint, arrays and inference policy pinned."""
import numpy as np
import stack_core as C
import preprocessing as P
class Backend:
 def __init__(self,protocol,profile):self.protocol=protocol;self.profile=profile;self.fits=0
 def fit_predict(self,X,y,query,pids,seed,expected):
  from sklearn.utils.validation import validate_data
  import torch
  assert C.digest(pids)==expected['training_pid_hash']
  model,kw,actual=P.constructor(self.profile,seed,self.protocol);assert kw==expected['parameters']and actual==expected['effective_constructor']
  before=(C.array_hash(X),C.array_hash(y),C.array_hash(query));model.fit(X.astype(float),np.asarray(y).copy());self.fits+=1
  raw=np.asarray(model.predict(query.astype(float)),dtype=float);assert raw.shape==(len(query),)and np.isfinite(raw).all()and before==(C.array_hash(X),C.array_hash(y),C.array_hash(query))
  q=validate_data(model,query.astype(float),reset=False,dtype=None,skip_check_array=True);fp=P.fingerprint(model.ensemble_generator_,model.X_encoder_.transform(q));assert fp==expected['generator']
  modules=[m for m in vars(model).values()if isinstance(m,torch.nn.Module)];devices=sorted({str(p.device)for m in modules for p in m.parameters()});assert devices and all(x.startswith('cuda')for x in devices)
  return raw,{'parameters':kw,'effective_constructor':actual,'actual_devices':devices,'generator':fp,'requested_ensemble_count':kw['n_estimators'],'effective_ensemble_count':fp['effective_estimators'],'effective_feature_count':fp['effective_features'],'input_columns':list(X),'training_pid_hash':C.digest(pids),'training_matrix_hash':before[0],'training_target_hash':before[1],'query_matrix_hash':before[2],'preprocessing_design_hash':C.digest(expected),'query_outcomes_seen':False}
