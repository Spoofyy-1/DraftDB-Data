"""Bounded negative checks for identity joins; no models or real outcomes."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('identity_audit', ROOT / 'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class IdentityBoundaryTests(unittest.TestCase):
    def test_no_general_suffix_or_fuzzy_matching(self):
        self.assertNotEqual(audit.normalize('Glen Rice Jr.'), audit.normalize('Glen Rice'))
        self.assertNotEqual(audit.normalize('Marko Todorovic'), audit.normalize('Marko Todorovich'))
        self.assertEqual(audit.normalize('İzzet Türkyılmaz'), audit.normalize('Izzet Turkyilmaz'))

    def test_null_NBA_ID_does_not_exclude_identity(self):
        self.assertEqual(audit.key_identity_id({'player_uid': 'nba_203134', 'nba_id': None}), 203134)
        self.assertIsNone(audit.key_identity_id({'player_uid': 'source_only_abc', 'nba_id': None}))

    def test_conflicting_IDs_are_rejected(self):
        with self.assertRaises(ValueError):
            audit.key_identity_id({'player_uid': 'nba_203134', 'nba_id': 779})

    def test_ambiguous_identity_is_not_first_match(self):
        with self.assertRaises(ValueError):
            audit.unique([{'pid': 'a'}, {'pid': 'b'}], 'homonym')

    def test_combine_wrong_requested_year_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'combine.json'
            path.write_text(json.dumps({'parameters': {'SeasonYear': '2013-14'}}))
            with self.assertRaises(ValueError):
                audit.combine_identity(path, 2012)

    def test_single_future_combine_row_is_rejected(self):
        fixture = {'parameters': {'SeasonYear': '2012-13'}, 'resultSets': [{
            'name': 'DraftCombineStats', 'headers': ['SEASON', 'PLAYER_ID', 'PLAYER_NAME'],
            'rowSet': [[2012, 1, 'First'], [2013, 2, 'Future']]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'combine.json'
            path.write_text(json.dumps(fixture))
            with self.assertRaises(ValueError):
                audit.combine_identity(path, 2012)

    def test_complete_source_population_and_no_private_columns(self):
        path = ROOT / 'data/all_membership_statuses.csv'
        if not path.exists():
            self.skipTest('Run offline audit first')
        records = audit.rows(path)
        self.assertEqual(len(records), 180)
        self.assertEqual(len({r['candidate_id'] for r in records}), 180)
        for year in (2012, 2013, 2014):
            self.assertEqual(sum(int(r['draft_year']) == year for r in records), 60)
        self.assertTrue(all(r['membership_retained'] == 'True' for r in records))
        self.assertFalse(set(records[0]) & {'player_name', 'player_name_source', 'nba_id', 'broad_pid', 'legacy_pid', 'actual_pick', 'WAR'})

    def test_missing_and_provisional_rows_remain_explicit(self):
        path = ROOT / 'data/gap_statuses.csv'
        if not path.exists():
            self.skipTest('Run offline audit first')
        records = audit.rows(path)
        self.assertEqual(len(records), 24)
        self.assertEqual(sum(r['existing_research_row'] == 'True' for r in records), 2)
        self.assertTrue(all(r['model_ready'] == 'False' for r in records))
        unresolved = [r for r in records if r['mapping_status'].startswith('unresolved')]
        provisional = [r for r in records if 'provisional' in r['mapping_status']]
        self.assertEqual(len(unresolved), 10)
        self.assertEqual(len(provisional), 4)
        self.assertTrue(all(r['identity_link_ready'] == 'False' for r in unresolved + provisional))

    def test_namespaces_are_kept_distinct(self):
        path = ROOT / 'private/reviewed_crosswalk.csv'
        if not path.exists():
            self.skipTest('Private review unavailable')
        records = [r for r in audit.rows(path) if r['broad_pid'] and r['legacy_pid']]
        self.assertEqual(len(records), 7)
        self.assertTrue(all(r['broad_pid'] != r['legacy_pid'] for r in records))

if __name__ == '__main__':
    unittest.main(verbosity=2)
