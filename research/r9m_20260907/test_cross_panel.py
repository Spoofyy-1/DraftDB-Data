"""Finite fixture only: no real outcomes or model fits."""
from pathlib import Path
import copy,hashlib,json,sys,unittest
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'code'))
import stack_core as C
import cross_panel as X
P=json.loads((ROOT/'protocol.json'if(ROOT/'protocol.json').exists()else ROOT/'code/protocol.json').read_text())
class FixtureBackend:
 def fit_predict(self,family,A,y,Q,seed,pids):
  n=len(Q);factor=-1 if family in ['catboost','ridge_a30']else 1
  raw=factor*(np.asarray(Q)[:,0]+np.arange(n)*.01)+np.sin(np.arange(n)+seed)*.001
  return raw,{'input_columns':list(A),'training_pid_hash':C.digest(pids),'training_target_hash':C.array_hash(y)}
def fixture():
 pids=[f't{i}'for i in range(45)];pids=[pids[i]for i in C.canonical_order(pids)];qp=[f'q{i}'for i in range(8)];qp=[qp[i]for i in C.canonical_order(qp)];target=np.linspace(-1,1,45);records=[]
 for year in P['outer_years']:
  for panel in P['panels']:
   cols=panel['columns'];a=np.tile(np.arange(len(cols)),(45,1)).astype(float);q=np.tile(np.arange(len(cols)),(8,1)).astype(float);q[:3,0]=0;q[3:,0]=1;q[:,2]=np.nan
   if len(cols)>44:q[3:,44]=2
   r=C.run_panel(pd.DataFrame(a,columns=cols),pd.DataFrame(q,columns=cols),pids,qp,target,FixtureBackend(),P)
   r.update(task_id=f"{panel['id']}_y{year}",panel_id=panel['id'],policy_id=P['policy_id'],outer_year=year,query_outcome_labels_accessed=False,label_audit={'outer_year':year,'observed':True});records.append(r)
 return records
GATE={'passed':True,'reused_records':6,'new_control_fits':0,'source_records_unchanged':True,'L_frozen_sha256':P['L_frozen_sha256'],'source_record_hash_manifest_sha256':'fixture_only','source_completed_log_sha256':'fixture_only'}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.records=fixture();cls.result=X.assemble(cls.records,P,GATE)
 def test_all950_and11400_finite_without_new_fits(self):
  self.assertEqual(self.result['recipe_count'],950);self.assertEqual(self.result['prediction_records'],11400);self.assertEqual(self.result['additional_model_fits'],0)
  self.assertTrue(all(np.isfinite(r['prediction']).all()for r in self.result['cross_panel_prediction_records']))
  self.assertEqual(len({(r['architecture'],r['year'],str(r['seed']))for r in self.result['cross_panel_prediction_records']}),11400)
 def test_all1824_declared_design_aliases_exact_after_dedup(self):
  base={r['id']:r for r in P['architectures']};seen=set();aliases=0
  for recipe in P['cross_panel_stacks']['recipes']:
   key=json.dumps(recipe['members'],sort_keys=True);self.assertNotIn(key,seen);seen.add(key)
   for alias in recipe['design_aliases']:
    members=[]
    for m in base[alias['same_panel_recipe']]['members']:
     panel=alias['T_panel']if m['family']=='tabicl'else alias['C_panel']if m['family']=='catboost'else alias['R_panel'];members.append({**m,'panel_id':panel})
    self.assertEqual(recipe['members'],members);aliases+=1
  self.assertEqual(aliases,1824)
 def test_exact_manual_integer_rank_blend_and_seed_mean(self):
  records={(r['panel_id'],r['outer_year']):r for r in self.records};recipes={r['id']:r for r in P['cross_panel_stacks']['recipes']}
  # Every distinct recipe at one fold in both a same-seed and the three-seed mode.
  for row in self.result['cross_panel_prediction_records']:
   if row['year']!=2012 or row['seed']not in [101,'fixed_three_seed_family_rank_average']:continue
   recipe=recipes[row['architecture']];numerator=np.zeros(8,dtype=np.int64)
   for m in recipe['members']:
    r=records[(m['panel_id'],2012)];family=m['family']
    if isinstance(row['seed'],int):v=next(s for s in r['seed_results']if s['seed']==101)['members'][family]['canonical_predictions']
    elif family.startswith('ridge_'):v=r['seed_results'][0]['members'][family]['canonical_predictions']
    else:v=sum(C.doubled_ranks(s['members'][family]['canonical_predictions'])for s in r['seed_results'])/(6*8)
    numerator+=m['units']*C.doubled_ranks(v)
   np.testing.assert_array_equal(row['prediction'],numerator/(24*8))
 def test_only_distinct_model_families_count_as_stacks(self):
  recipes={r['id']:r for r in P['cross_panel_stacks']['recipes']}
  for row in self.result['cross_panel_prediction_records']:
   expected=len({m['family'].split('_a')[0]for m in recipes[row['architecture']]['members']})>=2
   self.assertEqual(row['multi_family_stack'],expected)
  self.assertTrue(any(not r['multi_family_stack']for r in self.result['cross_panel_prediction_records']))
 def test_control_gate_and_pid_target_tamper_fail_closed(self):
  with self.assertRaises(AssertionError):X.assemble(self.records,P,{**GATE,'passed':False})
  for field,value in [('query_pids',['wrong']*8),('target_hash','wrong')]:
   bad=copy.deepcopy(self.records);bad[-1][field]=value
   with self.assertRaises(AssertionError):X.record_map(bad,P)
  bad=copy.deepcopy(self.records);bad[-1]['seed_results'][0]['members']['tabicl']['canonical_predictions'][0]+=.001
  with self.assertRaises(AssertionError):X.record_map(bad,P)
 def test_four_model_files_and_two_control_schemas_byte_exact_L(self):
  for f,h in P['unchanged_L_model_files'].items():
   path=ROOT/f if(ROOT/f).exists()else ROOT/'code'/f
   self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),h)
  self.assertEqual([p['width']for p in P['panels']],[44,92,129,112,107,149,127,164]);self.assertFalse(any(c.startswith('vmb_')for p in P['panels']for c in p['columns']))
if __name__=='__main__':unittest.main()
