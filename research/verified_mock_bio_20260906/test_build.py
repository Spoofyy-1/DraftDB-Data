"""Independent archive/cell/identity checks; no models or NBA outcomes."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import math
import tempfile
import types
import numpy as np
import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mock_bio_builder', ROOT / 'build.py')
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
P, sources, observations = B.load_verified_inputs()
verified = {s['draft_year']: s for s in sources if s['publisher'] == 'dx' and s['feature_eligible']}
assert set(verified) == set(range(2007, 2015))
checks, rejected = [], []


def reject(name, operation):
    try:
        operation()
    except (AssertionError, ValueError):
        rejected.append(name)
    else:
        raise AssertionError('Unsafe input accepted: ' + name)


def cell(tail, href='/profile/Example-Player-1/', name='Example Player'):
    return html.fromstring('<td><a href="' + href + '">' + name + '</a> ' + tail + '</td>')


# Both actual archived layouts/profile-link conventions, with explicit values.
rows, lineage, named = [], [], {}
for year, source in verified.items():
    facts, provenance, _ = B.extract_source(source, observations, P)
    assert len(facts) == source['matched_players']
    rows.extend(facts); lineage.extend(provenance)
    _, tree, encoding = P.source_tree(B.SOURCE / 'private' / f'dx_{year}.html')
    ranks, _, _, _, body = P.parse_dx(tree, year)
    cells = []
    for table in html.fragments_fromstring(body.decode(encoding)):
        for row in table.xpath('./tr|./tbody/tr'):
            td = row.xpath('./td')
            if len(td) >= 3 and P.txt(td[0]).rstrip('.').isdigit():
                cells.append(td[2])
    assert len(cells) == 60 and [r['rank'] for r in ranks] == list(range(1, 61))
    for rank, (element, ranking) in enumerate(zip(cells, ranks), 1):
        values, info = B.parse_cell(element)
        assert info['name'] == ranking['source_name'] and info['profile_href'] == ranking['profile_href']
        named[(year, info['name'])] = values, info
    checks.append('full_60_row_boundary_' + str(year))
assert len(rows) == 374 and len({r['pid'] for r in rows}) == 374
matched_count = len(rows)
for year, name, age, height, weight in [(2007, 'Greg Oden', 19., 84., 257.),
                                      (2007, 'Kevin Durant', 18., 82., 215.),
                                      (2014, 'Andrew Wiggins', 19.3, 80., 197.)]:
    fact, info = named[(year, name)]
    assert fact['vmb_age_reported_years'] == age and fact['vmb_listed_height_in'] == height and fact['vmb_listed_weight_lb'] == weight
    assert np.isclose(fact['vmb_listed_bmi'], weight * .45359237 / (height * .0254) ** 2)
    assert info['reported_age_precision'] == (1.0 if year == 2007 else .1)
checks += ['known_2007_facts', 'known_2014_facts_and_age_precision']
for name in ['Jamont Gordon', 'Anton Ponkrashov']:
    fact, _ = named[(2008, name)]
    assert [fact['vmb_position_' + p] for p in ['pg', 'sg', 'sf', 'pf', 'c']] == [1., 1., 1., 0., 0.]
fact, _ = named[(2010, 'Nemanja Bjelica')]
assert fact['vmb_position_sf'] == 1.0
checks.append('all_explicit_triple_positions_retained')
for year, name in [(2009, 'B.J. Mullens'), (2010, 'Tiny Gallon')]:
    fact, info = named[(year, name)]
    assert math.isnan(fact['vmb_age_reported_years']) and info['reported_age_precision'] is None
checks.append('actual_blank_age_placeholders_remain_missing')
for (year, name), (fact, _) in named.items():
    if name == 'Dante Exum' and year == 2014:
        assert math.isnan(fact['vmb_college_class_year'])
        checks.append('international_class_remains_missing')
assert 'international_class_remains_missing' in checks

for href in ['/profile/Example-Player-1/', 'viewprofile.php?p=1', 'http://www.draftexpress.com:80/viewprofile.php?p=1']:
    facts, info = B.parse_cell(cell('PG / SG 20.25 years old; 6\'8"; 200 lbs. International', href))
    assert info['profile_href'] == href and info['reported_age_precision'] == .01
    assert facts['vmb_position_pg'] == facts['vmb_position_sg'] == 1
    assert math.isnan(facts['vmb_college_class_year'])
checks.append('old_new_profile_source_aliases_and_decimal_precision')
# Empty/unknown fields retain NaN. Height/weight are never taken from another cell.
for tail in ['PG 20 years old; 200 lbs.', 'PG 20 years old; 6\'8";', 'PG years old; 6\'8"; lbs.']:
    facts, _ = B.parse_cell(cell(tail))
    assert math.isnan(facts['vmb_listed_bmi'])
checks.append('missing_either_measurement_means_missing_bmi')
parent = html.fromstring('<tr><td><a href="/profile/Example-Player-1/">Example Player</a> PG 20 years old; 6\'8";</td><td>200 lbs. 99 PPG 2050 NBA</td></tr>')
assert math.isnan(B.parse_cell(parent.xpath('./td')[0])[0]['vmb_listed_bmi'])
checks.append('adjacent_statistics_or_measurements_not_read')
missing_position, _ = B.parse_cell(cell('Unknown 20 years old; 6\'8"; 200 lbs. International'))
assert all(math.isnan(missing_position['vmb_position_' + p.lower()]) for p in B.POS)
checks.append('unknown_position_not_invented')

bad_cells = {
    'negative_age': 'PG -20 years old; 6\'8"; 200 lbs.',
    'unicode_negative_age': 'PG −20 years old; 6\'8"; 200 lbs.',
    'ambiguous_age_range': 'PG 20/21 years old; 6\'8"; 200 lbs.',
    'word_age_range': 'PG 20 to 21 years old; 6\'8"; 200 lbs.',
    'duplicate_age': 'PG 20 years old; 21 years old; 6\'8"; 200 lbs.',
    'partial_decimal_age': 'PG 20.1.2 years old; 6\'8"; 200 lbs.',
    'implausible_age': 'PG 120 years old; 6\'8"; 200 lbs.',
    'negative_height': 'PG 20 years old; -6\'8"; 200 lbs.',
    'truncated_height_digits': 'PG 20 years old; 16\'8"; 200 lbs.',
    'invalid_inches': 'PG 20 years old; 6\'12"; 200 lbs.',
    'two_heights': 'PG 20 years old; 6\'8" or 6\'9"; 200 lbs.',
    'negative_weight': 'PG 20 years old; 6\'8"; -200 lbs.',
    'weight_range': 'PG 20 years old; 6\'8"; 190/200 lbs.',
    'duplicate_weight': 'PG 20 years old; 6\'8"; 200 lbs. 210 lbs.',
    'unknown_position_suffix': 'PG/UNKNOWN 20 years old; 6\'8"; 200 lbs.',
    'unsupported_combo_position': 'C/F 20 years old; 6\'8"; 200 lbs.',
    'duplicate_position': 'PG/PG 20 years old; 6\'8"; 200 lbs.',
    'ambiguous_separated_position': 'PG SG 20 years old; 6\'8"; 200 lbs.',
    'position_slash_without_role': 'PG/ 20 years old; 6\'8"; 200 lbs.',
    'conflicting_class': 'PG 20 years old; 6\'8"; 200 lbs. Freshman Senior',
}
for name, tail in bad_cells.items():
    reject(name, lambda tail=tail: B.parse_cell(cell(tail)))
ambiguous = cell('PG 20 years old; 6\'8"; 200 lbs.')
ambiguous.append(copy.deepcopy(ambiguous.xpath('.//a')[0]))
reject('two_subject_profile_links', lambda: B.parse_cell(ambiguous))

# Source/calendar/hash and the already validated identity join are independently checked.
source = verified[2007]
def changed_source(key, value):
    modified = copy.deepcopy(source); modified[key] = value
    return B.extract_source(modified, observations, P)
reject('future_archive_capture', lambda: changed_source('source_available_by_utc', '2026-01-01T00:00:00+00:00'))
late = copy.deepcopy(source)
late['source']['timestamp'] = '20070629000000'
late['source_available_by_utc'] = '2007-06-29T00:00:00+00:00'
late['archive_url'] = f"https://web.archive.org/web/{late['source']['timestamp']}id_/{late['source']['original']}"
reject('self_consistent_postdraft_capture', lambda: B.extract_source(late, observations, P))
reject('wrong_html_hash', lambda: changed_source('html_sha256', '0' * 64))
reject('wrong_table_hash', lambda: changed_source('table_sha256', '0' * 64))
reject('wrong_rank_fact_hash', lambda: changed_source('rank_facts_sha256', '0' * 64))
reject('wrong_published_update_date', lambda: changed_source('source_last_updated_date', '2007-06-21'))
reject('wrong_archive_url', lambda: changed_source('archive_url', 'https://web.archive.org/web/20200101000000id_/http://www.draftexpress.com/'))
changed = observations.copy(); index = changed.index[changed.source_id.eq('dx_2007')][0]
changed.loc[index, 'pid'] = 'incorrect_identity'
reject('rank_to_pid_substitution', lambda: B.extract_source(source, changed, P))
for column in ['table_sha256', 'rank_facts_sha256', 'match_method', 'draft_date']:
    bad = observations.copy(); bad.loc[index, column] = 'changed'
    reject('observation_' + column, lambda bad=bad: B.extract_source(source, bad, P))
parser_copy = types.SimpleNamespace(**{k: getattr(P, k) for k in ['source_tree', 'parse_dx', 'txt', 'norm']})
allowed = [{k: p[k] for k in ['pid', 'name', 'draft_year', 'draft_date']} for p in P.PLAYERS]
parser_copy.PLAYERS = copy.deepcopy(allowed)
subject = next(p for p in parser_copy.PLAYERS if p['pid'] == observations.loc[index, 'pid'])
subject['name'] = 'GREG. ODEN'
assert B.extract_source(source, observations, parser_copy)[0] == B.extract_source(source, observations, P)[0]
checks.append('same_validated_normalization_rule_reused')
subject['name'] = 'Gregory Oden'
reject('new_name_alias_not_silently_joined', lambda: B.extract_source(source, observations, parser_copy))
parser_copy.PLAYERS = copy.deepcopy(allowed)
subject = next(p for p in parser_copy.PLAYERS if p['pid'] == observations.loc[index, 'pid'])
parser_copy.PLAYERS.append({**subject, 'pid': 'duplicate_candidate'})
reject('ambiguous_same_cohort_identity', lambda: B.extract_source(source, observations, parser_copy))
# Both actual row-layout parsers reject rank-boundary violations.
for year in [2007, 2014]:
    _, tree, _ = P.source_tree(B.SOURCE / 'private' / f'dx_{year}.html')
    rows = [r for r in tree.xpath('//table/tr|//table/tbody/tr') if len(r.xpath('./td')) >= 3 and P.txt(r.xpath('./td')[0]).rstrip('.').isdigit() and r.xpath('./td')[2].xpath('.//a[contains(@href,"profile")]')]
    assert rows
    rows[-1].getparent().remove(rows[-1])
    reject('truncated_rank_boundary_' + str(year), lambda tree=tree, year=year: P.parse_dx(tree, year))
with tempfile.TemporaryDirectory(prefix='mock-bio-tests-', dir=ROOT) as temporary:
    temp = Path(temporary)
    public = json.loads((B.SOURCE / 'public_manifest.json').read_text())
    (temp / 'public_manifest.json').write_text(json.dumps(public))
    (temp / 'rank_observations.csv').write_text('tampered')
    reject('unverified_source_observation_file', lambda: B.load_verified_inputs(temp))

report = {'status': 'passed', 'sources': 8, 'source_cells_checked': 480, 'matched_players': matched_count,
          'features': len(B.FEATURES), 'successful_checks': checks, 'adversarial_cases_rejected': rejected,
          'builder_sha256': B.sha(ROOT / 'build.py'), 'test_sha256': B.sha(Path(__file__)),
          'source_public_manifest_sha256': B.sha(B.SOURCE / 'public_manifest.json'),
          'test_writes_extracted_output_files': False, 'models_or_NBA_outcomes_used': False}
(ROOT / 'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
