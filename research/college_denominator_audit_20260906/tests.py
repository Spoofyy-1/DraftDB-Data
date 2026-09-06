"""Independent algebra, source boundary and fixed-sample regression checks."""
import contextlib,csv,io,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import build
class Checks(unittest.TestCase):
    def fixture(self):
        r=[None]*53
        for i in build.GAME_MAP:r[i]=0
        for i,v in {0:'20171110',5:'Other College',6:'game1',47:'College',48:'Player',51:123,52:2018,23:2,24:5,25:1,26:4,27:2,28:3,33:9,34:1,35:2,36:3,37:4,38:1,39:1,42:2}.items():r[i]=v
        return r
    def test_independent_scoring(self):
        p=build.parse(self.fixture());self.assertEqual(p['points'],9);self.assertEqual(p['two_m']+p['three_m'],3);self.assertEqual(p['tov'],4)
    def test_bad_counts_and_arithmetic(self):
        for i,value in [(33,10),(23,6),(28,1),(42,6),(37,-1),(34,.5),(35,float('nan')),(36,float('inf'))]:
            r=self.fixture();r[i]=value
            with self.assertRaises((AssertionError,ValueError)):build.parse(r)
    def test_date_and_schema_boundaries(self):
        for i,value in [(0,'20190701'),(0,'20170630'),(0,'20180601'),(52,2019)]:
            r=self.fixture();r[i]=value
            with self.assertRaises((AssertionError,ValueError)):build.parse(r)
        for change in [self.fixture()[:-1],self.fixture()+[0]]:
            with self.assertRaises(AssertionError):build.parse(change)
        with self.assertRaises(AssertionError):build.parse(self.fixture(),2019)
    def test_ignored_impact_fields_have_no_effect(self):
        r=self.fixture();expected=build.parse(r)
        for i in set(range(53))-set(build.GAME_READ_INDICES):r[i]={'DO_NOT_USE':'arbitrary ignored payload'}
        self.assertEqual(build.parse(r),expected)
    def test_sample_and_direct_total_regression(self):
        reg,entry,te,sample,games,team=build.load()
        expected=[30,31,21,31,31,31,31,6,10,27,17,19]
        got=[len([g for g in games if g['source_player_id']==s['32']]) for s in sample]
        self.assertEqual(got,expected)
        # Includes a true zero-scoring limited-minute reserve, retained without imputation.
        reserve=[g for g in games if g['source_player_id']==sample[7]['32']]
        self.assertEqual(sum(g['points'] for g in reserve),0);self.assertEqual(len(reserve),6)
        for s in sample:
            p=[g for g in games if g['source_player_id']==s['32']]
            self.assertEqual(sum(g['points'] for g in p),2*int(s['16'])+3*int(s['19'])+int(s['13']))
    def test_duplicate_and_missing_game_rejected(self):
        data=build.load()
        for altered in [data[4]+[data[4][0]],data[4][1:]]:
            with patch.object(build,'load',return_value=(*data[:4],altered,data[5])):
                with self.assertRaises(AssertionError):build.build()
    def test_source_and_sample_hash_guards(self):
        real_sha=build.sha
        for target,reason in [('player_games2018_compressed.bin','player_source_hash'),('fixed_source_sample.csv','sample_hash'),('torvik_2018.csv.gz','annual_source_hash'),('season2018.bin','team_source_hash')]:
            def changed(path):
                return '0'*64 if path.name==target else real_sha(path)
            with patch.object(build,'sha',side_effect=changed):
                with self.assertRaisesRegex(AssertionError,reason):build.load()
    def test_official_denominator_proof_and_no_blanket_claim(self):
        with contextlib.redirect_stdout(io.StringIO()):summary=build.build()
        self.assertEqual(summary['annual_shooting_count_exact_matches'],72)
        self.assertEqual(summary['annual_GP_exact_matches'],12)
        self.assertEqual(summary['official_all_game_pg_checks_matched'],10)
        self.assertEqual(summary['requests_used'],10)
        self.assertFalse(summary['model_eligible'])
        self.assertEqual([v['statistic'] for v in summary['official_team_total_checks'] if not v['equal']],['ast','blk'])
        with (build.R/'same_subset_basics_candidate.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),12);self.assertEqual(len(rows[0]),16)
        self.assertTrue(all(k.startswith('cgd_') for k in list(rows[0])[2:]))
        self.assertTrue(all(math.isfinite(float(v)) for r in rows for k,v in r.items() if k.startswith('cgd_')))
        self.assertTrue(all(int(r['source_season'])==2018 for r in rows))
if __name__=='__main__':unittest.main()
