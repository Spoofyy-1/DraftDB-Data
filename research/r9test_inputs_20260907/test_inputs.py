"""Input-only boundary fixtures. No model, outcomes, or scoring imports."""
import collections, copy, csv, json, unittest
import numpy as np
import build as B
class Inputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((B.ROOT/'manifest.json').read_text())
        cls.traces=[t for t in json.loads((B.WORK/'fifty_audit/source_row_lineage.json').read_text()) if t['draft_year']<=2025]
        cls.raw=B.raw_lookup(cls.traces,json.loads((B.WORK/'fifty/manifest.json').read_text())['source_hashes'])
    def test_schema_pool_metadata_and_hash(self):
        allids=[]
        for year in B.YEARS:
            p=B.ROOT/f'inputs_{year}.csv';r=B.rows(p);pool=B.rows(B.WORK/f'verified_inputs_v2/{year}_inputs.csv',['pid','draft_year'])
            self.assertEqual(list(r[0]),['pid','draft_year']+self.m['columns']);self.assertEqual([(v['pid'],v['draft_year']) for v in r],[(v['pid'],v['draft_year']) for v in pool])
            self.assertEqual(B.digest(p.read_bytes()),self.m['output_files'][p.name]['sha256']);allids += [v['pid'] for v in r]
            meta=B.rows(B.ROOT/f'metadata_{year}.csv');self.assertEqual([v['pid'] for v in meta],[v['pid'] for v in pool]);self.assertEqual(set(meta[0]),{'pid','draft_year','was_drafted'})
            self.assertTrue(all(v['was_drafted'] in ['0','1'] for v in meta));self.assertTrue(all(int(v['draft_year'])==year for v in meta))
        self.assertEqual(len(allids),len(set(allids)))
    def test_no_future_or_stale_history(self):
        t=copy.deepcopy(next(t for t in self.traces if t['draft_year']==2019));B.validate_trace(t,2019)
        with self.assertRaises(AssertionError):B.validate_trace(t,2018)
        for change in ['future','wrong_identity','duplicate_history','stale']:
            z=copy.deepcopy(t)
            if change=='future':z['history'][0]['season']=2020
            if change=='wrong_identity':z['history'][0]['tpid']='UNVERIFIED'
            if change=='duplicate_history':z['history'].append(copy.deepcopy(z['history'][0]))
            if change=='stale':z['draft_year']=z['focal']['season']+2
            with self.assertRaises(AssertionError):B.validate_trace(z,2025)
    def test_earlier_input_independent_of_future_sources(self):
        # Remove every later source year, then rebuild every selected earlier cohort row.
        for cutoff in [2019,2021,2023]:
            limited={k:v for k,v in self.raw.items() if int(k[0].split('_')[1].split('.')[0])<=cutoff}
            for t in self.traces:
                if t['draft_year']>cutoff:continue
                a=B.reconstruct(t,self.raw);b=B.reconstruct(t,limited)
                self.assertEqual(B.matrix_hash([[a[k] for k in sorted(a)]]),B.matrix_hash([[b[k] for k in sorted(b)]]))
    def test_mock_cutoff_and_identity_guards(self):
        sources={s['source_id']:s for s in json.loads((B.WORK/'verified_consensus_extension/validated_sources.json').read_text())}
        s=next(s for s in sources.values() if s['draft_year']==2019 and s['feature_eligible']);B.validate_source(s)
        for kind in ['capture','same_day_update','wrong_cutoff','quarantine']:
            z=copy.deepcopy(s)
            if kind=='capture':z['source_available_by_utc']=z['cutoff_utc']
            if kind=='same_day_update':z['source_last_updated_date']=z['draft_date']
            if kind=='wrong_cutoff':z['cutoff_utc']='2019-06-21T04:00:00+00:00'
            if kind=='quarantine':z['feature_eligible']=False
            with self.assertRaises(AssertionError):B.validate_source(z)
        obs=B.rows(B.WORK/'verified_consensus_extension/rank_observations.csv');first=next(r for r in obs if r['draft_year']=='2019')
        with self.assertRaises(AssertionError):B.consensus_for_year(2019,obs+[first],sources)
    def test_missing_remains_missing(self):
        traces={t['pid']:t for t in self.traces};sources={s['source_id']:s for s in json.loads((B.WORK/'verified_consensus_extension/validated_sources.json').read_text())};obs=B.rows(B.WORK/'verified_consensus_extension/rank_observations.csv')
        for year in B.YEARS:
            cons=B.consensus_for_year(year,obs,sources)
            for r in B.rows(B.ROOT/f'inputs_{year}.csv'):
                if r['pid'] not in traces:self.assertTrue(all(r[c]=='' for c,p in zip(self.m['columns'],self.m['physical_source_fields']) if not p.startswith('vcons_')))
                if r['pid'] not in cons:self.assertTrue(all(r[c]=='' for c,p in zip(self.m['columns'],self.m['physical_source_fields']) if p.startswith('vcons_')))
                if r['pid'] in cons and cons[r['pid']]['vcons_mock_n_sources']==1:self.assertEqual(r['slot_039'],'')
    def test_raw_hash_tamper_rejected(self):
        hashes=json.loads((B.WORK/'fifty/manifest.json').read_text())['source_hashes'];t=self.traces[0];hashes[t['focal']['source']]='0'*64
        with self.assertRaises(AssertionError):B.raw_lookup([t],hashes)
if __name__=='__main__':unittest.main()
