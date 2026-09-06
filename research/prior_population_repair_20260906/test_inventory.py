"""Boundary checks for calendar candidates and preserved repair population."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('population_inventory', ROOT / 'build_inventory.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

MEMBER = dict(candidate_id='source_candidate', draft_year='2012', player_name_source='Example Person',
              broad_name='Example Person', legacy_name='Example Person')

class RepairBoundaryTests(unittest.TestCase):
    def test_future_source_and_unrelated_target_changes_do_not_change_calendar(self):
        rows = [dict(player_name='Example Person',player_id='one',season='2014'),
                dict(player_name='Example Person',player_id='one',season='2016')]
        before = m.candidate_calendar(MEMBER, rows, 2016)
        after = m.candidate_calendar(MEMBER, rows + [dict(player_name='Example Person',player_id='future',season='2020'),
            dict(player_name='Other Person',player_id='other',season='2014')], 2016)
        self.assertEqual(before, after)

    def test_delayed_debut_and_season_gap_are_preserved(self):
        rows = [dict(player_name='Example Person',player_id='one',season='2014'),
                dict(player_name='Example Person',player_id='one',season='2016')]
        result, _ = m.candidate_calendar(MEMBER, rows, 2018)
        self.assertEqual([int(r['season']) for r in result], [2014, 2016])

    def test_no_record_does_not_create_zero(self):
        result, audit = m.candidate_calendar(MEMBER, [], 2018)
        self.assertEqual(result, [])
        self.assertEqual(audit['status'], 'no_eligible_source_record')

    def test_remaining_eligible_homonym_stays_unresolved(self):
        rows = [dict(player_name='Example Person',player_id='one',season='2014'),
                dict(player_name='Example Person',player_id='two',season='2015')]
        result, audit = m.candidate_calendar(MEMBER, rows, 2018)
        self.assertEqual(result, [])
        self.assertEqual(audit['eligible_identity_count'], 2)

    def test_old_homonym_remains_disclosed_not_automatically_certified(self):
        rows = [dict(player_name='Example Person',player_id='old',season='1987'),
                dict(player_name='Example Person',player_id='one',season='2014')]
        result, audit = m.candidate_calendar(MEMBER, rows, 2018)
        self.assertEqual(len(result), 1)
        self.assertEqual(audit['historical_name_id_count'], 2)
        self.assertIn('pending', audit['status'])

    def test_future_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            m.candidate_calendar(MEMBER, [], 2019)

    def test_candidate_value_agreement_is_not_identity_certification(self):
        candidate = dict(independent_source_id_bridge_verified=False,
                         existing_ordinal_value_agrees=True, season_end=2015)
        self.assertEqual(m.approved_labels([candidate]), [])

    def test_all_eight_rows_preserved_and_no_identity_in_combine_inputs(self):
        rows = m.load_csv(ROOT / 'data/combine_feature_candidates.csv')
        members = m.load_csv(ROOT / 'data/pilot_member_index.csv')
        self.assertEqual(len(rows), 8)
        self.assertEqual({r['candidate_id'] for r in rows}, {r['candidate_id'] for r in members})
        self.assertFalse(set(rows[0]) & {'player_name','player_name_source','broad_pid','legacy_pid','nba_id','actual_pick','war'})

    def test_no_label_promotion_and_no_absence_zeros(self):
        inventory = m.load_csv(ROOT / 'private/join_inventory.csv')
        self.assertEqual(len(inventory), 8)
        self.assertTrue(all(r['inferred_zero'] == 'False' and r['membership_retained'] == 'True' for r in inventory))
        self.assertEqual(m.load_csv(ROOT / 'private/approved_labels.csv'), [])

if __name__ == '__main__':
    unittest.main(verbosity=2)
