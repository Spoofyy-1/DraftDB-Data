"""Metric and aggregation fixtures only; never used as model training data."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import postprocess as P


class Tests(unittest.TestCase):
    def test_rank_direction_ties_and_constant(self):
        self.assertAlmostEqual(P.rho([2, 2, 5, 9], [1, 1, 4, 8]), 1)
        self.assertAlmostEqual(P.rho([9, 9, 5, 2], [1, 1, 4, 8]), -1)
        self.assertEqual(P.rho([7, 7, 7], [1, 2, 3]), 0)

    def test_frozen_modes_masks_and_degenerate_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scoring').mkdir()
            plan = {'outer_years': [2012, 2013, 2014], 'seeds': [0, 101, 202], 'scoring': {}}
            records = []
            for year in plan['outer_years']:
                path = root / 'scoring' / f'{year}.npz'
                np.savez(path, pid=np.array(['a', 'b', 'c', 'd']), legacy_truth=[1., 2., 3., 4.], observed_truth_mask=np.array([True, True, True, False]))
                plan['scoring'][str(year)] = {'sha256': P.sha(path)}
                seeds = []
                for seed in plan['seeds']:
                    vector = [1., 2., 3., 4.]
                    seeds.append({'seed': seed, 'architectures': {name: vector for name in
                        ['equal_three_direct', 'fixed_coverage_direct', 'fixed_coverage_residual', 'learned_global_nonnegative_meta']},
                        'members': {name: {'canonical_predictions': vector} for name in ['xgb_q25', 'tabicl', 'ridge']},
                        'meta': {'weights': [1., 0., 0.]}, 'residual': {'corrected_query_prediction': vector}})
                records.append({'outer_year': year, 'query_pids': ['a', 'b', 'c', 'd'], 'panel_id': 'panel44',
                                'policy_id': 'fixture_only', 'seed_results': seeds})
            (root / 'plan.json').write_text(json.dumps(plan))
            result = P.summarize(records, root)
            self.assertEqual(result['scored_prediction_records'], 96)
            self.assertEqual(len(result['stack_summaries_oof']), 4)
            self.assertEqual(len(result['control_summaries_oof']), 4)
            for row in result['stack_summaries_oof']:
                self.assertAlmostEqual(row['full']['mean_score'], 1)
                self.assertAlmostEqual(row['observed']['mean_score'], 1)
                self.assertAlmostEqual(row['full']['fixed_three_seed_rank_average'], 1)
                self.assertEqual(row['multi_family_every_fold_seed'], row['architecture'] != 'learned_global_nonnegative_meta')
            self.assertTrue(result['best_actual_multifamily_stack']['multi_family_every_fold_seed'])
            self.assertEqual(P.summarize(records[:1], root)['stack_summaries_oof'], [])


if __name__ == '__main__':
    unittest.main()
