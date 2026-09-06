"""Bounded eligibility-boundary tests; synthetic fixtures, no NBA outcomes."""
import copy
import unittest
import build

def event(name='A Prospect',status='declared_unresolved',date='2014-04-30',event_id='fixture1'):
    return dict(candidate_id=build.source_candidate_id(2014,name,'college'),draft_year=2014,
        player_name_source=name,name_normalized=build.norm(name),source_category='college',
        affiliation_source='Example College',status=status,evidence_available_date=date,
        event_id=event_id,source_id='synthetic_fixture')

class EligibilityBoundaries(unittest.TestCase):
    def test_initial_declaration_does_not_prove_final_eligibility(self):
        r=build.resolve_registry([event()],{2014:'2014-06-17'})[0]
        self.assertFalse(r['positive_eligibility_evidence'])
        self.assertEqual(r['eligibility_status'],'declared_unresolved')

    def test_withdrawal_and_known_as_of_dates(self):
        records=[event(),event(status='withdrawn',date='2014-06-17',event_id='fixture2')]
        earlier=build.resolve_registry(records,{2014:'2014-05-01'})[0]
        later=build.resolve_registry(records,{2014:'2014-06-17'})[0]
        self.assertEqual(earlier['eligibility_status'],'declared_unresolved')
        self.assertEqual(later['eligibility_status'],'withdrawn')
        self.assertFalse(later['positive_eligibility_evidence'])

    def test_future_record_cannot_change_earlier_registry(self):
        original=[event()]
        future=event(name='Future Prospect',status='eligible_final_early_entry',date='2014-06-17',event_id='future')
        self.assertEqual(build.resolve_registry(original,{2014:'2014-05-01'}),
                         build.resolve_registry(original+[future],{2014:'2014-05-01'}))

    def test_source_only_candidate_remains_without_player_key(self):
        registry=build.resolve_registry([event(status='eligible_final_early_entry')],{2014:'2014-06-17'})
        result=build.crosswalk_rows(registry,[])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['crosswalk_status'],'source_only_no_exact_match')
        self.assertTrue(registry[0]['positive_eligibility_evidence'])

    def test_ambiguous_name_is_not_certified(self):
        registry=build.resolve_registry([event()],{2014:'2014-06-17'})
        keys=[dict(pid='one',player_uid='source:one',player_name='A Prospect'),
              dict(pid='two',player_uid='source:two',player_name='A Prospect')]
        r=build.crosswalk_rows(registry,keys)[0]
        self.assertEqual(r['crosswalk_status'],'ambiguous')
        self.assertIsNone(r['suggested_pid'])
        self.assertFalse(r['identity_verified'])

    def test_nba_id_absence_does_not_change_crosswalk_or_inclusion(self):
        registry=build.resolve_registry([event()],{2014:'2014-06-17'})
        keys=[dict(pid='one',player_uid='source:one',player_name='A Prospect')]
        changed=copy.deepcopy(keys)
        changed[0]['nba_id']='forbidden_future_fixture'
        self.assertEqual(build.crosswalk_rows(registry,keys),build.crosswalk_rows(registry,changed))

    def test_same_date_conflict_remains_unresolved(self):
        records=[event(status='eligible_final_early_entry'),event(status='withdrawn',event_id='fixture2')]
        r=build.resolve_registry(records,{2014:'2014-06-17'})[0]
        self.assertEqual(r['eligibility_status'],'conflict_unresolved')
        self.assertFalse(r['positive_eligibility_evidence'])

    def test_cached_primary_lists_have_complete_asserted_section_counts(self):
        if not (build.ROOT/'private'/'final_web_response.txt').exists():
            self.skipTest('Private source views excluded from public bundle')
        events,sources=build.extract(build.ROOT/'private')
        finals=[x for x in events if x['status']=='eligible_final_early_entry']
        self.assertEqual(len(finals),56+60+57)
        self.assertEqual(sum(x['status']=='withdrawn' for x in events),11+18+18)
        self.assertEqual(len(events),67+78+75+77+75)
        self.assertTrue(all(x['claimed_published_date']<build.DRAFT_DATES[x['draft_year']] for x in sources))
        self.assertTrue(all(not x['source_copyright_body_public'] for x in sources))

if __name__=='__main__':
    unittest.main()
