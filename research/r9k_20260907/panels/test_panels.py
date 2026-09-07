"""Input-only integrity fixtures for the fixed paired panels."""
import copy,json,unittest
import numpy as np,pandas as pd
import build_panels as B
class Panels(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.m=json.loads((B.ROOT/'panel_manifest.json').read_text());cls.a=pd.read_csv(B.ROOT/'pairedpanel44.csv',float_precision='round_trip');cls.b=pd.read_csv(B.ROOT/'panel174.csv',float_precision='round_trip')
 def test_fixed_columns_metadata_and_exact_H(self):
  m=self.m;self.assertEqual(len(self.a),1428);self.assertEqual(list(self.b),B.META+m['columns174']);self.assertEqual(len(m['columns174']),174);self.assertEqual(m['columns174'][:44],m['columns44']);self.assertEqual(m['columns174'][44:],sorted(m['added_columns']))
  pd.testing.assert_frame_equal(self.a,self.b[B.META+m['columns44']]);self.assertTrue(self.a.pid.is_unique);self.assertTrue(self.a.draft_year.le(2018).all());self.assertTrue(self.a.was_drafted.isin([0,1]).all())
  h=json.loads((B.W/'r9h/plan.json').read_text());idx=self.a.set_index('pid');n=0
  for q in h['queries'].values():self.assertEqual(B.values_hash(idx.loc[q['query_pids'],m['columns44']].to_numpy(float)),q['matrix_hash']);n+=1
  for p in h['canonical_payloads']:
   for v in p['folds']:self.assertEqual(B.values_hash(idx.loc[v['training_pids'],m['columns44']].to_numpy(float)),v['matrix_hash']);n+=1
  self.assertEqual(n,66)
 def test_all_added_cells_exact_leftjoin_and_missingness(self):
  sources={'F50':('r8w/data/fifty_features.csv',False),'combine':('verified_combine/data/train_inputs.csv',True),'player_game':('college_context_join_v1/candidate_inputs.csv',True),'team_context':('college_context_join_v1/candidate_inputs.csv',True)}
  for group,g in self.m['family_coverage'].items():
   cols=g['columns']
   if group=='dated_bio':
    src=pd.concat([B.frame(B.W/'verified_mock_bio/features_eligible.csv',['pid','draft_year']+cols),B.frame(B.W/'verified_mock_bio_extension/features_training_2015_2018.csv',['pid','draft_year']+cols)],ignore_index=True)
   else:p,rt=sources[group];src=B.frame(B.W/p,['pid','draft_year']+cols,rt)
   expected=B.merge(self.a[B.META],src,cols)
   self.assertEqual(B.values_hash(expected[cols].to_numpy(float)),B.values_hash(self.b[cols].to_numpy(float)))
   shuffled=B.merge(self.a[B.META],src.iloc[::-1],cols);self.assertEqual(B.values_hash(shuffled[cols].to_numpy(float)),B.values_hash(expected[cols].to_numpy(float)))
 def test_duplicate_and_conflicting_identity_rejected(self):
  base=self.a[B.META].head(2);src=base[['pid','draft_year']].copy();src['new_value']=[1.,2.]
  with self.assertRaises(AssertionError):B.merge(base,pd.concat([src,src.iloc[:1]]),['new_value'])
  wrong=src.copy();wrong.loc[wrong.index[0],'draft_year']+=1
  with self.assertRaises(AssertionError):B.merge(base,wrong,['new_value'])
  absent=B.merge(base,src.iloc[:1],['new_value']);self.assertTrue(np.isnan(absent.iloc[1].new_value));self.assertEqual(len(absent),2)
 def test_game_quarantine_date_and_minimum_guards(self):
  rows=json.loads((B.W/'college_context_join_v1/join_provenance.json').read_text());p=next(r for r in rows if r['game_join_reason']is None and r['team_join_reason']is None)
  for group in ['game','team']:B.validate_game_row(p,group)
  for kind in ['future_game','bad_group','team_partial','future_season']:
   z=copy.deepcopy(p);group='game'
   if kind=='future_game':z['player_game_max_date']=z['registered_draft_date']
   if kind=='bad_group':z['game_join_reason']='quarantined'
   if kind=='team_partial':z['team_cached_games']=19;group='team'
   if kind=='future_season':z['source_season']=z['draft_year']+1
   with self.assertRaises(AssertionError):B.validate_game_row(z,group)
 def test_bio_future_capture_and_unknown_source_rejected(self):
  sources=json.loads((B.W/'verified_consensus/validated_sources.json').read_text());s=next(r for r in sources if r['feature_eligible']);B.validate_capture(s)
  for field,value in [('source_available_by_utc',s['cutoff_utc']),('source_last_updated_date',s['draft_date']),('feature_eligible',False)]:
   z=copy.deepcopy(s);z[field]=value
   with self.assertRaises(AssertionError):B.validate_capture(z)
 def test_hashes_roundtrip_and_no_forbidden_fields(self):
  for name,info in self.m['outputs'].items():
   self.assertEqual(B.h((B.ROOT/name).read_bytes()),info['sha256']);d=pd.read_csv(B.ROOT/name,float_precision='round_trip');cols=self.m['columns44']if info['columns']==44 else self.m['columns174'];self.assertEqual(B.values_hash(d[cols].to_numpy(float)),info['matrix_hash'])
  self.assertFalse(set(['actual_pick','target','war','draft_pick']+self.m['forbidden_removed_columns'])&set(self.m['columns174']));self.assertFalse(np.isinf(self.b[self.m['columns174']].to_numpy(float)).any())
  with self.assertRaises(AssertionError):B.pin(B.ROOT/'panel174.csv','0'*64)
if __name__=='__main__':unittest.main()
