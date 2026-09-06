"""No fitting/outcomes: membership dates, coverage, isolation and identity gaps."""
import copy
import unittest
import build

def fixture_registry(year):
    return [dict(candidate_id=f'fixture_{year}_{i}',draft_year=year,
                 membership_available_date=build.HR_DATES[year]) for i in range(60)]

class PriorDraftBoundaryTests(unittest.TestCase):
    def test_current_and_future_cohorts_excluded(self):
        rows=fixture_registry(2012)+fixture_registry(2013)+fixture_registry(2014)
        selected=build.model_row_index(rows,2014,'2013-12-31')
        self.assertEqual(len(selected),120)
        self.assertEqual({r['draft_year'] for r in selected},{2012,2013})

    def test_membership_not_available_before_actual_release(self):
        self.assertEqual(build.model_row_index(fixture_registry(2014),2015,'2014-06-25'),[])
        self.assertEqual(len(build.model_row_index(fixture_registry(2014),2015,'2014-06-27')),60)

    def test_draft_positions_and_order_do_not_enter_model_index(self):
        original=fixture_registry(2014)
        changed=copy.deepcopy(original)
        for i,row in enumerate(changed):
            row.update(actual_pick=60-i,actual_round=2,source_text_line=1000-i,player_name='forbidden predictor')
        changed.reverse()
        self.assertEqual(build.model_row_index(original,2015,'2014-12-31'),build.model_row_index(changed,2015,'2014-12-31'))
        self.assertEqual(set(build.model_row_index(changed,2015,'2014-12-31')[0]),{'candidate_id','draft_year'})

    def test_partial_or_duplicate_source_roster_rejected(self):
        good=[dict(actual_pick=i,player_name=f'Fixture Player {i}') for i in range(1,61)]
        build.validate_picks(good,2014)
        with self.assertRaises(ValueError):build.validate_picks(good[:-1],2014)
        changed=copy.deepcopy(good);changed[-1]['actual_pick']=59
        with self.assertRaises(ValueError):build.validate_picks(changed,2014)
        with self.assertRaises(ValueError):build.model_row_index(fixture_registry(2014)[:-1],2015,'2014-12-31')

    def test_no_out_of_scope_years(self):
        with self.assertRaises(ValueError):build.validate_picks([],2019)
        with self.assertRaises(ValueError):build.model_row_index([dict(draft_year=2019)],2020,'2019-12-31')

    def test_missing_identity_and_training_do_not_drop_member(self):
        rows=[dict(candidate_id='fixture',draft_year=2014)]
        aliases=[dict(candidate_id='fixture',name_normalized='sourceonly')]
        result=build.identity_crosswalk(rows,aliases,[],[],set())
        self.assertEqual(len(result),1)
        self.assertIsNone(result[0]['suggested_pid'])
        self.assertEqual(result[0]['gap_status'],'no_legacy_same_cohort_name_match')

    def test_ambiguous_name_remains_unresolved(self):
        rows=[dict(candidate_id='fixture',draft_year=2014)]
        aliases=[dict(candidate_id='fixture',name_normalized='person')]
        keys=[dict(pid='one',player_name='Person'),dict(pid='two',player_name='Person')]
        result=build.identity_crosswalk(rows,aliases,keys,[],set())
        self.assertIsNone(result[0]['suggested_pid'])
        self.assertFalse(result[0]['identity_verified'])

    def test_source_local_id_is_independent_of_pick_and_nba_id(self):
        self.assertEqual(build.candidate_id(2014,'Danté Exum'),build.candidate_id(2014,'Dante Exum'))
        self.assertNotEqual(build.candidate_id(2013,'A Person'),build.candidate_id(2014,'A Person'))

    def test_real_source_pair_has_all_180_selected_players(self):
        if not (build.ROOT/'private'/'hr_2012_2013_indexed.txt').exists():
            self.skipTest('Private source views excluded from public bundle')
        results,sources=build.get_sources(build.ROOT/'private')
        registry,protected,aliases=build.make_registry(results)
        self.assertEqual(len(registry),180)
        self.assertEqual(len(sources),6)
        self.assertEqual(len(protected),180)
        self.assertEqual(len({r['candidate_id'] for r in registry}),180)
        self.assertEqual(len(build.model_row_index(registry,2015,'2014-12-31')),180)

if __name__=='__main__':unittest.main()
