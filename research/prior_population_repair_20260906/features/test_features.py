"""Read-only integrity tests for the bounded feature-only repair."""
from pathlib import Path
import datetime as dt
import hashlib
import importlib.util
import json
import re
import unittest
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parent
W = R.parents[1]
K = pd.read_csv(R / 'private/identity_crosswalk.csv')
F = pd.read_csv(R / 'numeric_feature_join.csv')
M = json.loads((R / 'manifest.json').read_text())
NAMES = dict(zip(K.player_name_source, K.candidate_id))

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def row(table, name): return table.set_index('candidate_id').loc[NAMES[name]]
def historical(publication, capture, draft):
    assert publication < draft
    assert dt.datetime.fromisoformat(capture) < dt.datetime.fromisoformat(draft).replace(tzinfo=ZoneInfo('America/New_York'))

class FeatureRepairTests(unittest.TestCase):
    def test_exact_population_and_schema(self):
        self.assertEqual(len(F), 8)
        self.assertEqual(len(F.columns), 150)
        self.assertTrue(F[['candidate_id','draft_year']].equals(K[['candidate_id','draft_year']]))
        self.assertEqual(F.candidate_id.nunique(), 8)
        self.assertEqual(set(F.columns[2:]), set(sum(M['families'].values(), [])))
        self.assertTrue(np.isfinite(F.iloc[:,2:].stack().dropna().to_numpy()).all())
        self.assertTrue(all(c.startswith(('ctx_base_', 'ctx_skill_', 'vcons_', 'vmb_', 'report_')) for c in F.columns[2:]))
        for family, columns in M['families'].items():
            t = pd.read_csv(R / f'{family}_features.csv')
            self.assertTrue(t[['candidate_id','draft_year']].equals(F[['candidate_id','draft_year']]))
            np.testing.assert_allclose(F[columns].to_numpy(), t[columns].to_numpy(), equal_nan=True, rtol=1e-14)

    def test_identity_alias_failure_closed(self):
        college = pd.read_csv(R / 'college_features.csv')
        self.assertTrue(row(college, 'Jeff Taylor').iloc[1:].isna().all())
        self.assertTrue(row(college, 'Marcus Denmon').iloc[1:].notna().all())
        source_identities = json.loads((R / 'private/mock_source_identities.json').read_text())
        jeff = [r for r in source_identities if r['candidate_id'] == NAMES['Jeff Taylor']]
        self.assertEqual(len(jeff), 1)
        self.assertEqual(jeff[0]['source_name'], 'Jeff Taylor')
        self.assertEqual(jeff[0]['source_id'], 'dx_2012')
        self.assertNotIn('Jeffery Taylor', set(K[['player_name_source','broad_name','legacy_name']].astype(str).to_numpy().flat))

    def test_college_source_replay_and_cutoffs(self):
        source = json.loads((R / 'college_provenance.json').read_text())
        self.assertEqual(len(source), 7)
        fields = {int(k): v for k,v in M['college_source_field_indices'].items()}
        self.assertTrue(set(fields).isdisjoint({0,1,26,31,32,45,66}))
        rawroot = Path('/Users/kennakao/nba/datarebuild/tracking_raw')
        for fact in source:
            self.assertLessEqual(fact['source_season'], fact['draft_year'])
            self.assertIn(fact['source_year_gap'], [0,1])
            self.assertFalse(fact['original_release_vintage_verified'])
            p = rawroot / fact['source_file']
            self.assertEqual(sha(p), fact['source_sha256'])
            values = pd.read_csv(p, header=None, usecols=list(fields)).iloc[fact['source_row_zero_based']]
            actual = F.set_index('candidate_id').loc[fact['candidate_id']]
            for idx, label in fields.items():
                self.assertAlmostEqual(float(values[idx]), actual['ctx_base_' + label], places=10)
            self.assertAlmostEqual(actual.ctx_base_three_share, actual.ctx_base_fg3a / (actual.ctx_base_fg2a + actual.ctx_base_fg3a), places=12)
            self.assertAlmostEqual(actual.ctx_skill_ft_volume, actual.ctx_base_ft_pct*np.log1p(actual.ctx_base_fta), places=10)
        glen = [p for p in source if p['candidate_id'] == NAMES['Glen Rice Jr.']][0]
        self.assertEqual((glen['source_season'],glen['draft_year']), (2012,2013))

    def test_fixed_mock_facts(self):
        t = pd.read_csv(R / 'consensus_features.csv')
        expected = {'Jeff Taylor': (28,28,np.nan,1), 'Glen Rice Jr.': (31.5,29,5,2), 'Deshaun Thomas': (42.5,37,11,2), 'Colton Iverson': (47,43,8,2), 'Alec Brown': (57,57,np.nan,1), 'DeAndre Daniels': (44,39,10,2)}
        for name, facts in expected.items():
            np.testing.assert_allclose(row(t,name).iloc[1:].to_numpy(dtype=float), facts, equal_nan=True)
        for name in ['Marcus Denmon','Xavier Thames']:
            self.assertTrue(row(t,name).iloc[1:].isna().all())
        for p in json.loads((R / 'mock_provenance.json').read_text()):
            historical(p['update_date'], p['capture_utc'], p['draft_date'])
        self.assertEqual(len(json.loads((R / 'mock_provenance.json').read_text())), 10)

    def test_bio_whole_row_priority_and_units(self):
        t = pd.read_csv(R / 'bio_features.csv').set_index('candidate_id')
        source = pd.read_csv(R / 'mock_bio_observations.csv')
        for cid in t.index:
            candidates = source[source.candidate_id.eq(cid)].copy()
            if candidates.empty:
                self.assertTrue(t.loc[cid].iloc[1:].isna().all()); continue
            candidates['priority'] = candidates.publisher.map({'dx':0,'nbadraft':1})
            chosen = candidates.sort_values('priority').iloc[0]
            np.testing.assert_allclose(t.loc[cid,M['families']['bio']].to_numpy(dtype=float), chosen[M['families']['bio']].to_numpy(dtype=float), equal_nan=True)
            h,w,bmi = t.loc[cid, ['vmb_listed_height_in','vmb_listed_weight_lb','vmb_listed_bmi']]
            self.assertAlmostEqual(bmi, w*.45359237/(h*.0254)**2, places=9)
        self.assertTrue(pd.isna(t.loc[NAMES['Alec Brown'],'vmb_age_reported_years']))
        self.assertAlmostEqual(t.loc[NAMES['Jeff Taylor'],'vmb_listed_height_in'],79)

    def test_report_new_facts_and_section_boundaries(self):
        source_root = W / 'source_validation/expansion'
        facts = json.loads((R / 'new_report_numeric_facts.json').read_text())
        self.assertEqual(len(facts),5)
        specs = {'Xavier Thames':('dx4617', {'report_pullup_fga_pg':4.9,'report_pullup_fg_pct':40.0}, 'DeAndre Kane'),
                 'Alec Brown':('dx4618', {'report_poss_pg':14.9,'report_transition_poss_pct':10.8,'report_spotup_ppp':1.14}, 'Jordan Bachynski')}
        lex = json.loads((source_root / 'extraction_rules.json').read_text())['lexicons']
        for name,(sid,expected,next_name) in specs.items():
            body = (source_root/'private'/f'{sid}.body.txt').read_bytes()
            sections = [' '.join(b.split()) for b in re.split(r'(?:^|\n)\s*[-•]\s*',body.decode())[1:]]
            selected = [b for b in sections if name in b[:80]]
            self.assertEqual(len(selected),1); section = selected[0]
            self.assertNotIn(next_name, section)
            subset = [v for v in facts if v['candidate_id']==NAMES[name]]
            self.assertEqual({v['metric']:v['value'] for v in subset}, expected)
            actual = row(F,name)
            for fact in subset:
                self.assertEqual(fact['body_sha256'], hashlib.sha256(body).hexdigest())
                self.assertEqual(fact['section_sha256'], hashlib.sha256(section.encode()).hexdigest())
                self.assertEqual(actual[fact['metric']],fact['value'])
                self.assertTrue(fact['unit'] and fact['denominator'])
                historical(fact['publication_date'],fact['capture_utc'],'2014-06-26')
            wc=len(re.findall(r'\b\w+\b',section))
            self.assertEqual(actual.report_text_words,wc)
            for term,pattern in lex.items():
                self.assertAlmostEqual(actual[f'report_text_{term}_per1k'],1000*len(re.findall(pattern,section,re.I))/wc,places=10)

    def test_dates_fail_closed(self):
        historical('2014-06-21','2014-06-26T03:59:59+00:00','2014-06-26')
        for pub,capture in [('2014-06-26','2014-06-25T00:00:00+00:00'),('2014-06-21','2014-06-26T04:00:00+00:00'),('2014-06-21','2015-06-20T00:00:00+00:00')]:
            with self.assertRaises(AssertionError): historical(pub,capture,'2014-06-26')

    def test_sources_and_repair_hashes_unchanged(self):
        for directory, pin in M['pinned_source_packages'].items():
            root = W / directory; path = root / pin['manifest']
            self.assertEqual(sha(path),pin['sha256'])
            for name, record in json.loads(path.read_text())['files'].items():
                self.assertEqual(sha(root / name), record['sha256'])
        for name,digest in M['files'].items(): self.assertEqual(sha(R/name),digest)
        self.assertFalse(M['labels_or_outcomes_read'])
        self.assertEqual(M['network_calls'],0)
        self.assertFalse(M['models_or_publishing_performed'])

if __name__ == '__main__': unittest.main(verbosity=2)
