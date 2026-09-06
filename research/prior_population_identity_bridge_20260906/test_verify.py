"""Adversarial identity checks; no label values or model computations."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('identity_bridge', ROOT / 'verify.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class IdentityBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / 'private/review_config.json').read_text())
        cls.cid, cls.config = next(iter(config.items()))
        cls.member = next(r for r in m.rows(m.CROSSWALK) if r['candidate_id'] == cls.cid)
        cls.target = json.loads((ROOT / f"private/{cls.config['target_entity']}_identity_only.json").read_text())
        cls.father = json.loads((ROOT / f"private/{cls.config['wrong_entity']}_identity_only.json").read_text())
        cls.expected = {r['raptor_source_id'] for r in m.rows(m.PRIOR_PROVENANCE) if r['candidate_id'] == cls.cid}

    def test_verified_pair_matches_both_ID_systems(self):
        pair = m.verify_bridge(self.member, self.target, self.expected)
        self.assertEqual(pair['nba_id'], int(self.member['official_predraft_id']))
        self.assertEqual({pair['raptor_player_id']}, self.expected)

    def test_father_identity_cannot_replace_child(self):
        with self.assertRaises(ValueError):
            m.verify_bridge(self.member, self.father, self.expected)

    def test_wrong_calendar_ID_rejected_even_with_same_name(self):
        with self.assertRaises(ValueError):
            m.verify_bridge(self.member, self.target, {'wrong_source_id'})

    def test_duplicate_published_IDs_rejected(self):
        target = copy.deepcopy(self.target)
        target['identity_claims_only'].append(copy.deepcopy(m.claims(target, 'P3647')[0]))
        with self.assertRaises(ValueError):
            m.verify_bridge(self.member, target, self.expected)

    def test_deprecated_identity_is_not_accepted(self):
        target = copy.deepcopy(self.target)
        for claim in target['identity_claims_only']:
            if claim['property'] == 'P3647': claim['rank'] = 'deprecated'
        with self.assertRaises(ValueError):
            m.verify_bridge(self.member, target, self.expected)

    def test_WAR_agreement_metadata_cannot_change_identity(self):
        first = copy.deepcopy(self.member)
        first['existing_ordinal_value_agrees'] = 'True'
        second = copy.deepcopy(self.member)
        second['existing_ordinal_value_agrees'] = 'False'
        self.assertEqual(m.verify_bridge(first, self.target, self.expected), m.verify_bridge(second, self.target, self.expected))

    def test_proposals_have_no_numeric_labels_and_keep_actual_seasons(self):
        proposals = m.rows(ROOT / 'private/proposed_calendar_entries.csv')
        self.assertEqual(len(proposals), 5)
        self.assertFalse(set(proposals[0]) & {'war','y_s1_war','birth_date','height','weight'})
        prior = {(r['candidate_id'], int(r['ordinal']), int(r['season_end'])) for r in m.rows(m.PRIOR_PROVENANCE)}
        self.assertTrue(all((r['candidate_id'],int(r['ordinal']),int(r['season_end'])) in prior for r in proposals))
        self.assertTrue(all(int(r['season_end']) <= 2018 for r in proposals))

    def test_all_four_wrong_caches_are_unchanged(self):
        records = m.rows(ROOT / 'private/wrong_person_cache_audit.csv')
        self.assertEqual(len(records), 4)
        self.assertEqual(len({r['candidate_id'] for r in records}), 2)
        for r in records:
            self.assertEqual(m.sha(Path(r['source_cache_path'])), r['source_cache_sha256'])
            self.assertNotEqual(r['intended_birth_date'], r['wrong_person_birth_date'])
            self.assertNotEqual(r['intended_draft_year'], r['wrong_person_draft_year'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
