"""Bounded independent fixtures plus full generated-output integrity audit."""
import collections,copy,csv,datetime as dt,gzip,json,math,unittest
from pathlib import Path
from unittest.mock import patch
import build
class UnitChecks(unittest.TestCase):
    def raw(self):
        row=[None]*53
        for i in build.COUNTS:row[i]=0
        for i,v in {0:'20111110',5:'Other',6:'fixture_game',47:'College',48:'Player',51:123,52:2012,23:2,24:5,25:1,26:3,27:2,28:4,33:9,34:2,35:3,36:4,37:5,38:1,39:1,42:2}.items():row[i]=v
        return row
    def fixture(self):
        key,g=build.parse(self.raw(),2012)
        a={'gp':1,**{n:g[n] for n in build.SIX},'name':'Player','source_row_zero_based':0}
        return key,g,a
    def test_algebra_independently(self):
        _,g=build.parse(self.raw(),2012);self.assertEqual(g['points'],9);self.assertEqual(g['tov'],5);self.assertEqual(g['pf'],2)
    def test_ignored_indices_cannot_influence(self):
        row=self.raw();expected=build.parse(row,2012)
        for i in set(range(53))-set(build.READ_INDICES):row[i]={'unread':'arbitrary future-rating text'}
        self.assertEqual(build.parse(row,2012),expected);self.assertNotIn(45,build.READ_INDICES);self.assertNotIn(45,build.ANNUAL)
    def test_invalid_counts(self):
        for idx,value in [(33,10),(23,6),(25,4),(27,5),(42,6),(37,-1),(34,.5),(35,float('nan')),(36,float('inf')),(38,True)]:
            row=self.raw();row[idx]=value
            with self.assertRaises((AssertionError,ValueError)):build.parse(row,2012)
    def test_dates_years_width_identity(self):
        for idx,value in [(0,'20120601'),(0,'20110630'),(0,'20191301'),(0,'20110229'),(52,2013),(51,0),(47,'Other')]:
            row=self.raw();row[idx]=value
            with self.assertRaises((AssertionError,ValueError)):build.parse(row,2012)
        with self.assertRaises(AssertionError):build.parse(self.raw()[:-1],2012)
        with self.assertRaises(AssertionError):build.parse(self.raw(),2019)
    def test_annual_counts_gate_every_field(self):
        key,g,a=self.fixture();self.assertEqual(build.assess_group(key,[g],[a],set())[2],[])
        for n in ['gp',*build.SIX]:
            changed=dict(a);changed[n]+=1
            self.assertIn(n+'_disagreement',build.assess_group(key,[g],[changed],set())[2])
        self.assertIn('duplicate_annual_rows',build.assess_group(key,[g],[a,a],set())[2])
        self.assertIn('missing_annual_row',build.assess_group(key,[g],[],set())[2])
        bad=dict(a);bad['name']='Different';self.assertIn('annual_game_name_disagreement',build.assess_group(key,[g],[bad],set())[2])
    def test_duplicate_and_ambiguous_games_block_whole_group(self):
        key,g,a=self.fixture();records,bad,n=build.group_records([(key,g),(key,copy.deepcopy(g))]);self.assertEqual(n,2);self.assertIn('duplicate_player_game',bad[key])
        changed=dict(g);changed['opponent']='Another';changed['raw_game_id']='another_game'
        _,bad,_=build.group_records([(key,g),(key,changed)]);self.assertIn('player_date_multiple_teams_or_opponents',bad[key])
        self.assertIn('invalid_game_record',build.assess_group(key,[g],[a],{'invalid_game_record'})[2])
    def test_zero_is_observed_missing_is_missing(self):
        key,g,a=self.fixture()
        for n in build.COUNTS.values():g[n]=0
        for n in build.SIX:a[n]=0
        gp,total,reasons=build.assess_group(key,[g],[a],set());self.assertEqual((gp,reasons),(1,[]));self.assertTrue(all(v==0 for v in total.values()))
        self.assertIn('no_valid_game_records',build.assess_group(key,[],[a],set())[2])
    def test_invalid_annual_duplicate_identity_is_retained(self):
        row=['IGNORED']*67
        values={0:'Player',1:'College',3:'1',13:'2',14:'4',16:'2',17:'5',19:'1',20:'3',31:'2012',32:'123'}
        for i,v in values.items():row[i]=v
        bad=list(row);bad[17]='NaN'
        groups,invalid=build.parse_annual_records([row,bad],2012)
        key=(2012,'123','College');self.assertEqual(len(groups[key]),1);self.assertEqual(len(invalid),1)
        self.assertEqual(invalid[0]['source_subject_id'],build.hashed('subject',*key))
        bad_groups=collections.defaultdict(set);self.assertFalse(build.apply_annual_issues(groups,invalid,bad_groups))
        _,g,a=self.fixture();self.assertIn('invalid_annual_record',build.assess_group(key,[g],groups[key],bad_groups[key])[2])
        groups,invalid=build.parse_annual_records([bad],2012);self.assertIn(key,groups);self.assertEqual(groups[key],[])
        malformed=list(row);malformed[32]='NaN';_,invalid=build.parse_annual_records([malformed],2012);self.assertIsNone(invalid[0]['source_subject_id']);self.assertTrue(build.apply_annual_issues(groups,invalid,collections.defaultdict(set)))
    def test_scope_and_hash_tamper_before_reads(self):
        e=copy.deepcopy(build.freeze_manifest()['sources'][0]);e['sha256']='0'*64
        with self.assertRaisesRegex(AssertionError,'game_source_changed'):build.build_year(e)
        e=copy.deepcopy(build.freeze_manifest()['sources'][0]);e['annual_source']['sha256']='0'*64
        with self.assertRaisesRegex(AssertionError,'annual_source_changed'):build.annual_rows(e)
        e['source_season']=2019
        with patch.object(build,'sha',side_effect=AssertionError('Unexpected source read')):
            with self.assertRaisesRegex(AssertionError,'outside_year_scope'):build.build_year(e)
            with self.assertRaisesRegex(AssertionError,'outside_year_scope'):build.annual_rows(e)
        e=copy.deepcopy(build.freeze_manifest()['sources'][0]);e['path']='../outcomes.csv'
        with patch.object(build,'sha',side_effect=AssertionError('Unexpected source read')):
            with self.assertRaisesRegex(AssertionError,'game_path_scope'):build.build_year(e)

class FullOutputChecks(unittest.TestCase):
    def test_every_projection_and_candidate(self):
        manifest=build.freeze_manifest();cov={x['source_season']:x for x in json.loads((build.R/'coverage.json').read_text())}
        self.assertEqual(set(cov),set(range(2008,2019)))
        checked_games=checked_groups=consistent=0
        for e in manifest['sources']:
            year=e['source_season'];summed=collections.defaultdict(lambda:collections.Counter());seen=set();dates={};group_keys={}
            with gzip.open(build.R/'data'/f'games_{year}.csv.gz','rt',newline='') as f:
                for row in csv.DictReader(f):
                    subject=row['source_subject_id'];idx=int(row['source_row_zero_based']);self.assertNotIn(idx,seen);seen.add(idx)
                    self.assertEqual(row['source_sha256'],e['sha256']);self.assertEqual(int(row['source_season']),year)
                    date=dt.date.fromisoformat(row['game_date']);self.assertTrue(dt.date(year-1,7,1)<=date<=dt.date(year,5,31))
                    counts={n:int(row[n]) for n in build.COUNTS.values()};self.assertEqual(2*counts['two_m']+3*counts['three_m']+counts['ft_m'],counts['points']);self.assertTrue(all(v>=0 for v in counts.values()))
                    summed[subject].update(counts);summed[subject]['gp']+=1;checked_games+=1
            self.assertEqual(len(seen),cov[year]['valid_parsed_game_rows'])
            audit=json.loads(gzip.decompress((build.R/'data'/f'audit_{year}.json.gz').read_bytes()));byid={x['source_subject_id']:x for x in audit};self.assertEqual(len(byid),len(audit))
            with (build.R/'data'/f'candidates_{year}.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),len(audit));self.assertEqual(len({x['source_subject_id'] for x in rows}),len(rows))
            self.assertEqual(len(rows[0]),18);self.assertTrue(all(k.startswith('cgd_') for k in list(rows[0])[3:]))
            for row in rows:
                a=byid[row['source_subject_id']];s=summed[row['source_subject_id']];self.assertFalse(a['model_eligible']);self.assertEqual(a['valid_parsed_game_rows'],s['gp'])
                self.assertEqual(a['direct_game_totals'],{n:s[n] for n in build.COUNTS.values()})
                if a['source_consistent']:
                    self.assertEqual(a['quarantine_reasons'],[]);self.assertEqual(a['annual_gp'],s['gp']);self.assertEqual(float(row['cgd_observed_gp']),s['gp'])
                    for n in build.SIX:self.assertEqual(a['annual_six_counts'][n],s[n])
                    for n in build.COUNTS:self.assertTrue(n in build.READ_INDICES)
                    for n in build.COUNTS.values():self.assertEqual(float(row['cgd_'+n+'_pg']),s[n]/s['gp'])
                    consistent+=1
                else:self.assertTrue(a['quarantine_reasons']);self.assertTrue(all(v=='' for k,v in row.items() if k.startswith('cgd_')))
                checked_groups+=1
            quarantined=json.loads(gzip.decompress((build.R/'data'/f'quarantine_games_{year}.json.gz').read_bytes()));bad_indices={x['source_row_zero_based'] for x in quarantined}
            self.assertFalse(seen&bad_indices);self.assertEqual(len(seen)+len(bad_indices),e['rows'])
        self.assertEqual(checked_games,sum(x['valid_parsed_game_rows'] for x in cov.values()))
        self.assertEqual(checked_groups,sum(x['source_player_team_seasons'] for x in cov.values()))
        self.assertEqual(consistent,sum(x['source_consistent_player_team_seasons'] for x in cov.values()))
        print(' Full projection audit:',checked_games,'games;',checked_groups,'groups;',consistent,'consistent')
    def test_frozen12_player_pilot_reproduced(self):
        old=build.REF
        with (old/'same_subset_basics_candidate.csv').open() as f:oldrows={x['source_subject_id']:x for x in csv.DictReader(f)}
        identities=json.loads((old/'private/identity_crosswalk.json').read_text())
        with (build.R/'data/candidates_2018.csv').open() as f:new={x['source_subject_id']:x for x in csv.DictReader(f)}
        for ident in identities:
            key=build.hashed('subject',2018,ident['raw_player_id'],ident['source_team']);a=new[key];b=oldrows[ident['source_subject_id']]
            self.assertEqual(float(a['cgd_observed_gp']),ident['annual_gp'])
            for n in build.COUNTS.values():self.assertEqual(float(a['cgd_'+n+'_pg']),float(b['cgd_'+n+'_pg']))
if __name__=='__main__':unittest.main()
