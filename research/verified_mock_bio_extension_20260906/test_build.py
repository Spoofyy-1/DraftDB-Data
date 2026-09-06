"""Real archived cells, source chronology/identity, typed tokens and full pools."""
from pathlib import Path
import copy
import hashlib
import json
import math
import types
import numpy as np
import pandas as pd
import build as E

ROOT = Path(__file__).resolve().parent
P, B, sources, observations = E.load_inputs()
rows, provenance, cells_checked = [], [], 0
for source in sources:
    ff, pp, _ = E.extract_source(source, observations, P, B)
    rows += ff; provenance += pp; cells_checked += source['listed_count']
assert len(rows) == len(provenance) == 764 and cells_checked == 945
frame = pd.DataFrame(rows)
pd.testing.assert_frame_equal(frame, pd.read_csv(ROOT / 'source_observations.csv'), check_dtype=False, rtol=1e-14)
selected = E.choose_rows(frame)
assert len(selected) == selected.pid.nunique() == 600
assert E.choose_rows(frame.iloc[::-1]).equals(selected)
assert selected.loc[selected.draft_year >= 2018, 'vmb_age_reported_years'].isna().all()
finite_bmi = frame.vmb_listed_bmi.notna()
assert frame.loc[finite_bmi, ['vmb_listed_height_in', 'vmb_listed_weight_lb']].notna().all().all()
assert np.allclose(frame.loc[finite_bmi, 'vmb_listed_bmi'], frame.loc[finite_bmi, 'vmb_listed_weight_lb'] * .45359237 / (frame.loc[finite_bmi, 'vmb_listed_height_in'] * .0254) ** 2)
roles = frame[['vmb_position_' + p.lower() for p in E.POS]]
assert ((roles.notna().sum(axis=1) == 5) | (roles.notna().sum(axis=1) == 0)).all()
assert roles.stack().isin([0., 1.]).all()

positive, rejected, missing_cases = [], [], []
def reject(name, action):
    try:
        action()
    except (AssertionError, ValueError):
        rejected.append(name)
    else:
        raise AssertionError('Unsafe input accepted: ' + name)

values, info = E.typed_fields({'age': ' 20.25 ', 'height': '6\'8 ½"', 'weight': '200', 'position': 'PG / SG / SF', 'class': 'Junior'}, 'dx_table')
assert values['vmb_age_reported_years'] == 20.25 and info['reported_age_precision'] == .01
assert values['vmb_listed_height_in'] == 80.5 and values['vmb_college_class_year'] == 3
assert [values['vmb_position_' + p.lower()] for p in E.POS] == [1, 1, 1, 0, 0]
assert np.isclose(values['vmb_listed_bmi'], 200 * .45359237 / (80.5 * .0254) ** 2)
positive += ['decimal_age_precision', 'explicit_fractional_height', 'triple_position_indicators', 'same_row_bmi']
values, _ = E.typed_fields({'height': '6-4', 'weight': '190', 'position': 'PG/SG', 'class': 'Fr.'}, 'ndnet')
assert values['vmb_listed_height_in'] == 76 and values['vmb_listed_weight_lb'] == 190
assert math.isnan(values['vmb_age_reported_years']) and values['vmb_college_class_year'] == 1
positive.append('typed_ndnet_units_and_missing_age')
for field, bad in [('age', '-20'), ('age', '20/21'), ('age', '20.1.2'), ('age', '120'),
                   ('weight', '−200'), ('weight', '190 to 200'), ('weight', '200lbs'), ('weight', '600'),
                   ('height', '6-12'), ('height', '-6-8'), ('height', '16-8'), ('height', '6-8/6-9'),
                   ('position', 'PG SG'), ('position', 'PG/UNKNOWN'), ('position', 'PG/PG'), ('position', 'C/F'),
                   ('class', 'Fr./Sr.'), ('class', '1999')]:
    raw = {'age': '20', 'height': '6-8', 'weight': '200', 'position': 'PG', 'class': 'Fr.'}
    raw[field] = bad
    values, info = E.typed_fields(raw, 'ndnet')
    column = {'age': 'vmb_age_reported_years', 'height': 'vmb_listed_height_in', 'weight': 'vmb_listed_weight_lb', 'class': 'vmb_college_class_year'}.get(field)
    if field == 'position':
        assert all(math.isnan(values['vmb_position_' + p.lower()]) for p in E.POS)
    else:
        assert math.isnan(values[column])
    if field in ['height', 'weight']:
        assert math.isnan(values['vmb_listed_bmi'])
    assert field in info['issues']
    missing_cases.append(field + ':' + bad)
for raw in [{'height': '6-8'}, {'weight': '200'}, {'height': '', 'weight': '200'}]:
    assert math.isnan(E.typed_fields(raw, 'ndnet')[0]['vmb_listed_bmi'])
positive.append('missing_either_size_prevents_bmi')

# One better-populated lower-priority source cannot fill the preferred row.
a = E.typed_fields({'height': '6\'8"', 'position': 'PG'}, 'dx_table')[0]
b = E.typed_fields({'height': '6-10', 'weight': '210', 'position': 'SF', 'class': 'Sr.'}, 'ndnet')[0]
fixture = pd.DataFrame([{'pid': 'example', 'draft_year': 2017, 'source_id': 'dx_2017', 'publisher': 'dx', **a},
                        {'pid': 'example', 'draft_year': 2017, 'source_id': 'nbadraft_2017', 'publisher': 'nbadraft', **b}])
chosen = E.choose_rows(fixture).iloc[0]
assert chosen.source_id == 'dx_2017' and chosen.vmb_listed_height_in == 80
assert math.isnan(chosen.vmb_listed_weight_lb) and math.isnan(chosen.vmb_listed_bmi) and math.isnan(chosen.vmb_college_class_year)
positive.append('whole_row_priority_without_completeness_or_cross_source_fills')

by_id = {s['source_id']: s for s in sources}
base = by_id['nbadraft_2021']
def bad_source(key, value):
    source = copy.deepcopy(base); source[key] = value
    return E.extract_source(source, observations, P, B)
for key in ['html_sha256', 'table_sha256', 'rank_facts_sha256', 'archive_url', 'source_last_updated_date']:
    reject('source_' + key, lambda key=key: bad_source(key, 'changed'))
late = copy.deepcopy(base)
late['source']['timestamp'] = '20210730000000'; late['source_available_by_utc'] = '2021-07-30T00:00:00+00:00'
late['archive_url'] = f"https://web.archive.org/web/{late['source']['timestamp']}id_/{late['source']['original']}"
reject('self_consistent_postdraft_capture', lambda: E.extract_source(late, observations, P, B))
date2026 = copy.deepcopy(by_id['nbadraft_2026_fallback']); date2026['draft_date'] = '2026-06-24'
reject('incorrect_2026_first_draft_date', lambda: E.extract_source(date2026, observations, P, B))
index = observations.index[observations.source_id.eq(base['source_id'])][0]
for column in ['pid', 'draft_year', 'table_sha256', 'rank_facts_sha256', 'match_method', 'draft_date', 'capture_utc']:
    bad = observations.copy(); bad.loc[index, column] = 2018 if column == 'draft_year' else 'changed'
    reject('observation_' + column, lambda bad=bad: E.extract_source(base, bad, P, B))
parser_copy = types.SimpleNamespace(**vars(P)); parser_copy.PLAYERS = copy.deepcopy(P.PLAYERS)
subject = next(p for p in parser_copy.PLAYERS if p['pid'] == observations.loc[index, 'pid'])
parser_copy.PLAYERS.append({**subject, 'pid': 'second_identity'})
reject('ambiguous_same_cohort_identity', lambda: E.extract_source(base, observations, parser_copy, B))
source = by_id['nbadraft_2022']; _, tree, _ = P.read_tree(E.SOURCE / 'private' / 'nbadraft_2022.html')
duplicate = tree.xpath('//table[@id="nba_mock_consensus_table"]')[1]
duplicate.xpath('./tbody/tr/td|./tr/td')[4].text = '999'
reject('sticky_clone_measurement_disagreement', lambda: E.source_cells(tree, source, P))

identity = pd.DataFrame({'pid': ['missing', 'example'], 'draft_year': [2017, 2017]})
joined = E.join_identities(identity, E.choose_rows(fixture))
assert joined[['pid', 'draft_year']].equals(identity) and joined.iloc[0][E.FEATURES].isna().all()
positive.append('full_ordered_identity_left_join_with_explicit_missing_row')
wrong = identity.copy(); wrong.loc[1, 'draft_year'] = 2018
reject('pool_cohort_collision', lambda: E.join_identities(wrong, E.choose_rows(fixture)))
reject('duplicate_pool_pid', lambda: E.join_identities(pd.concat([identity, identity]), E.choose_rows(fixture)))
for year in range(2019, 2027):
    original = pd.read_csv(E.ORIGINAL / f'tests/test_{year}_inputs.csv', usecols=['pid', 'draft_year'])
    saved = pd.read_csv(ROOT / 'sidecars' / f'mock_bio_extension_test_{year}_inputs.csv')
    assert original.equals(saved[['pid', 'draft_year']])
    assert list(saved) == ['pid', 'draft_year'] + E.FEATURES
    pd.testing.assert_frame_equal(saved, E.join_identities(original, selected[selected.draft_year == year]), check_dtype=False, rtol=1e-14)
positive.append('all_eight_original_test_pools_and_numeric_left_joins')
unchanged = {}
for directory, filename in [(E.SOURCE, 'public_manifest.json'), (E.REVIEWED, 'PUBLIC_ALLOWLIST.json')]:
    public = json.loads((directory / filename).read_text())
    assert all(E.sha(directory / name) == row['sha256'] for name, row in public['files'].items())
    unchanged[directory.name] = len(public['files'])
report = {'status': 'passed_no_models_or_network', 'source_tables': len(sources), 'source_cells_checked': cells_checked,
          'source_observations_replayed': len(rows), 'selected_players': len(selected), 'features': len(E.FEATURES),
          'positive_checks': positive, 'ambiguous_field_cases_left_missing': missing_cases,
          'adversarial_source_pool_cases_rejected': rejected, 'pinned_source_files_unchanged': unchanged,
          'builder_sha256': E.sha(ROOT / 'build.py'), 'tests_sha256': E.sha(Path(__file__)),
          'models_or_outcomes_used': False, 'network_calls': 0, 'r8t_files_modified': False}
(ROOT / 'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
