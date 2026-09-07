"""Synthetic software fixtures only; no actual model fits or historical scores."""
import collections,copy,unittest
import numpy as np
import pandas as pd
import stack_core as C
from model_backend import ridge_statistics,ridge_transform

class FakeBackend:
 def __init__(self):self.counts=collections.Counter();self.calls=[]
 def select(self,X,y,pids,stage):
  self.counts['selector']+=1;importance=np.abs(np.nan_to_num(np.asarray(X)).T@np.asarray(y));columns=[c for _,c in sorted(zip(importance,X),reverse=True)[:2]]
  return columns,{'training_pid_hash':C.digest(pids),'training_target_hash':C.array_hash(y),'selected_columns':columns,'training_matrix_hash':C.array_hash(X)}
 def fit(self,family,X,y,seed,pids,stage):
  self.counts[family]+=1;coef=np.nan_to_num(np.asarray(X)).T@np.asarray(y)/len(y);record={'family':family,'seed':seed,'fields':list(X),'coef':coef,'mean':float(np.mean(y)),'training_pid_hash':C.digest(pids),'training_target_hash':C.array_hash(y),'stage':stage};self.calls.append(record);return record
 def predict(self,model,X):
  assert list(X)==model['fields'];factor={'ridge':.8,'tabicl':1.2,'xgb_q25':1.,'residual_q25':.3}[model['family']]
  raw=np.nan_to_num(np.asarray(X))@model['coef']*factor+model['mean']+model['seed']*.00001
  return raw,{k:v for k,v in model.items()if k!='coef'}

def fixture():
 rng=np.random.default_rng(7813);pids=[f'P_test_{i}'for i in range(90)];order=C.canonical_order(pids);pids=[pids[i]for i in order];cohorts=np.tile([2007,2008,2009],30)[order];x=rng.normal(size=(90,5))[order];x[::7,1]=np.nan;values=(2*np.nan_to_num(x[:,0])+rng.normal(size=90));target=C.gaussian_target(values,cohorts)
 queries=['Q1','Q2','Q3','Q4','Q5'];qorder=C.canonical_order(queries);queries=[queries[i]for i in qorder];query=np.vstack([np.ones(5)]*3+[np.zeros(5),np.full(5,np.nan)])[qorder]
 X=pd.DataFrame(x,columns=[f'x{i}'for i in range(5)]);q=pd.DataFrame(query,columns=X.columns);meta=pd.DataFrame({'pid':pids,'draft_year':cohorts});audit={'outer_year':2012,'max_actual_label_season':2011,'all_labels_finite_observed':True,'missing_training_labels_zero_filled':False,'training_pid_hash':C.digest(pids),'label_value_hash':C.array_hash(values),'target_hash':C.array_hash(target),'source_fact_hash':'fixture'}
 return X,q,meta,queries,values,target,audit

class OOFSafety(unittest.TestCase):
 def test_counts_partition_reuse_and_meta(self):
  X,q,m,p,v,y,a=fixture();backend=FakeBackend();r=C.run_outer(X,q,m,p,v,y,2012,backend,label_audit=a)
  self.assertEqual(dict(backend.counts),{'selector':4,'ridge':4,'tabicl':12,'xgb_q25':12,'residual_q25':3})
  held=[]
  for stage in r['inner_stages']:
   self.assertFalse(set(stage['train_pids'])&set(stage['held_pids']));held+=stage['held_pids']
   for item in stage['records']:self.assertEqual(item['model_audit']['training_pid_hash'],C.digest(stage['train_pids']))
  self.assertCountEqual(held,m.pid.tolist())
  for e in r['seed_results']:
   self.assertEqual(e['meta']['family_order'],C.FAMILIES);self.assertFalse(e['meta']['residual_member_included']);self.assertAlmostEqual(sum(e['meta']['weights']),1);self.assertTrue(all(w>=0 for w in e['meta']['weights']))
   expected=C.rank_percentile(y)-C.rank_percentile(e['OOF_predictions']['tabicl']);np.testing.assert_array_equal(expected,e['residual']['training_target'])
   for prediction in e['architectures'].values():C.validate_equal_groups(q,prediction)
 def test_held_label_change_cannot_change_its_inner_fit(self):
  X,q,m,p,v,y,a=fixture();r=C.run_outer(X,q,m,p,v,y,2012,FakeBackend(),label_audit=a)
  mutated=v.copy();mutated[C.assignments(m.pid)==0]=np.linspace(-80,80,np.sum(C.assignments(m.pid)==0));newy=C.gaussian_target(mutated,m.draft_year);newaudit={**a,'label_value_hash':C.array_hash(mutated),'target_hash':C.array_hash(newy)}
  changed=C.run_outer(X,q,m,p,mutated,newy,2012,FakeBackend(),label_audit=newaudit)
  self.assertEqual(r['inner_stages'][0],changed['inner_stages'][0])
 def test_future_or_unknown_labels_rejected(self):
  X,q,m,p,v,y,a=fixture()
  for update in [{'max_actual_label_season':2012},{'all_labels_finite_observed':False},{'missing_training_labels_zero_filled':True}]:
   with self.assertRaises(AssertionError):C.run_outer(X,q,m,p,v,y,2012,FakeBackend(),label_audit={**a,**update})
  bad=v.copy();bad[0]=np.nan
  with self.assertRaises(AssertionError):C.gaussian_target(bad,m.draft_year)
 def test_Ridge_original_train_mean_sample_std(self):
  X=pd.DataFrame({'a':[0.,2.,np.nan,4.],'b':[np.nan]*4,'c':[7.]*4});mean,std=ridge_statistics(X);before=(mean.copy(),std.copy());query=pd.DataFrame({'a':[1000000.,np.nan],'b':[4.,np.nan],'c':[9.,7.]});z=ridge_transform(query,mean,std)
  self.assertEqual(mean.a,2.);self.assertEqual(std.a,2.);self.assertEqual(z.iloc[0].a,499999.);self.assertEqual(z.iloc[1].a,0.);self.assertEqual(z.iloc[0].b,0.);self.assertEqual(z.iloc[0].c,2.);pd.testing.assert_series_equal(mean,before[0]);pd.testing.assert_series_equal(std,before[1])
 def test_known_zero_negative_and_duplicate_ties(self):
  value=np.array([-3.,0.,0.,7.]);target=C.gaussian_target(value,np.ones(4));self.assertTrue(target[0]<target[1]==target[2]<target[3]);self.assertEqual(len(value),len(target))
  for n in [3,5]:
   frame=pd.DataFrame({'x':[1.]*n+[2.]});score=np.array([.0015]*n+[.8]);before=score.tobytes();C.validate_equal_groups(frame,score);self.assertEqual(before,score.tobytes())
 def test_hash_is_H_encoding(self):
  import hashlib,json
  a=np.array([[1.,np.nan],[-0.,2.]]);m=np.isnan(a);expected=hashlib.sha256(json.dumps(list(a.shape),sort_keys=True,separators=(',',':')).encode()+m.tobytes()+np.where(m,0.,np.where(a==0,0.,a)).tobytes()).hexdigest();self.assertEqual(C.array_hash(a),expected)
 def test_query_truth_not_in_api_and_query_PID_rejected(self):
  import inspect
  self.assertNotIn('query_labels',inspect.signature(C.run_outer).parameters)
  X,q,m,p,v,y,a=fixture();p[0]=m.pid.iloc[0]
  with self.assertRaises(AssertionError):C.run_outer(X,q,m,p,v,y,2012,FakeBackend(),label_audit=a)

if __name__=='__main__':unittest.main()
