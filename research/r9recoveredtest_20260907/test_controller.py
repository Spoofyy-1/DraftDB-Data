import unittest
from unittest.mock import patch
import numpy as np
import score_frozen as S
import verify as V

class Gates(unittest.TestCase):
 def test_no_answers_when_freeze_check_fails(self):
  with patch.object(S,'validate_freeze',side_effect=AssertionError('missing seventh prediction')),patch.object(S.pd,'read_csv') as reader:
   with self.assertRaisesRegex(AssertionError,'seventh'):S.score()
   reader.assert_not_called()
 def test_undefined_year_never_omitted(self):
  self.assertIsNone(S.mean([.4,None,.5]));self.assertIsNone(S.correlation([1,1,1],[1,2,3]))
  self.assertAlmostEqual(S.mean([.2,.4]),.3)
 def test_metric_is_rank_not_position_accuracy(self):
  self.assertAlmostEqual(S.correlation([30,20,10],[3,2,1]),1.)
  self.assertAlmostEqual(S.correlation([30,20,10],[1,2,3]),-1.)
 def test_recovered_weights_route_thin_hybrid(self):
  m={'tabicl':np.array([4,3,2,1]),'ridge':np.array([1,2,3,4]),'hybrid':np.array([4,1,3,2])}
  a=V.arithmetic([m,m,m],np.array([True,False,False,True]))
  np.testing.assert_array_equal(a['family_seed_rank_average']['recovered_gen11'],[1.,.5,.75,.25])
  np.testing.assert_array_equal(a['family_seed_rank_average']['always_rich'],[.25,.5,.75,1.])
 def test_three_seed_blend_no_best_seed(self):
  one={'tabicl':np.array([1,2,3]),'ridge':np.array([1,2,3]),'hybrid':np.array([1,2,3])}
  reverse={k:v[::-1] for k,v in one.items()};a=V.arithmetic([one,reverse,one],np.array([False]*3))
  np.testing.assert_array_equal(a['family_seed_rank_average']['recovered_gen11'],[1/3,2/3,1])
if __name__=='__main__':unittest.main(verbosity=2)
