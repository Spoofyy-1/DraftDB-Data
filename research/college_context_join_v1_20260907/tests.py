import copy,json,unittest
from unittest.mock import patch
import build
class Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=build.load();cls.output,cls.prov,_,_=build.project(cls.data)
    def test_full_pool_original_strings_and_order(self):
        base=self.data[0];saved=build.rows(build.R/'private/full_pool_with_candidates.csv');out=build.rows(build.R/'candidate_inputs.csv')
        self.assertEqual(len(base),1458);self.assertEqual(len(out),1458);self.assertEqual(len(saved[0]),574)
        self.assertEqual([(x['pid'],x['draft_year']) for x in base],[(x['pid'],x['draft_year']) for x in out])
        self.assertEqual(out,self.output)
        for a,b in zip(base,saved):self.assertEqual(list(a.values()),[b[k] for k in a])
        self.assertEqual(len({x['pid'] for x in out}),1458)
    def test_missingness_and_group_gate(self):
        gc=tc=0
        for r,p in zip(self.output,self.prov):
            g=[bool(r[c]) for c in build.GAME_COLS];t=[bool(r[c]) for c in self.data[9]]
            self.assertIn(sum(g),[0,15]);self.assertIn(sum(t),[0,20]);self.assertFalse(p['model_eligible'])
            self.assertEqual(all(g),p['game_join_reason'] is None);self.assertEqual(all(t),p['team_join_reason'] is None)
            gc+=all(g);tc+=all(t)
        self.assertEqual((gc,tc),(670,624))
        self.assertEqual(sum(p['game_join_reason']=='no_verified_focal_college_lineage' for p in self.prov),787)
    def test_actual_temporal_boundaries(self):
        for p in self.prov:
            for family in ['player','team']:
                if family+'_game_max_date' in p:
                    self.assertLess(p[family+'_game_max_date'],p['registered_draft_date']);self.assertLessEqual(p['source_season'],p['draft_year'])
        cuts=self.data[2]
        self.assertIsNotNone(build.source_date_status(2013,2012,'2012-11-01','2013-03-01',cuts))
        self.assertIsNotNone(build.source_date_status(2012,2012,'2011-11-01','2012-06-28',cuts))
        self.assertIsNotNone(build.source_date_status(2012,2012,'2011-11-01',None,cuts))
        self.assertIsNotNone(build.source_date_status(2012,2012,'2011-11-01','2012-03-01',{}))
    def test_future_source_removal_does_not_change_earlier_cohorts(self):
        capped=build.load(max_season=2014);earlier,_,_,_=build.project(capped,max_draft_year=2014)
        expected=[x for x in self.output if int(x['draft_year'])<=2014]
        self.assertEqual(earlier,expected);self.assertEqual(build.digest(earlier),build.digest(expected))
        self.assertFalse(any(int(x['source_season'])>2014 for x in capped[3].values()))
    def test_quarantined_group_and_provenance_tamper(self):
        base,ld,cuts,audits,candidates,entries,*_=self.data
        p=next(p for p in self.prov if p['game_join_reason'] is None);f=ld[p['pid']]['focal'];season=f['season'];key=(season,build.subject(season,f['tpid'],f['team']));a=audits[key];c=candidates[key]
        self.assertIsNone(build.game_status(f,p['draft_year'],a,c,entries[season],cuts))
        for field,val in [('source_consistent',False),('annual_source_row_zero_based',-1),('game_date_max',None),('source_sha256','0'*64)]:
            changed=dict(a);changed[field]=val;self.assertIsNotNone(build.game_status(f,p['draft_year'],changed,c,entries[season],cuts))
        changed=dict(c);changed['cgd_tov_pg']=str(float(c['cgd_tov_pg'])+1);self.assertIsNotNone(build.game_status(f,p['draft_year'],a,changed,entries[season],cuts))
        self.assertIsNotNone(build.game_status(f,p['draft_year'],None,c,entries[season],cuts))
    def test_hash_and_duplicate_key_rejection(self):
        original=build.sha
        with patch.object(build,'sha',side_effect=lambda p:'0'*64 if p==build.POOL else original(p)):
            with self.assertRaisesRegex(AssertionError,'source_hash_changed'):build.verify_inputs()
        with self.assertRaisesRegex(AssertionError,'duplicate_join_key'):build.keyed([{'pid':'a'},{'pid':'a'}],lambda r:r['pid'])
    def test_candidate_schema_excludes_inherited_metadata(self):
        self.assertEqual(list(self.output[0]),['pid','draft_year']+build.GAME_COLS+self.data[9])
        self.assertNotIn('actual_pick',self.output[0]);self.assertNotIn('was_drafted',self.output[0])
        comparison=json.loads((build.R/'overlap_with_source41.json').read_text());self.assertEqual(len(comparison['source41_columns']),41);self.assertFalse(comparison['outcomes_or_model_results_used'])
if __name__=='__main__':unittest.main()
