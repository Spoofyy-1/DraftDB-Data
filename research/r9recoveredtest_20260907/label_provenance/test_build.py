"""Small adversarial fixtures for the fixed recovered target; no real outcomes."""
from pathlib import Path
import json,unittest
import numpy as np
import pandas as pd
import build as B
K=B.load(Path('/home/ubuntu/nba/handoff/r9k_labelprep/build.py'))
class Tests(unittest.TestCase):
 def data(self):
  p=pd.DataFrame({'pid':['old','new','zero','gap','prestart'],'draft_year':[2007,2019,2017,2017,2006],'was_drafted':[1,1,0,1,1]})
  f=pd.DataFrame([['old',2007,i,2007+i,float(i)] for i in range(1,6)]+[['new',2019,1,2020,999.],['zero',2017,1,2018,0.],['gap',2017,2,2019,77.],['prestart',2006,1,2007,88.]],columns=B.FACTS)
  return p,f
 def test_query_and_future_season_excluded(self):
  p,f=self.data();a,u=B.payload(K,p,f,2019)
  self.assertEqual(set(a['pid']),{'old','zero'});self.assertLessEqual(u.season_end.max(),2018)
 def test_unknown_not_zero_known_zero_kept(self):
  p,f=self.data();a,_=B.payload(K,p,f,2019)
  self.assertNotIn('gap',a['pid']);self.assertEqual(a['label_value'][a['pid']=='zero'].tolist(),[0.])
 def test_discount_and_season_max(self):
  p,f=self.data();a,_=B.payload(K,p,f,2019)
  self.assertEqual(a['label_value'][a['pid']=='old'].tolist(),[sum(.85**(i-1)*i for i in range(1,6))])
  self.assertEqual(a['season_end_max'][a['pid']=='old'].tolist(),[2012])
 def test_no_guessing_missing_future_calendar(self):
  p,f=self.data();a,_=B.payload(K,p,f,2023);b,_=B.payload(K,p,f,2025)
  for k in a:self.assertTrue(np.array_equal(a[k],b[k]))
  self.assertLessEqual(a['season_end_max'].max(),2020)
 def test_reordering_and_duplicate(self):
  p,f=self.data();a,_=B.payload(K,p,f,2019);b,_=B.payload(K,p.iloc[::-1],f.iloc[::-1],2019)
  for k in a:self.assertTrue(np.array_equal(a[k],b[k]))
  with self.assertRaises(AssertionError):B.payload(K,p,pd.concat([f,f.iloc[:1]]),2019)
 def test_clip_and_per_cohort_target(self):
  a=K.gaussian_target([41.,42.,0.,-4.],[2007]*4);self.assertEqual(a[0],a[1]);self.assertGreater(a[2],a[3])
  self.assertTrue(np.array_equal(K.gaussian_target([1.,2.,999.],[2007,2007,2019])[:2],K.gaussian_target([1.,2.],[2007,2007])))
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 Path(__file__).with_name('tests.json').write_text(json.dumps({'passed':r.wasSuccessful(),'tests':r.testsRun,'errors':len(r.errors),'failures':len(r.failures),'fixture_data_exported':False,'model_runs':0},indent=2)+'\n');raise SystemExit(0 if r.wasSuccessful() else 1)
