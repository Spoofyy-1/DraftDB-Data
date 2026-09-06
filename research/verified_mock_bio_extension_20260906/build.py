"""No-network extension of reviewed ten archived mock-biography features."""
from pathlib import Path
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import re
import urllib.parse
import zoneinfo
import numpy as np
import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'verified_consensus_extension'
REVIEWED = ROOT.parent / 'verified_mock_bio'
ORIGINAL = Path('/Users/kennakao/Downloads/nba_redraft_handoff/data')
PRIORITY = {'dx': 0, 'nbadraft': 1, 'walter_serious': 2}
POS = ['PG', 'SG', 'SF', 'PF', 'C']
FEATURES = ['vmb_age_reported_years', 'vmb_listed_height_in', 'vmb_listed_weight_lb', 'vmb_listed_bmi', 'vmb_college_class_year'] + ['vmb_position_' + p.lower() for p in POS]
MISSING = ['', '-', '--', 'N/A', 'NA', 'Unknown', '?']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_inputs(source_root=SOURCE, reviewed_root=REVIEWED):
    manifest = json.loads((source_root / 'public_manifest.json').read_text())
    for name in ['rank_observations.csv', 'validated_sources.json', 'verification.json', 'parse.py']:
        assert sha(source_root / name) == manifest['files'][name]['sha256'], 'Unpinned source: ' + name
    check = json.loads((source_root / 'verification.json').read_text())
    assert check['status'] == 'passed_without_model_execution' and not check['training_or_scoring_performed']
    reviewed = json.loads((reviewed_root / 'PUBLIC_ALLOWLIST.json').read_text())
    for name in ['build.py', 'metric_dictionary.json', 'verification.json']:
        assert sha(reviewed_root / name) == reviewed['files'][name]['sha256'], 'Unpinned reviewed parser: ' + name
    reviewed_check = json.loads((reviewed_root / 'verification.json').read_text())
    assert reviewed_check['status'] == 'passed' and reviewed_check['matched_players'] == 374
    assert not reviewed_check['models_or_NBA_outcomes_used']
    B = load_module('reviewed_vmb_parser', reviewed_root / 'build.py')
    P = load_module('extension_rank_parser', source_root / 'parse.py')
    assert B.FEATURES == FEATURES
    sources = [s for s in json.loads((source_root / 'validated_sources.json').read_text()) if s['feature_eligible']]
    assert len(sources) == 18 and all(2015 <= s['draft_year'] <= 2026 for s in sources)
    return P, B, sources, pd.read_csv(source_root / 'rank_observations.csv')


def typed_fields(raw, layout):
    """Strict entire-cell tokens. Unsupported fields stay NaN with a reason."""
    values = {f: np.nan for f in FEATURES}
    issues, precision = {}, None
    for key in raw:
        assert key in ['age', 'height', 'weight', 'position', 'class']
    def number(key, low, high):
        token = raw.get(key, '').strip()
        if token in MISSING:
            return np.nan
        if not re.fullmatch(r'\d+(?:\.\d+)?', token):
            issues[key] = 'Malformed or ambiguous numeric token'; return np.nan
        result = float(token)
        if not low <= result <= high:
            issues[key] = 'Value outside reviewed plausibility bounds'; return np.nan
        return result
    age = number('age', 13, 35)
    values['vmb_age_reported_years'] = age
    if np.isfinite(age):
        token = raw['age'].strip(); precision = 10 ** -len(token.split('.')[1]) if '.' in token else 1.0
    height = raw.get('height', '').strip()
    if height not in MISSING:
        if layout in ['ndnet', 'walter']:
            match = re.fullmatch(r'([4-8])-(\d{1,2}(?:\.\d+)?)', height)
            fraction = 0
        else:
            match = re.fullmatch(r"([4-8])'(\d{1,2}(?:\.\d+)?)(?:\s*([¼½¾]))?\"", height)
            fraction = {'¼': .25, '½': .5, '¾': .75}.get(match[3], 0) if match else 0
            if match and match[3] and '.' in match[2]:
                match = None
        if match and 0 <= float(match[2]) + fraction < 12:
            values['vmb_listed_height_in'] = int(match[1]) * 12 + float(match[2]) + fraction
        else:
            issues['height'] = 'Malformed, ambiguous or implausible full height token'
    values['vmb_listed_weight_lb'] = number('weight', 90, 450)
    h, w = values['vmb_listed_height_in'], values['vmb_listed_weight_lb']
    if np.isfinite(h) and np.isfinite(w):
        values['vmb_listed_bmi'] = w * .45359237 / (h * .0254) ** 2
    role = raw.get('position', '').strip()
    if role not in MISSING:
        roles = [p.strip() for p in role.split('/')]
        if 1 <= len(roles) <= 5 and len(set(roles)) == len(roles) and all(p in POS for p in roles):
            for p in POS:
                values['vmb_position_' + p.lower()] = float(p in roles)
        else:
            issues['position'] = 'Unsupported or ambiguous roles; all five indicators missing'
    year = raw.get('class', '').strip()
    mapping = {'Fr.': 1, 'Freshman': 1, 'So.': 2, 'Soph.': 2, 'Sophomore': 2, 'Jr.': 3, 'Junior': 3, 'Sr.': 4, 'Senior': 4}
    if year in mapping:
        values['vmb_college_class_year'] = float(mapping[year])
    elif year not in MISSING + ['Intl.', 'International', 'HS Sr.', 'HS', 'H.S.']:
        issues['class'] = 'Unrecognized class token; no inferred class year'
    return values, {'reported_age_precision': precision, 'issues': issues, 'raw_tokens': raw}


def source_cells(tree, source, P):
    """Return only verified player cells/rows, in literal rank order."""
    year, publisher = source['draft_year'], source['publisher']
    if publisher == 'dx' and year == 2015:
        candidates = []
        for table in tree.xpath('//table'):
            rows = [r for r in table.xpath('./tr|./tbody/tr') if r.xpath('./td') and re.fullmatch(r'\d+\.', P.txt(r.xpath('./td')[0]))]
            if len(rows) >= 30:
                candidates.append(rows)
        assert len(candidates) == 1 and len(candidates[0]) == 60
        result = []
        for row in candidates[0]:
            cell = copy.deepcopy(row.xpath('./td')[2])
            for nested in cell.xpath('.//table'):
                nested.drop_tree()
            result.append(('dx_text', cell))
        return result
    if publisher == 'dx' and year == 2016:
        containers = P.classes(tree, 'div', 'rankings'); assert len(containers) == 1
        items = containers[0].xpath('./div[contains(concat(" ",normalize-space(@class)," ")," ranking-item ")]')
        assert len(items) == 60
        return [('dx_text', P.classes(item, 'div', 'item')[0]) for item in items]
    if publisher == 'dx' and year == 2017:
        table = [t for t in P.classes(tree, 'table', 'sorttable') if 'averages' in t.get('class', '').split()]
        assert len(table) == 1
        return [('dx_table', r) for r in table[0].xpath('./tr|./tbody/tr')]
    if publisher == 'nbadraft':
        result = []
        for ident in ['nba_mock_consensus_table', 'nba_mock_consensus_table2']:
            tables = tree.xpath('//table[@id=$ident]', ident=ident)
            assert 1 <= len(tables) <= 2
            # Rank parser checks clone rank/name facts. Bio extraction must also
            # require equal factual measurement cells, not merely equal masks.
            vectors = [[[P.txt(c) for c in row.xpath('./td')][2:] for row in table.xpath('./tr|./tbody/tr')] for table in tables]
            assert all(v == vectors[0] for v in vectors), 'Conflicting measurement cells in sticky table clone'
            result += [('ndnet', row) for row in tables[0].xpath('./tr|./tbody/tr')]
        return result
    if publisher == 'walter_serious':
        lists = tree.xpath('//ol'); assert len(lists) == 1 and len(lists[0].xpath('./li')) == 15
        return [('walter', item.xpath('./b|./strong')[0]) for item in lists[0].xpath('./li')]
    raise AssertionError('Unregistered source layout')


def parse_row(layout, node, P, B):
    cell_hash = hashlib.sha256(html.tostring(node)).hexdigest()
    if layout == 'dx_text':
        links = node.xpath('.//a[contains(@href,"/profile/")]'); assert len(links) == 1
        name, href = P.txt(links[0]), links[0].get('href')
        try:
            values, info = B.parse_cell(node)
        except AssertionError as error:
            values = {f: np.nan for f in FEATURES}
            info = {'reported_age_precision': None, 'issues': {'cell': str(error)}, 'raw_tokens': {}}
        else:
            assert info['name'] == name and info['profile_href'] == href
            info.update(issues={}, raw_tokens={})
    elif layout in ['dx_table', 'ndnet']:
        cells = node.xpath('./td')
        assert len(cells) == (16 if layout == 'dx_table' else 8)
        name_index = 3 if layout == 'dx_table' else 2
        links = cells[name_index].xpath('./a'); assert len(links) == 1
        name, href = P.txt(links[0]), links[0].get('href')
        assert ('/profile/' if layout == 'dx_table' else '/players/') in href
        columns = {'position': 5, 'age': 6, 'height': 7, 'weight': 8} if layout == 'dx_table' else {'height': 3, 'weight': 4, 'position': 5, 'class': 7}
        values, info = typed_fields({key: P.txt(cells[i]) for key, i in columns.items()}, layout)
    else:
        heading = P.txt(node)
        parts = [p.strip() for p in heading.split(':', 1)[1].split(',')]
        assert len(parts) == 5, 'Unsupported Walter heading field count'
        name, href = parts[0], ''
        values, info = typed_fields({'position': parts[1], 'height': parts[3], 'class': parts[4]}, 'walter')
    info.update(name=name, profile_href=href, cell_sha256=cell_hash, layout=layout)
    return values, info


def extract_source(source, observations, P, B, source_root=SOURCE):
    assert source['feature_eligible'] and source['status'] == 'verified_predraft_mock'
    sid, year = source['source_id'], source['draft_year']
    assert 2015 <= year <= 2026 and year == int(source['draft_date'][:4])
    capture = dt.datetime.strptime(source['source']['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=dt.timezone.utc)
    cutoff = dt.datetime.fromisoformat(source['draft_date']).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
    assert capture == dt.datetime.fromisoformat(source['source_available_by_utc']) < cutoff
    assert dt.datetime.fromisoformat(source['cutoff_utc']) == cutoff
    assert source['source_last_updated_date'] < source['draft_date']
    if year == 2026:
        assert source['draft_date'] == '2026-06-23'
    original = source['source']['original']
    host = urllib.parse.urlparse(original).hostname
    expected = {'dx': ['draftexpress.com', 'www.draftexpress.com'], 'nbadraft': ['nbadraft.net', 'www.nbadraft.net'], 'walter_serious': ['walterfootball.com', 'www.walterfootball.com']}
    assert host in expected[source['publisher']]
    assert source['archive_url'] == f"https://web.archive.org/web/{source['source']['timestamp']}id_/{original}"
    path = source_root / 'private' / f'{sid}.html'
    assert sha(path) == source['html_sha256']
    raw, tree, encoding = P.read_tree(path)
    rank_parser = {'dx': P.dx, 'nbadraft': P.nbadraft, 'walter_serious': P.walter_serious}[source['publisher']]
    ranks, date, update, boundary, body = rank_parser(tree, year)
    assert date == source['source_last_updated_date'] <= capture.date().isoformat()
    assert update == source['source_update_text'] and boundary == source['body_boundary']
    assert hashlib.sha256(body).hexdigest() == source['table_sha256']
    rank_hash = hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest()
    assert rank_hash == source['rank_facts_sha256'] and len(ranks) == source['listed_count']
    cells = source_cells(tree, source, P)
    assert len(cells) == len(ranks) and [r['rank'] for r in ranks] == list(range(1, len(ranks) + 1))
    lookup = observations[observations.source_id == sid].set_index('mock_rank')
    assert lookup.index.is_unique and lookup.pid.is_unique and len(lookup) == source['matched_players']
    facts, provenance, issues = [], [], []
    for rank, ((layout, node), ranking) in enumerate(zip(cells, ranks), 1):
        if ranking['source_name'] in ['Forfeited Pick', 'Pick Forfeited']:
            assert rank not in lookup.index
            continue
        values, info = parse_row(layout, node, P, B)
        assert info['name'] == ranking['source_name'] and info['profile_href'] == ranking['profile_href']
        candidates = [p for p in P.PLAYERS if p['draft_year'] == year and P.norm(p['name']) == P.norm(info['name'])]
        if rank not in lookup.index:
            assert len(candidates) != 1
            continue
        match = lookup.loc[rank]
        assert len(candidates) == 1 and match.pid == candidates[0]['pid'] and match.draft_year == year
        assert match.draft_date == candidates[0]['draft_date'] == source['draft_date']
        for key, expected_value in [('publisher', source['publisher']), ('listed_count', len(ranks)), ('match_method', 'unique_exact_normalized_same_cohort_name'),
                                    ('table_sha256', source['table_sha256']), ('rank_facts_sha256', rank_hash), ('capture_utc', source['source_available_by_utc']),
                                    ('source_last_updated_date', date), ('archive_url', source['archive_url']), ('source_url', original)]:
            assert match[key] == expected_value, 'Observation mismatch: ' + key
        record = {'pid': match.pid, 'draft_year': year, 'source_id': sid, 'publisher': source['publisher']}
        facts.append({**record, **values})
        provenance.append({**record, 'archive_url': source['archive_url'], 'source_url': original, 'capture_utc': source['source_available_by_utc'],
                           'draft_date': source['draft_date'], 'source_last_updated_date': date, 'table_sha256': source['table_sha256'],
                           'html_sha256': source['html_sha256'], 'rank_facts_sha256': rank_hash, 'cell_sha256': info['cell_sha256'],
                           'profile_href': info['profile_href'], 'source_row_ordinal': rank, 'age_precision_years': info['reported_age_precision'],
                           'layout': layout, 'raw_typed_tokens_json': json.dumps(info['raw_tokens'], sort_keys=True),
                           'missing_reasons_json': json.dumps(info['issues'], sort_keys=True)})
        if info['issues']:
            issues.append({**record, 'source_row_ordinal': rank, 'missing_reasons': info['issues']})
    assert len(facts) == source['matched_players']
    return facts, provenance, issues


def choose_rows(observations):
    observations = observations.copy()
    assert not observations.duplicated(['pid', 'source_id']).any()
    observations['priority'] = observations.publisher.map(PRIORITY)
    assert observations.priority.notna().all()
    # One source per publisher/cohort is already registered. No rank, values,
    # target, completeness score or test information participates in priority.
    assert not observations.duplicated(['pid', 'publisher']).any()
    chosen = observations.sort_values(['draft_year', 'pid', 'priority', 'source_id']).drop_duplicates('pid', keep='first')
    return chosen.drop(columns='priority').reset_index(drop=True)


def join_identities(identity, facts):
    assert list(identity) == ['pid', 'draft_year'] and identity.pid.is_unique and facts.pid.is_unique
    known = facts[facts.pid.isin(identity.pid)]
    assert known.draft_year.equals(known.pid.map(identity.set_index('pid').draft_year)), 'Cross-cohort identity collision'
    joined = identity.merge(facts[['pid', 'draft_year'] + FEATURES], on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined[['pid', 'draft_year']].equals(identity) and len(joined) == len(identity)
    return joined


def main():
    P, B, sources, observations = load_inputs()
    facts, provenance, issues = [], [], []
    for source in sources:
        ff, pp, ii = extract_source(source, observations, P, B)
        facts.extend(ff); provenance.extend(pp); issues.extend(ii)
    all_rows = pd.DataFrame(facts)
    assert len(all_rows) == len(observations) == 764
    selected = choose_rows(all_rows)
    assert selected.pid.is_unique and len(selected) == 600
    all_rows.to_csv(ROOT / 'source_observations.csv', index=False)
    pd.DataFrame(provenance).to_csv(ROOT / 'row_provenance.csv', index=False)
    selected[['pid', 'draft_year', 'source_id', 'publisher']].to_csv(ROOT / 'selected_sources.csv', index=False)
    for segment, subset in [('training_2015_2018', selected[selected.draft_year <= 2018]), ('inference_2019_2026', selected[selected.draft_year >= 2019])]:
        subset[['pid', 'draft_year'] + FEATURES].to_csv(ROOT / f'features_{segment}.csv', index=False)
    sidecars = ROOT / 'sidecars'; sidecars.mkdir(exist_ok=True)
    pools = {}
    for year in [None] + list(range(2019, 2027)):
        source_path = ORIGINAL / ('train_2000_2018.csv' if year is None else f'tests/test_{year}_inputs.csv')
        identity = pd.read_csv(source_path, usecols=['pid', 'draft_year'])
        subset = selected[selected.draft_year <= 2018] if year is None else selected[selected.draft_year == year]
        joined = join_identities(identity, subset)
        name = 'train_2000_2018' if year is None else f'test_{year}_inputs'
        joined.to_csv(sidecars / f'mock_bio_extension_{name}.csv', index=False)
        pools[name] = {'rows': len(identity), 'covered': int(joined[FEATURES].notna().any(axis=1).sum()),
                       'identity_order_sha256': hashlib.sha256(identity.to_csv(index=False).encode()).hexdigest(),
                       'nonmissing': {c: int(joined[c].notna().sum()) for c in FEATURES}}
    dictionary = json.loads((REVIEWED / 'metric_dictionary.json').read_text())
    assert list(dictionary) == FEATURES
    for c in dictionary:
        dictionary[c]['source'] = 'Verified archived DX, NBADraft, or serious Walter mock player cell/row; see selected_sources.csv'
        dictionary[c]['extension_note'] = 'Definitions unchanged; one whole source row chosen by fixed DX, NBADraft, serious Walter priority; no cross-source field filling.'
    (ROOT / 'metric_dictionary.json').write_text(json.dumps(dictionary, indent=2))
    (ROOT / 'missing_field_reasons.json').write_text(json.dumps(issues, indent=2))
    coverage = {'source_rows': len(all_rows), 'sources': len(sources), 'selected_players': len(selected),
                'training_selected': int((selected.draft_year <= 2018).sum()), 'inference_selected': int((selected.draft_year >= 2019).sum()),
                'selected_publisher_counts': selected.publisher.value_counts().to_dict(), 'pools': pools,
                'per_year': {str(year): {'players': len(g), 'nonmissing': {c: int(g[c].notna().sum()) for c in FEATURES}} for year, g in selected.groupby('draft_year')},
                'rows_with_recorded_missing_reasons': len(issues), 'network_calls': 0, 'models_or_outcomes_used': False}
    (ROOT / 'coverage.json').write_text(json.dumps(coverage, indent=2))
    manifest = {'status': 'Dated listed biographies; not official measurements or model certification', 'features': FEATURES,
                'source_priority': PRIORITY, 'priority_unit': 'Entire source row, never per feature', 'source_public_manifest_sha256': sha(SOURCE / 'public_manifest.json'),
                'reviewed_public_allowlist_sha256': sha(REVIEWED / 'PUBLIC_ALLOWLIST.json'), 'reviewed_builder_sha256': sha(REVIEWED / 'build.py'),
                'source_tables': [{k: s[k] for k in ['source_id', 'publisher', 'draft_year', 'archive_url', 'html_sha256', 'table_sha256', 'rank_facts_sha256', 'source_available_by_utc', 'draft_date']} for s in sources],
                'files': {n: sha(ROOT / n) for n in ['source_observations.csv', 'row_provenance.csv', 'selected_sources.csv', 'features_training_2015_2018.csv', 'features_inference_2019_2026.csv', 'metric_dictionary.json', 'coverage.json', 'missing_field_reasons.json']}}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: v for k, v in coverage.items() if k not in ['pools', 'per_year']}, indent=2))


if __name__ == '__main__':
    main()
