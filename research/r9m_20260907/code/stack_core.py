"""Fixed-family stack utilities; no query truth or scoring interface."""
import hashlib,json,math,collections
import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata

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

def doubled_ranks(value):
 a=np.asarray(value,dtype=float);assert a.ndim==1 and len(a)>0 and np.isfinite(a).all()
 return np.rint(2*rankdata(a,method='average')).astype(np.int64)
def fixed_blend(members,recipe,query):
 assert recipe['kind']=='fixed_rank_weights'and recipe['weight_total']==12
 units=[m['units']for m in recipe['members']];assert all(isinstance(x,int)and x>0 for x in units)and sum(units)==12
 numerator=np.sum([doubled_ranks(members[m['family']])*m['units']for m in recipe['members']],axis=0,dtype=np.int64)
 result=numerator/(24*len(query));validate_equal_groups(query,result);return result

def run_panel(X,query,pids,query_pids,target,backend,protocol):
 assert list(X)==list(query)and len(X)==len(pids)==len(target)and len(query)==len(query_pids)
 assert not set(X)&{'pid','draft_year','actual_pick','was_drafted','qid'}
 assert np.array_equal(canonical_order(pids),np.arange(len(pids)))and np.array_equal(canonical_order(query_pids),np.arange(len(query_pids)))and not set(pids)&set(query_pids)
 assert np.isfinite(target).all()and not np.isinf(np.asarray(X)).any()and not np.isinf(np.asarray(query)).any()
 snapshot=(array_hash(X),array_hash(query),array_hash(target));shared={};seeds=protocol['seeds'];assert seeds==[0,101,202]
 def member(family,seed):
  raw,audit=backend.fit_predict(family,X,target,query,seed,pids);pred,ties=canonicalize(query,raw,query_pids)
  return {'raw_predictions':np.asarray(raw).tolist(),'canonical_predictions':pred.tolist(),'model_audit':audit,'tie_audit':ties}
 for alpha in protocol['ridge']['alphas']:shared[f'ridge_a{alpha}']=member(f'ridge_a{alpha}',0)
 rows=[]
 for seed in seeds:
  members={'tabicl':member('tabicl',seed),**shared,'catboost':member('catboost',seed)}
  vectors={k:v['canonical_predictions']for k,v in members.items()};architectures={r['id']:fixed_blend(vectors,r,query).tolist()for r in protocol['architectures']}
  rows.append({'seed':seed,'members':members,'architectures':architectures})
 averaged={}
 for family in rows[0]['members']:
  if family.startswith('ridge_'):averaged[family]=np.asarray(shared[family]['canonical_predictions'])
  else:averaged[family]=np.sum([doubled_ranks(s['members'][family]['canonical_predictions'])for s in rows],axis=0,dtype=np.int64)/(6*len(query))
 architectures={r['id']:fixed_blend(averaged,r,query).tolist()for r in protocol['architectures']}
 assert snapshot==(array_hash(X),array_hash(query),array_hash(target))
 return {'columns':list(X),'training_pids':pids,'query_pids':query_pids,'training_matrix_hash':snapshot[0],'query_matrix_hash':snapshot[1],'target_hash':snapshot[2],'seed_results':rows,'fixed_three_seed_family_rank_average':{'members':{k:v.tolist()for k,v in averaged.items()},'architectures':architectures},'query_outcomes_accessed':False,'learned_weights':False,'selector_fits':0}
