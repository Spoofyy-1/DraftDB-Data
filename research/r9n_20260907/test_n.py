"""Finite outcome-free fixtures; no predictive model fit or actual dataset access."""
from pathlib import Path
import copy,hashlib,json,sys,unittest
import numpy as np
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'code'))
import stack_core as C,preprocessing as P,stack_predictions as S
PROTOCOL=json.loads((R/'protocol.json'if(R/'protocol.json').exists()else R/'code/protocol.json').read_text());G='f50_game_team'

def fixture():
 pids=[f't{i}'for i in range(45)];pids=[pids[i]for i in C.canonical_order(pids)];qp=[f'q{i}'for i in range(8)];qp=[qp[i]for i in C.canonical_order(qp)];sources={};jobs=[]
 def member(family,seed,offset,q):
  factor=-1 if family in ['catboost','ridge_a30']else 1;s=0 if family.startswith('ridge_')else seed
  raw=factor*(np.arange(8)+np.sin(np.arange(8)+s+offset)*.1);pred,ties=C.canonicalize(q,raw,qp)
  return {'seed':seed,'raw_predictions':raw.tolist(),'canonical_predictions':pred.tolist(),'tie_audit':ties}
 for year in PROTOCOL['outer_years']:
  for panel in PROTOCOL['source_panels']:
   q=np.zeros((8,panel['width']));q[3:,0]=1;q[:,2]=np.nan
   r={'panel_id':panel['id'],'outer_year':year,'query_pids':qp,'training_pids':pids,'target_hash':'fixture_target','label_audit':{'outer_year':year,'fixture_observed':True},'policy_id':PROTOCOL['policy_id'],'seed_results':[]}
   for seed in PROTOCOL['seeds']:r['seed_results'].append({'seed':seed,'members':{f:member(f,seed,panel['width'],q)for f in ['tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost']}})
   sources[(panel['id'],year)]=r
  for i,profile in enumerate(PROTOCOL['profiles']):
   if profile['id']==PROTOCOL['baseline_profile_id']:continue
   base=sources[(G,year)];q=np.zeros((8,127));q[3:,0]=1;q[:,2]=np.nan
   jobs.append({k:v for k,v in base.items()if k!='seed_results'}|{'task_id':f"{profile['id']}_y{year}",'profile_id':profile['id'],'members':[member('tabicl',s,i,q)for s in PROTOCOL['seeds']]})
 return sources,jobs
class FakeGenerator:
 n_features_in_=2
 ensemble_configs_={'none':[{'fixture':True}]}
 feature_shuffles_=np.array([[0,1]])
 def __init__(self,bad=False):self.bad=bad
 def transform(self,q,mode):return {'none':(np.array([[1.,np.inf if self.bad else 2.]]),np.array([0.]))}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.sources,cls.jobs=fixture();cls.rows=S.assemble(cls.sources,cls.jobs,PROTOCOL['stack_recipes'],PROTOCOL)
 def test_declared23_profiles198fits_and1723_unique_recipes(self):
  self.assertEqual(len(PROTOCOL['profiles']),23);self.assertEqual(len(self.jobs),66);self.assertEqual(len(PROTOCOL['stack_recipes']),1723)
  self.assertEqual(len({json.dumps(r['members'],sort_keys=True)for r in PROTOCOL['stack_recipes']}),1723);self.assertEqual(sum(len(r['design_aliases'])for r in PROTOCOL['stack_recipes']),3496)
  self.assertEqual(len(self.rows),20676);self.assertTrue(all(np.isfinite(r['prediction']).all()for r in self.rows))
 def test_all_aliases_reconstruct_identical_positive_member_views(self):
  base={r['id']:r for r in PROTOCOL['same_panel_architectures']}
  for recipe in PROTOCOL['stack_recipes']:
   for alias in recipe['design_aliases']:
    expected=[]
    for m in base[alias['same_panel_recipe']]['members']:
     view=G if m['family']=='tabicl'else alias['C_panel']if m['family']=='catboost'else alias['R_panel'];expected.append({**m,'panel_id':view,'profile_id':alias['profile_id']if m['family']=='tabicl'else None})
    self.assertEqual(expected,recipe['members'])
 def test_same_seed_and_three_seed_integer_arithmetic(self):
  jobs={(r['profile_id'],r['outer_year']):r for r in self.jobs};recipes={r['id']:r for r in PROTOCOL['stack_recipes']}
  for row in self.rows:
   if row['year']!=2012 or row['seed']not in [101,'fixed_three_seed_family_rank_average']:continue
   numerator=np.zeros(8,dtype=np.int64)
   for m in recipes[row['architecture']]['members']:
    if m['family']=='tabicl'and m['profile_id']!=PROTOCOL['baseline_profile_id']:members=jobs[(m['profile_id'],2012)]['members']
    else:members=[s['members'][m['family']]for s in self.sources[(m['panel_id'],2012)]['seed_results']]
    if isinstance(row['seed'],int):v=next(x for x in members if x['seed']==row['seed'])['canonical_predictions']
    elif m['family'].startswith('ridge_'):v=members[0]['canonical_predictions']
    else:v=sum(C.doubled_ranks(x['canonical_predictions'])for x in members)/(6*8)
    numerator+=m['units']*C.doubled_ranks(v)
   np.testing.assert_array_equal(row['prediction'],numerator/(24*8))
 def test_nonfinite_and_unsupported_profiles_fail_closed(self):
  good=PROTOCOL['profiles'][0]
  for change in [{'outlier_threshold':float('nan')},{'outlier_threshold':float('inf')},{'outlier_threshold':-.5},{'norm_methods':'unsupported'},{'n_estimators':True},{'n_estimators':0}]:
   with self.assertRaises((AssertionError,ValueError)):P.parameters({**good,**change},0,PROTOCOL)
  with self.assertRaises(ValueError):P.fingerprint(FakeGenerator(True),np.zeros((1,2)))
  goodfp=P.fingerprint(FakeGenerator(),np.zeros((1,2)));self.assertEqual(goodfp['effective_estimators'],1)
 def test_complete_ninefold_seed_signature_not_count_only(self):
  base={f'{y}:{s}':{'profile_id':'p128','parameters':{'n_estimators':128},'effective_constructor':{'n_estimators':128,'norm_methods':'none','outlier_threshold':2},'seed':s,'generator':{'effective_estimators':100,'ensemble_hash':'ordered','transformed_views_hash':'finite','shapes':[100,45,127]},'training_pid_hash':'ordered_train','query_pid_hash':'ordered_query','target_hash':'frozen','columns':['a','b']}for y in [2012,2013,2014]for s in [0,101,202]}
  alias=copy.deepcopy(base)
  for d in alias.values():d['profile_id']='p256';d['parameters']['n_estimators']=256;d['effective_constructor']['n_estimators']=256
  self.assertEqual(P.equality_signature(base),P.equality_signature(alias))
  for field,value in [('training_pid_hash','changed'),('target_hash','changed'),('columns',['b','a'])]:
   bad=copy.deepcopy(alias);bad['2014:202'][field]=value;self.assertNotEqual(P.equality_signature(base),P.equality_signature(bad))
  bad=copy.deepcopy(alias);bad['2014:202']['generator']['ensemble_hash']='different_even_same_count';self.assertNotEqual(P.equality_signature(base),P.equality_signature(bad))
 def test_no_Tab_profiles_dedup_and_no_false_multifamily(self):
  recipes={r['id']:r for r in PROTOCOL['stack_recipes']};self.assertEqual(sum(all(m['family']!='tabicl'for m in r['members'])for r in recipes.values()),44)
  for row in self.rows:
   multi=len({m['family'].split('_a')[0]for m in recipes[row['architecture']]['members']})>=2;self.assertEqual(row['multi_family_stack'],multi)
 def test_source_pid_target_mismatch_and_bad_weights_rejected(self):
  for field,value in [('target_hash','changed'),('query_pids',['bad']*8)]:
   bad=copy.deepcopy(self.jobs);bad[0][field]=value
   with self.assertRaises(AssertionError):S.assemble(self.sources,bad,PROTOCOL['stack_recipes'],PROTOCOL)
  r=copy.deepcopy(PROTOCOL['stack_recipes'][0]);r['members'][0]['units']+=1
  with self.assertRaises(AssertionError):S.assemble(self.sources,self.jobs,[r],PROTOCOL)
 def test_reference_recipes_present_at_frozen_baseline(self):
  b=PROTOCOL['baseline_profile_id'];expected=[[{'family':'tabicl','units':4,'panel_id':G,'profile_id':b},{'family':'ridge_a30','units':4,'panel_id':G,'profile_id':None},{'family':'catboost','units':4,'panel_id':'base44','profile_id':None}],[{'family':'tabicl','units':9,'panel_id':G,'profile_id':b},{'family':'ridge_a30','units':3,'panel_id':G,'profile_id':None}]]
  for members in expected:self.assertEqual(sum(r['members']==members for r in PROTOCOL['stack_recipes']),1)
if __name__=='__main__':unittest.main()
