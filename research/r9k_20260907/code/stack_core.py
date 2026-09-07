"""Outer-cutoff OOF stack engine. No query truth or scoring interface exists here."""
import hashlib,json,math,collections
import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata
from scipy.optimize import nnls

FAMILIES=['xgb_q25','tabicl','ridge']
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def array_hash(value):
 a=np.asarray(value,dtype=np.float64);a=np.where(a==0,0,a);missing=np.isnan(a);return hashlib.sha256(json.dumps(list(a.shape),separators=(',',':')).encode()+missing.tobytes()+np.where(missing,0.,a).tobytes()).hexdigest()
def rank_percentile(value):
 a=np.asarray(value,dtype=float);assert a.ndim==1 and len(a)>0 and np.isfinite(a).all()
 return np.rint(2*rankdata(a,method='average')).astype(np.int64)/(2*len(a))
def gaussian_target(label_values,cohorts):
 values=np.asarray(label_values,dtype=float);cohorts=np.asarray(cohorts);assert values.shape==cohorts.shape and np.isfinite(values).all()
 clipped=np.clip(values,-40,40);target=np.empty(len(values))
 for year in np.unique(cohorts):
  keep=cohorts==year;n=int(keep.sum());target[keep]=ndtri(np.clip((rankdata(clipped[keep],method='average')-.5)/n,.01,.99))
 return target
def canonical_order(pids):
 assert len(set(pids))==len(pids)and all(isinstance(p,str)for p in pids)
 return np.array(sorted(range(len(pids)),key=lambda i:(hashlib.sha256(pids[i].encode()).hexdigest(),pids[i])),dtype=int)
def assignments(pids):return np.array([int(hashlib.sha256(p.encode()).hexdigest(),16)%3 for p in pids])
def vector_keys(frame):
 a=np.asarray(frame,dtype=float);assert a.ndim==2 and not np.isinf(a).any()
 return [tuple(None if np.isnan(v)else('0x0.0p+0'if v==0 else float(v).hex())for v in row)for row in a]
def canonicalize(frame,prediction,pids):
 raw=np.asarray(prediction,dtype=float);assert raw.shape==(len(frame),)and np.isfinite(raw).all()and len(pids)==len(raw)
 groups=collections.defaultdict(list)
 for i,key in enumerate(vector_keys(frame)):groups[key].append(i)
 result=raw.copy();duplicate=[]
 for indices in groups.values():
  if len(indices)>1:
   value=math.fsum(sorted(float(raw[i])for i in indices))/len(indices);result[indices]=value
   duplicate.append({'pids':[pids[i]for i in indices],'assigned':value,'raw':[float(raw[i])for i in indices]})
 return result,{'duplicate_groups':duplicate,'raw_hash':array_hash(raw),'canonical_hash':array_hash(result),'input_vector_hashes':[digest(k)for k in vector_keys(frame)]}
def validate_equal_groups(frame,prediction):
 seen={}
 for key,value in zip(vector_keys(frame),prediction):
  if key in seen:assert value==seen[key]
  else:seen[key]=value

def nonnegative_meta(oof,outer_target):
 assert list(oof)==FAMILIES
 matrix=np.column_stack([rank_percentile(oof[name])for name in FAMILIES]);target=rank_percentile(outer_target)
 assert matrix.shape==(len(target),3)and len(target)>=20
 raw,loss=nnls(matrix,target);assert np.isfinite(raw).all()and (raw>=0).all()
 fallback=bool(raw.sum()==0);weights=np.ones(3)/3 if fallback else raw/raw.sum()
 assert (weights>=0).all()and np.isclose(weights.sum(),1)
 return weights,{'family_order':FAMILIES,'weights':weights.tolist(),'unnormalized_weights':raw.tolist(),'nnls_residual_norm':float(loss),'equal_weight_zero_sum_fallback':fallback,'OOF_rank_matrix_hash':array_hash(matrix),'outer_training_rank_target_hash':array_hash(target),'rows':len(target),'query_truth_accessed':False,'residual_member_included':False}

def _stage(backend,X,y,train_pids,stage):
 """Each selector and each fit receives this stage's training values only."""
 selected,selector=backend.select(X,y,train_pids,stage)
 assert selected and len(selected)<=min(100,len(X.columns))and len(set(selected))==len(selected)and set(selected)<=set(X)
 ridge=backend.fit('ridge',X,y,0,train_pids,stage)
 return selected,selector,ridge

def run_outer(X,query,metadata,query_pids,label_values,target,outer_year,backend,seeds=(0,101,202),label_audit=None):
 """All label values are admitted/verified by root's frozen policy exporter.

 No query labels, observed-query mask, draft picks or validation scores are accepted.
 The backend only sees numeric X/y subsets and PID audit metadata; PIDs never predictors.
 """
 assert list(metadata)==['pid','draft_year']and list(X)==list(query)and len(X)==len(metadata)
 assert len(set(X.columns))==len(X.columns)and not set(X)&{'pid','draft_year','actual_pick','was_drafted','qid'}
 pids=metadata.pid.tolist();assert np.array_equal(canonical_order(pids),np.arange(len(pids)))and np.array_equal(canonical_order(query_pids),np.arange(len(query_pids)))
 assert len(query)==len(query_pids)and not set(pids)&set(query_pids)and metadata.draft_year.lt(outer_year).all()
 assert label_audit is not None and label_audit['outer_year']==outer_year and label_audit['max_actual_label_season']<=outer_year-1 and label_audit['all_labels_finite_observed']and not label_audit['missing_training_labels_zero_filled']
 assert label_audit['training_pid_hash']==digest(pids)and label_audit['label_value_hash']==array_hash(label_values)and label_audit['target_hash']==array_hash(target)
 assert np.array_equal(gaussian_target(label_values,metadata.draft_year),target)
 assert len(X)>=40 and not np.isinf(np.asarray(X)).any()and not np.isinf(np.asarray(query)).any()
 fold=assignments(pids);assert set(fold)=={0,1,2};source=(array_hash(X),array_hash(query),array_hash(target),array_hash(label_values));inner=[];oof={s:{name:np.full(len(X),np.nan)for name in FAMILIES}for s in seeds}
 for f in range(3):
  train=np.flatnonzero(fold!=f);held=np.flatnonzero(fold==f);assert len(train)>=20 and len(held)>=1
  train_pids=[pids[i]for i in train];held_pids=[pids[i]for i in held];xi=X.iloc[train].reset_index(drop=True);xh=X.iloc[held].reset_index(drop=True)
  # Recompute cohort target using only inner training label values. No held-label normalization.
  yi=gaussian_target(np.asarray(label_values)[train],metadata.draft_year.to_numpy()[train]);stage=f'outer{outer_year}_inner{f}'
  selected,selector,ridge=_stage(backend,xi,yi,train_pids,stage);records=[]
  ridge_raw,ridge_design=backend.predict(ridge,xh);ridge_pred,ridge_ties=canonicalize(xh,ridge_raw,held_pids)
  for seed in seeds:
   for name in FAMILIES:
    fields=selected if name=='tabicl'else list(X)
    if name=='ridge':raw,design,pred,ties=ridge_raw,ridge_design,ridge_pred,ridge_ties
    else:
     model=backend.fit(name,xi[fields],yi,seed,train_pids,stage);raw,design=backend.predict(model,xh[fields]);pred,ties=canonicalize(xh[fields],raw,held_pids)
    assert np.isnan(oof[seed][name][held]).all();oof[seed][name][held]=pred
    records.append({'family':name,'seed':seed,'held_pids':held_pids,'raw_predictions':np.asarray(raw).tolist(),'canonical_predictions':pred.tolist(),'model_audit':design,'tie_audit':ties,'shared_Ridge_fit':name=='ridge'})
  inner.append({'fold':f,'train_pids':train_pids,'held_pids':held_pids,'training_matrix_hash':array_hash(xi),'held_matrix_hash':array_hash(xh),'training_target_hash':array_hash(yi),'training_label_value_hash':array_hash(np.asarray(label_values)[train]),'selector':selector,'selected_TabICL_columns':selected,'records':records})
 for seed in seeds:
  assert all(np.isfinite(v).all()for v in oof[seed].values())
 selected,selector,ridge=_stage(backend,X,target,pids,f'outer{outer_year}_full');ridge_raw,ridge_design=backend.predict(ridge,query);ridge_pred,ridge_ties=canonicalize(query,ridge_raw,query_pids);results=[]
 coverage=np.isfinite(np.asarray(query)).mean(axis=1);thin=coverage<np.median(coverage)
 for seed in seeds:
  members={};member_audits={}
  for name in FAMILIES:
   fields=selected if name=='tabicl'else list(X)
   if name=='ridge':raw,design,pred,ties=ridge_raw,ridge_design,ridge_pred,ridge_ties
   else:
    model=backend.fit(name,X[fields],target,seed,pids,f'outer{outer_year}_full');raw,design=backend.predict(model,query[fields]);pred,ties=canonicalize(query[fields],raw,query_pids)
   members[name]=pred;member_audits[name]={'raw_predictions':np.asarray(raw).tolist(),'canonical_predictions':pred.tolist(),'model_audit':design,'tie_audit':ties}
  weights,meta=nonnegative_meta(oof[seed],target)
  residual_target=rank_percentile(target)-rank_percentile(oof[seed]['tabicl']);residual=backend.fit('residual_q25',X,residual_target,seed,pids,f'outer{outer_year}_residual');raw,design=backend.predict(residual,query);delta,ties=canonicalize(query,raw,query_pids)
  corrected=rank_percentile(members['tabicl'])+delta;ranked=np.column_stack([rank_percentile(members[name])for name in FAMILIES]);corrected_rank=rank_percentile(corrected)
  predictions={'equal_three_direct':np.sum([np.rint(ranked[:,i]*(2*len(query))).astype(np.int64)for i in range(3)],axis=0)/(6*len(query)),
               'fixed_coverage_direct':np.where(thin,ranked[:,0],.25*ranked[:,1]+.75*ranked[:,2]),
               'fixed_coverage_residual':np.where(thin,corrected_rank,.25*ranked[:,1]+.75*ranked[:,2]),
               'learned_global_nonnegative_meta':ranked@weights}
  for prediction in predictions.values():validate_equal_groups(query,prediction)
  results.append({'seed':seed,'outer_query_pids':query_pids,'members':member_audits,'OOF_predictions':{name:value.tolist()for name,value in oof[seed].items()},'meta':meta,'residual':{'training_target_hash':array_hash(residual_target),'training_target':residual_target.tolist(),'OOF_TabICL_hash':array_hash(oof[seed]['tabicl']),'raw_query_correction':np.asarray(raw).tolist(),'canonical_query_correction':delta.tolist(),'corrected_query_prediction':corrected.tolist(),'model_audit':design,'tie_audit':ties,'excluded_from_learned_meta':True},'architectures':{name:value.tolist()for name,value in predictions.items()}})
 assert source==(array_hash(X),array_hash(query),array_hash(target),array_hash(label_values))
 return {'outer_year':outer_year,'columns':list(X),'training_pids':pids,'inner_fold_by_pid':dict(zip(pids,fold.tolist())),'label_audit':label_audit,'inner_stages':inner,'full_selector':selector,'full_TabICL_columns':selected,'full_training_target_hash':array_hash(target),'raw_panel_query_coverage':coverage.tolist(),'query_thin_mask':thin.tolist(),'seed_results':results,'query_outcomes_accessed':False,'OOF_residual_used_for_meta':False}
