"""Independent game-algebra and temporal boundary fixtures; no ratings/models."""
from pathlib import Path
import copy,datetime as dt,json,unittest
import pandas as pd
from audit import parse_game
R=Path(__file__).resolve().parent
class DependencyTests(unittest.TestCase):
 def setUp(self):self.raw=json.loads((R/'private/season2012.bin').read_bytes())[0]
 def test_known_algebra(self):
  x=parse_game(self.raw,2012);self.assertEqual(x['date'],'2011-11-07');self.assertEqual(x['team_minutes'],200)
  self.assertEqual(x['sides'][0]['pts'],64);self.assertEqual(x['sides'][1]['pts'],73)
  self.assertEqual(x['sides'][0]['fgm'],21);self.assertEqual(x['sides'][0]['fg3m'],5);self.assertEqual(x['sides'][0]['ftm'],17)
 def test_corruption_rejections(self):
  for idx,value in [(1,'1/0/00'),(1,'11/7/2019'),(1,'6/1/2012'),(2,201),(5,-1),(5,21.5),(19,65),(13,999),(18,float('inf'))]:
   x=copy.deepcopy(self.raw);x[idx]=value
   with self.assertRaises((AssertionError,ValueError)):parse_game(x,2012)
  with self.assertRaises(AssertionError):parse_game(self.raw,2019)
 def test_overtime_and_temporal_boundary(self):
  x=copy.deepcopy(self.raw);x[2]=225;x[1]='5/31/2012';self.assertEqual(parse_game(x,2012)['team_minutes'],225)
  x[1]='7/1/2011';self.assertEqual(parse_game(x,2012)['date'],'2011-07-01')
 def test_side_swap(self):
  x=copy.deepcopy(self.raw);x[3],x[4]=x[4],x[3];x[5:20],x[20:35]=x[20:35],x[5:20]
  self.assertEqual(parse_game(x,2012)['sides'][::-1],parse_game(self.raw,2012)['sides'])
 def test_candidate_totals_and_lineage(self):
  t=pd.read_csv(R/'team_season_totals_candidate.csv');l=pd.read_csv(R/'team_game_lineage.csv.gz')
  self.assertEqual(len(t),5741);self.assertEqual(len(l),2*62480);self.assertFalse(t.model_eligible.any());self.assertFalse(t.publication_vintage_verified.any())
  self.assertTrue(t.source_season.between(2008,2018).all());self.assertTrue((t.validated_games+t.rejected_source_games==t.raw_source_games).all())
  for prefix in ['team_','opponent_']:
   self.assertTrue((2*t[prefix+'fgm']+t[prefix+'fg3m']+t[prefix+'ftm']==t[prefix+'pts']).all())
   self.assertTrue((t[prefix+'orb']+t[prefix+'drb']==t[prefix+'trb']).all())
  counts=l.groupby(['source_season','team_id']).size()
  for row in t.itertuples():self.assertEqual(counts.loc[(row.source_season,row.team_id)],row.validated_games)
 def test_missing_and_blocked_not_admitted(self):
  i=json.loads((R/'player_dependency_inventory.json').read_text());self.assertEqual(len(i),11);self.assertTrue(all(x['player_impact_features_admitted']==0 for x in i))
  self.assertTrue(sum(x['basic_points_vs_per_game_times_gp_inconsistent'] for x in i)>10000)
  log=json.loads((R/'network_ledger.json').read_text());self.assertEqual(len(log),13);self.assertEqual(log[-1]['status'],403);self.assertFalse(log[-1]['eligible'])
  for x in json.loads((R/'local_source_lineage.json').read_text()):self.assertNotIn(45,x['read_indices'])
if __name__=='__main__':unittest.main(verbosity=2)
