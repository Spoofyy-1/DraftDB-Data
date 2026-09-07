"""Synthetic adversarial unit fixtures only; no fixture enters exported data."""
from pathlib import Path
import importlib.util,unittest,json
import pandas as pd
import numpy as np
import build as B
ROOT=Path(__file__).resolve().parent
class NoFloat:
 def __float__(self):raise AssertionError('Future value was inspected')
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  candidates=[ROOT.parent/'calendar_broker/broker.py',Path('/home/ubuntu/nba/handoff/calendar_broker_prototype/broker.py')]
  cls.broker=B.load_broker(next(p for p in candidates if p.exists()))
 def data(self):
  pool=pd.DataFrame([{'pid':'a','draft_year':2007,'was_drafted':1},{'pid':'z','draft_year':2007,'was_drafted':0},{'pid':'future','draft_year':2013,'was_drafted':1}])
  ids=pd.DataFrame([{'pid':'a','draft_year':2007,'player_name':'Alpha'},{'pid':'z','draft_year':2007,'player_name':'Zero'},{'pid':'future','draft_year':2013,'player_name':'Alpha'}])
  source=pd.DataFrame([{'player_name':'Alpha','player_id':'alpha01','season':2008,'war_total':3.},{'player_name':'Alpha','player_id':'alpha01','season':2009,'war_total':4.},{'player_name':'Zero','player_id':'zero01','season':2010,'war_total':0.},{'player_name':'Alpha','player_id':'collision','season':2013,'war_total':NoFloat()}])
  raw={'a':{'pid':'a','draft_year':'2007','y_s1_war':'3','y_s2_war':'4','y_s3_war':NoFloat()},'z':{'pid':'z','draft_year':'2007','y_s1_war':'0'},'future':{'pid':'future','draft_year':'2013','y_s1_war':NoFloat()}}
  return pool,ids,source,raw
 def test_future_values_and_identity_ignored(self):
  pool,ids,source,raw=self.data();one,_=B.verify_cutoff(self.broker,source,ids,raw,pool,2012)
  changed=source.copy();changed.loc[changed.season>2011,'player_name']='Zero';changed.loc[changed.season>2011,'player_id']='new_collision'
  ids.loc[ids.draft_year>=2012,'player_name']='Zero';two,_=B.verify_cutoff(self.broker,changed,ids,raw,pool,2012)
  pd.testing.assert_frame_equal(one,two);self.assertEqual(set(one.pid),{'a','z'})
 def test_future_membership_and_external_identity_ignored(self):
  pool,ids,source,raw=self.data();one,_=B.verify_cutoff(self.broker,source,ids,raw,pool,2012)
  pool=pd.concat([pool,pd.DataFrame([{'pid':'future2','draft_year':2014,'was_drafted':1}])],ignore_index=True)
  ids=pd.concat([ids,pd.DataFrame([{'pid':'future2','draft_year':2014,'player_name':'Alpha'},{'pid':'outside_fixed_pool','draft_year':2007,'player_name':'Alpha'}])],ignore_index=True)
  two,_=B.verify_cutoff(self.broker,source,ids,raw,pool,2012);pd.testing.assert_frame_equal(one,two)
 def test_eligible_mismatch_rejects_entire_identity(self):
  pool,ids,source,raw=self.data();raw['a']['y_s2_war']='55';facts,audit=B.verify_cutoff(self.broker,source,ids,raw,pool,2012)
  self.assertEqual(set(facts.pid),{'z'});self.assertEqual(audit['label_verification']['eligible_label_mismatch_players'],1)
 def test_prefix_gap_unknown_and_known_zero(self):
  pool=pd.DataFrame({'pid':['a','b','z'],'draft_year':[2007]*3,'was_drafted':[1,1,0]})
  facts=pd.DataFrame([['a',2007,1,2008,2.],['a',2007,3,2010,100.],['b',2007,2,2009,99.],['z',2007,1,2008,0.]],columns=B.FACT_COLUMNS)
  a,used=B.prefix_payload(pool,facts,2012);self.assertEqual(set(a['pid']),{'a','z'});self.assertEqual(a['prefix_length'].tolist(),[1,1]);self.assertEqual(set(used.ordinal),{1})
  self.assertEqual(a['label_value'][a['pid']=='z'].tolist(),[0.]);self.assertEqual(a['label_value'][a['pid']=='a'].tolist(),[2.])
 def test_discount_actual_dates_and_future_fact(self):
  pool=pd.DataFrame({'pid':['a'],'draft_year':[2007],'was_drafted':[1]})
  facts=pd.DataFrame([['a',2007,1,2009,4.],['a',2007,2,2011,2.],['a',2007,3,2014,888.]],columns=B.FACT_COLUMNS)
  a,used=B.prefix_payload(pool,facts,2012);self.assertEqual(a['prefix_length'].tolist(),[2]);self.assertEqual(a['label_value'].tolist(),[4.+.85*2.]);self.assertEqual(used.season_end.tolist(),[2009,2011])
 def test_reordering_invariant_and_duplicate_rejected(self):
  pool,ids,source,raw=self.data();facts,_=B.verify_cutoff(self.broker,source,ids,raw,pool,2012)
  a,_=B.prefix_payload(pool,facts,2012);b,_=B.prefix_payload(pool.iloc[::-1],facts.iloc[::-1],2012)
  for k in a:self.assertTrue(np.array_equal(a[k],b[k]))
  with self.assertRaises(AssertionError):B.prefix_payload(pool,pd.concat([facts,facts.iloc[[0]]]),2012)
 def test_target_clip_ties_and_inner_cohort_only(self):
  y=B.gaussian_target([41.,42.,0.,-4.],[2007]*4);self.assertEqual(y[0],y[1]);self.assertGreater(y[2],y[3])
  # Holding values fixed while removing a training peer requires a fresh rank.
  self.assertFalse(np.array_equal(y[:3],B.gaussian_target([41.,42.,0.],[2007]*3)))
  self.assertTrue(np.array_equal(B.gaussian_target([1.,2.,999.],[2007,2007,2008])[:2],B.gaussian_target([1.,2.],[2007,2007])))
 def test_admission_guards(self):
  ids=np.asarray([f'a{i}'for i in range(40)]);a={'pid':ids,'draft_year':np.asarray([2007]*40),'label_value':np.arange(40.),'prefix_length':np.ones(40,dtype=int)};a['y']=B.gaussian_target(a['label_value'],a['draft_year'])
  self.assertEqual(B.validate_admission(a,2012,['query']),{'2007':40})
  with self.assertRaises(AssertionError):B.validate_admission(a,2012,[ids[0]])
  short={k:v[:39] for k,v in a.items()};short['y']=B.gaussian_target(short['label_value'],short['draft_year'])
  with self.assertRaises(ValueError):B.validate_admission(short,2012,['query'])
  small={k:v.copy() for k,v in a.items()};small['draft_year'][0]=2006;small['y']=B.gaussian_target(small['label_value'],small['draft_year'])
  with self.assertRaises(ValueError):B.validate_admission(small,2012,['query'])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);r=unittest.TextTestRunner(verbosity=2).run(suite)
 (ROOT/'tests.json').write_text(json.dumps({'tests':r.testsRun,'errors':len(r.errors),'failures':len(r.failures),'passed':r.wasSuccessful(),'fixture_data_exported':False,'models_run':0},indent=2)+'\n');raise SystemExit(0 if r.wasSuccessful() else 1)
