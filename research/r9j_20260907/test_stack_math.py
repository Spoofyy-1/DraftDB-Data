import unittest,json
from pathlib import Path
import numpy as np
from stack_math import blend,family_seed_average,doubled_ranks

class FixedStacks(unittest.TestCase):
 def test_equal_and_ties(self):
  vectors=[np.array([1.,1.,3.]),np.array([3.,1.,1.]),np.array([2.,1.,3.])]
  r={'kind':'fixed_rank_weights','members':[{'units':20}]*3};z=blend(vectors,r,np.zeros((3,44)))
  np.testing.assert_array_equal(z,np.sum([doubled_ranks(x)for x in vectors],axis=0)/(6*3))
 def test_seed_permutation_invariant(self):
  vectors=[np.array([1.,1.,3.]),np.array([3.,1.,1.]),np.array([2.,1.,3.])]
  np.testing.assert_array_equal(family_seed_average(vectors),family_seed_average(vectors[::-1]))
 def test_duplicate_vectors_remain_tied(self):
  x=np.zeros((4,44));x[:2]=np.nan
  vectors=[np.array([.2,.2,.3,.5]),np.array([.3,.3,.2,.1]),np.array([.1,.1,.8,.9])]
  r={'kind':'adapted_coverage_control','members':[{}]*3,'rich_units':[0,15,45],'thin_units':[60,0,0]}
  z=blend(vectors,r,x);self.assertEqual(z[0],z[1]);self.assertEqual(z[0],doubled_ranks(vectors[0])[0]/8)
 def test_shape_and_weight_reject(self):
  r={'kind':'fixed_rank_weights','members':[{'units':59}]}
  with self.assertRaises(AssertionError):blend([[1.,2.,3.]],r,np.zeros((3,44)))
  with self.assertRaises(AssertionError):family_seed_average([[1.,2.],[3.,4.]])
 def test_registration_counts_unique(self):
  p=json.loads((Path(__file__).parent/'plan.json').read_text());self.assertEqual(len(p['tasks']),48);self.assertEqual(len(p['stacks']['recipes']),187)
  identities=[]
  for r in p['stacks']['recipes']:
   identities.append(json.dumps({k:v for k,v in r.items()if k!='id'},sort_keys=True))
  self.assertEqual(len(set(identities)),187);self.assertTrue(all(t['seed']==0 for t in p['tasks']if 'ridge_'in t['variant']))
 def test_three_and_five_rational_duplicate_scores(self):
  for size in [3,5]:
   vector=np.array([.0015]*size+[.3,.6,.9]);matrix=np.zeros((len(vector),44));matrix[size:,0]=[1.,2.,3.]
   recipe={'kind':'fixed_rank_weights','members':[{'units':15},{'units':45}]}
   score=blend([vector,vector],recipe,matrix);before=score.tobytes()
   self.assertTrue(np.all(score[:size]==score[0]));self.assertEqual(before,score.tobytes())
   np.testing.assert_array_equal(score,doubled_ranks(vector)/(2*len(vector)))

if __name__=='__main__':unittest.main()
