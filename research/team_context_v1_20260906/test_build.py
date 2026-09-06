import copy, csv, json, pathlib, shutil, tempfile, unittest
import build as module
from build import build, eligible, features


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.row = {'source_season':2012,'min_date':'2011-11-01','max_date':'2012-04-02',
                    'rejected_source_games':0,'raw_source_games':30,'validated_games':30}

    def test_actual_dates_and_class(self):
        self.assertTrue(eligible(self.row,2012));self.assertFalse(eligible(self.row,2011))
        self.assertTrue(eligible(self.row,2013));self.assertFalse(eligible(self.row,2014))
        for date in ['2013-04-02','2012-06-01','not a date']:
            row={**self.row,'max_date':date};self.assertFalse(eligible(row,2012))

    def test_incomplete_season_is_not_partial_fill(self):
        for change in [{'rejected_source_games':1},{'validated_games':29},{'validated_games':19,'raw_source_games':19}]:
            self.assertFalse(eligible({**self.row,**change},2012))

    def test_future_season(self):
        self.assertFalse(eligible({**self.row,'source_season':2019,'min_date':'2018-11-01','max_date':'2019-04-01'},2019))

    def test_ratio_and_margin_algebra(self):
        row={'validated_games':2}
        fields=['pts','fgm','fga','fg3m','fg3a','fta','orb','drb','tov','ast','stl','blk']
        row.update({'team_'+k:v for k,v in zip(fields,[140,50,120,20,50,30,20,40,25,30,12,8])})
        row.update({'opponent_'+k:v for k,v in zip(fields,[130,48,110,15,45,25,15,35,20,25,10,5])})
        f=features(row);self.assertEqual(f['tctx_margin_pg'],5)
        self.assertEqual(f['tctx_efg'],.5)
        self.assertEqual(f['tctx_offensive_rebound_share'],20/55)
        doubled={k:(v*2) for k,v in row.items()};self.assertEqual(features(doubled),f)
        row['opponent_tov']=0;self.assertIsNone(features(row)['tctx_steals_per_opponent_turnover'])

    def test_build_preserves_population_and_later_source_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            summary=build(output=root/'full')
            with (root/'full/team_context_train_candidates.csv').open() as stream:
                full=list(csv.DictReader(stream))
            lineage=[p for p in json.loads(module.LINEAGE.read_text()) if int(p['draft_year'])<=2018]
            self.assertEqual([r['pid'] for r in full],[p['pid'] for p in lineage])
            self.assertEqual(len(full),790);self.assertEqual(summary['rows_all_missing'],59)
            cols=[k for k in full[0] if k.startswith('tctx_')]
            self.assertTrue(all(sum(r[k]!='' for k in cols) in [0,20] for r in full))
            build(max_source_season=2014,output=root/'early')
            with (root/'early/team_context_train_candidates.csv').open() as stream:
                early=list(csv.DictReader(stream))
            self.assertEqual([r for r in full if int(r['draft_year'])<=2014],
                             [r for r in early if int(r['draft_year'])<=2014])

    def test_source_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source=pathlib.Path(directory)/'source';source.mkdir()
            original=module.SOURCE
            shutil.copy2(original/'PUBLIC_ALLOWLIST.json',source/'PUBLIC_ALLOWLIST.json')
            name='team_season_totals_candidate.csv'
            (source/name).write_bytes((original/name).read_bytes()+b'\n')
            try:
                module.SOURCE=source
                with self.assertRaises(AssertionError):build(output=pathlib.Path(directory)/'out')
            finally:module.SOURCE=original


if __name__=='__main__':unittest.main()
