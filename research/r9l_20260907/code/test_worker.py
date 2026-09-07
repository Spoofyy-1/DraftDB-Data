import collections,hashlib,inspect,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import stack_core as C
import worker as W
ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'protocol.json').read_text())
class FakeBackend:
 def __init__(self):self.counts=collections.Counter();self.calls=[]
 def fit_predict(self,family,X,y,q,seed,pids):
  self.counts[family]+=1;self.calls.append((family,seed,list(X),C.array_hash(y),list(pids)))
  z=np.nan_to_num(np.asarray(q)[:,0])+np.arange(len(q))*.1+seed*.001
  return z,{'family':family,'seed':seed,'training_target_hash':C.array_hash(y),'training_matrix_hash':C.array_hash(X)}
def inputs():
 pids=[f't{i}'for i in range(45)];order=C.canonical_order(pids);pids=[pids[i]for i in order];years=np.repeat([2008,2009,2010],15)[order];values=np.arange(45,dtype=float)[order]-10;y=C.gaussian_target(values,years)
 X=np.tile(np.arange(44,dtype=float),(45,1));X[:,0]=np.arange(45)[order];X[::7,2]=np.nan
 qp=[f'q{i}'for i in range(8)];order=C.canonical_order(qp);qp=[qp[i]for i in order];query=np.tile(np.arange(44,dtype=float),(8,1));query[:3,0]=0;query[3:,0]=1;query=query[order];query[:,2]=np.nan
 return pids,years,values,y,X,qp,query
def bundle(directory):
 pids,years,values,y,X,qp,query=inputs();np.savez(directory/'training.npz',X=X,pid=np.array(pids),draft_year=years,label_value=values,y=y,prefix_length=np.ones(45,dtype=int));np.savez(directory/'inference.npz',X=query,pid=np.array(qp))
 d={'outer_year':2012,'task_id':'base44_y2012','panel_id':'base44','policy_id':'h_s2008_gap1_all_h1','columns':P['original_H44_columns'],'protocol_sha256':W.sha(ROOT/'protocol.json'),'files':{x:{'sha256':W.sha(directory/x)}for x in ['training.npz','inference.npz']},'label_audit':{'outer_year':2012,'max_actual_label_season':2011,'all_labels_finite_observed':True,'missing_training_labels_zero_filled':False,'training_pid_hash':C.digest(pids),'label_value_hash':C.array_hash(values),'target_hash':C.array_hash(y),'source_fact_hash':'fixture_observed_only'}}
 (directory/'manifest.json').write_text(json.dumps(d));return d
class Tests(unittest.TestCase):
 def test_38_fixed_recipes_and_exact_J_rank_arithmetic(self):
  assert len(P['architectures'])==38
  query=np.zeros((8,44));query[3:]=1
  vectors={'tabicl':[.0015]*3+[.2]*5,'catboost':[.4]*3+[.1]*5,**{f'ridge_a{a}':[.17]*3+[.9]*5 for a in [30,300,3000]}}
  seen=set()
  for r in P['architectures']:
   key=json.dumps(r['members'],sort_keys=True);self.assertNotIn(key,seen);seen.add(key)
   z=C.fixed_blend(vectors,r,query);expected=sum(C.doubled_ranks(vectors[m['family']])*m['units']*5 for m in r['members'])/(120*8)
   np.testing.assert_array_equal(z,expected);C.validate_equal_groups(query,z)
  target=next(r for r in P['architectures']if r['members']==[{'family':'tabicl','units':6},{'family':'ridge_a300','units':6}]);self.assertEqual(len(target['members']),2)
 def test_nine_fits_original_order_shared_Ridge_and_no_truth(self):
  p,years,values,y,X,qp,q=inputs();back=FakeBackend();result=C.run_panel(pd.DataFrame(X,columns=P['original_H44_columns']),pd.DataFrame(q,columns=P['original_H44_columns']),p,qp,y,back,P)
  self.assertEqual(dict(back.counts),{'ridge_a30':1,'ridge_a300':1,'ridge_a3000':1,'tabicl':3,'catboost':3});self.assertEqual(len(back.calls),9)
  self.assertTrue(all(c[2]==P['original_H44_columns']and c[3]==C.array_hash(y)and c[4]==p for c in back.calls))
  self.assertNotIn('query_truth',inspect.signature(C.run_panel).parameters);self.assertFalse(result['query_outcomes_accessed'])
  for s in result['seed_results']:
   for z in s['architectures'].values():C.validate_equal_groups(q,z)
  for z in result['fixed_three_seed_family_rank_average']['architectures'].values():C.validate_equal_groups(q,z)
 def test_future_cutoff_unknown_label_rejected(self):
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);m=bundle(d);W.load(d)
   for change in [{'max_actual_label_season':2012},{'all_labels_finite_observed':False},{'missing_training_labels_zero_filled':True}]:
    bad={**m,'label_audit':{**m['label_audit'],**change}};(d/'manifest.json').write_text(json.dumps(bad))
    with self.assertRaises(AssertionError):W.load(d)
 def test_extra_file_label_tamper_order_and_panel_rejected(self):
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);m=bundle(d);(d/'query_truth.csv').write_text('forbidden')
   with self.assertRaises(AssertionError):W.load(d)
   (d/'query_truth.csv').unlink()
   for bad in [{**m,'columns':list(reversed(m['columns']))},{**m,'policy_id':'h_s2000_gap1_drafted_h2'},{**m,'files':{**m['files'],'training.npz':{'sha256':'0'*64}}}]:
    (d/'manifest.json').write_text(json.dumps(bad))
    with self.assertRaises(AssertionError):W.load(d)
 def test_atomic_immutable_interruption_and_conflict(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'out.json'
   with patch.object(W.os,'link',side_effect=InterruptedError):
    with self.assertRaises(InterruptedError):W.save_new(p,{'ok':1})
   self.assertFalse(p.exists());self.assertFalse(list(p.parent.iterdir()));W.save_new(p,{'ok':1});W.save_new(p,{'ok':1})
   with self.assertRaises(AssertionError):W.save_new(p,{'ok':2})
   self.assertEqual(json.loads(p.read_text()),{'ok':1})
 def test_nan_signed_zero_hash_and_distinct_vectors(self):
  a=np.array([[np.nan,-0.],[1.,2.]])
  self.assertEqual(C.array_hash(a),C.array_hash([[np.nan,0.],[1.,2.]]));self.assertNotEqual(C.array_hash(a),C.array_hash([[np.nan,0.],[1.,2.00000001]]))
  z,_=C.canonicalize([[1.],[1.00000001]],[.1,.2],['p1','p2']);np.testing.assert_array_equal(z,[.1,.2])
if __name__=='__main__':unittest.main()
