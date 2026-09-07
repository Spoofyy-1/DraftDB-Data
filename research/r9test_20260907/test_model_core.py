"""Small non-model fixtures: cutoff/unknown labels, columns, ties and rank mean."""
import unittest,json,copy
from pathlib import Path
import numpy as np
import pandas as pd
import model_core as M
class ContractTests(unittest.TestCase):
 def setUp(self):
  self.r=json.loads((Path(__file__).parent/'recipe.json').read_text());f=self.r['physical_source_fields'];self.tr=pd.DataFrame({'pid':[f'p{i:03}'for i in range(45)],'draft_year':[2010]*45,'was_drafted':[1]*45,**{c:np.arange(45,dtype=float)for c in f}});self.q=pd.DataFrame({'pid':['query_a','query_b'],'draft_year':[2019]*2,**{c:[1.,2.]for c in f}});self.labels=pd.DataFrame([{'pid':f'p{i:03}','draft_year':2010,'ordinal':o,'season_end':2010+o,'war':float(i-20)}for i in range(45)for o in[1,2]])
 def build(self,tr=None,q=None,l=None):return M.build_payload(self.tr if tr is None else tr,self.q if q is None else q,self.labels if l is None else l,self.r,2019)
 def test_observed_target_order_and_zero(self):
  a=self.build();b=self.build(tr=self.tr.iloc[::-1],q=self.q.iloc[::-1],l=self.labels.iloc[::-1]);self.assertEqual(a[-1],b[-1]);self.assertTrue(np.array_equal(a[2],b[2]));self.assertIn('p020',a[3]);self.assertTrue((a[2]<0).any());self.assertEqual(a[-1]['source_fact_rows'],90)
 def test_missing_ordinal_excluded_not_zero(self):
  labels=self.labels[~((self.labels.pid=='p000')&(self.labels.ordinal==2))];a=self.build(l=labels);self.assertNotIn('p000',a[3]);self.assertEqual(a[-1]['training_rows'],44)
 def test_future_and_unknown_rejected(self):
  for field,value in [('season_end',2019),('war',np.nan)]:
   bad=self.labels.copy();bad.loc[0,field]=value
   with self.assertRaises(AssertionError):self.build(l=bad)
 def test_query_labels_and_pick_column_rejected(self):
  bad=self.labels.copy();bad.loc[0,'pid']='query_a'
  with self.assertRaises(AssertionError):self.build(l=bad)
  bad=self.q.copy();bad['actual_pick']=[1,2]
  with self.assertRaises(AssertionError):self.build(q=bad)
 def test_duplicate_or_bad_calendar_rejected(self):
  with self.assertRaises(AssertionError):self.build(l=pd.concat([self.labels,self.labels.iloc[[0]]]))
  bad=self.labels.copy();bad.loc[0,'season_end']=2009
  with self.assertRaises(AssertionError):self.build(l=bad)
 def test_exact_vector_ties_and_fixed_rank_average(self):
  x=pd.DataFrame({'x':[1.,1.,2.],'missing':[np.nan,np.nan,3.]});p,a=M.canonical_predictions(x,np.array([.1,.3,.8]),['a','b','c']);self.assertEqual(p[0],p[1]);self.assertEqual(p[2],.8);self.assertEqual(len(a['duplicate_groups']),1)
  z=M.fixed_rank_average([np.array([1.,1.,3.])]*3);self.assertTrue(np.array_equal(z,np.array([.5,.5,1.])))
if __name__=='__main__':unittest.main()
