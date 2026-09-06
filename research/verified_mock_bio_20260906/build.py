"""Extract contemporaneously listed bios from pinned pre-draft mock archives."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import re
import urllib.parse
import numpy as np
import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'verified_consensus'
POS = ['PG', 'SG', 'SF', 'PF', 'C']
FEATURES = ['vmb_age_reported_years', 'vmb_listed_height_in', 'vmb_listed_weight_lb',
            'vmb_listed_bmi', 'vmb_college_class_year'] + ['vmb_position_' + p.lower() for p in POS]
NUMBER = r'[+-]?\d+(?:\.\d+)?'
LEFT_BOUNDARY = r'(?<![\w./+\-\u2013\u2014\u2212])'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(node):
    return ' '.join(' '.join(node.itertext()).split())


def _unambiguous_number(matches, body):
    assert len(matches) <= 1, 'More than one value for a biography field'
    if matches:
        assert not re.search(r'\d\s*(?:to|or|[-/\u2013\u2014])\s*$', body[:matches[0].start()], re.I), 'Ambiguous numeric range'


def parse_cell(cell):
    links = [a for a in cell.xpath('.//a') if '/profile/' in a.get('href', '') or 'viewprofile.php?' in a.get('href', '')]
    assert len(links) == 1, 'Biography cell must have one subject profile link'
    name, body = text(links[0]), text(cell)
    assert name and body.startswith(name)
    tail = body[len(name):].strip()
    fields = {c: np.nan for c in FEATURES}
    ages = list(re.finditer(LEFT_BOUNDARY + '(' + NUMBER + r')\s+years\s+old\b', tail))
    heights = list(re.finditer(LEFT_BOUNDARY + r'([+-]?\d+)\s*\x27\s*(' + NUMBER + r')\s*"', tail))
    weights = list(re.finditer(LEFT_BOUNDARY + '(' + NUMBER + r')\s+lbs\b', tail))
    for matches in [ages, heights, weights]:
        _unambiguous_number(matches, tail)
    # Empty template placeholders (literally 'years old' or 'lbs') are
    # missing, while a malformed numeric token cannot be silently discarded.
    for matches, unit in [(ages, r'\byears\s+old\b'), (weights, r'\blbs\b')]:
        markers = list(re.finditer(unit, tail))
        assert len(markers) <= 1, 'Ambiguous repeated biography units'
        if markers and not matches:
            assert not re.search(r'[\d./+\-\u2013\u2014\u2212]\s*$', tail[:markers[0].start()]), 'Malformed numeric biography token'
    if re.search(r'\d\s*\x27', tail):
        assert heights, 'Malformed listed height'
    if ages:
        age = float(ages[0][1]); assert 13 <= age <= 35, 'Invalid reported age'
        fields['vmb_age_reported_years'] = age
    if heights:
        feet, inches = map(float, heights[0].groups())
        assert 4 <= feet <= 8 and 0 <= inches < 12, 'Invalid listed height'
        fields['vmb_listed_height_in'] = feet * 12 + inches
    if weights:
        weight = float(weights[0][1]); assert 90 <= weight <= 450, 'Invalid listed weight'
        fields['vmb_listed_weight_lb'] = weight
    if np.isfinite(fields['vmb_listed_height_in']) and np.isfinite(fields['vmb_listed_weight_lb']):
        fields['vmb_listed_bmi'] = fields['vmb_listed_weight_lb'] * .45359237 / (fields['vmb_listed_height_in'] * .0254) ** 2
    classes = re.findall(r'\b(Freshman|Sophomore|Junior|Senior)\b', tail)
    assert len(set(classes)) <= 1, 'Conflicting class years'
    if classes:
        fields['vmb_college_class_year'] = ['Freshman', 'Sophomore', 'Junior', 'Senior'].index(classes[0]) + 1
    position = re.match(r'([A-Za-z]+(?:\s*/\s*[A-Za-z]+)*)(?=$|\s|[;(,])', tail)
    if position and (position[1] in POS or '/' in position[1]):
        roles = [p.strip() for p in position[1].split('/')]
        assert 1 <= len(roles) <= len(POS) and len(set(roles)) == len(roles) and all(p in POS for p in roles), 'Invalid/ambiguous listed position'
        assert not re.match(r'\s*(?:PG|SG|SF|PF|C)(?:\b|/)', tail[position.end():]), 'Ambiguous separated positions'
        for p in POS:
            fields['vmb_position_' + p.lower()] = float(p in roles)
    else:
        assert not re.match(r'(?:PG|SG|SF|PF|C)(?:\b|/)', tail), 'Malformed position prefix'
    assert any(np.isfinite(v) for v in fields.values()), 'No parsed biography facts'
    raw_age = None if not ages else ages[0][1]
    precision = None if raw_age is None else (10.0 ** -len(raw_age.split('.')[1]) if '.' in raw_age else 1.0)
    return fields, {'name': name, 'profile_href': links[0].get('href'), 'reported_age_precision': precision}


def load_verified_inputs(source_root=SOURCE):
    public = json.loads((source_root / 'public_manifest.json').read_text())
    for name in ['rank_observations.csv', 'validated_sources.json', 'verification.json', 'parse.py']:
        assert sha(source_root / name) == public['files'][name]['sha256'], f'Unpinned verified source file: {name}'
    verification = json.loads((source_root / 'verification.json').read_text())
    assert verification['status'] == 'passed' and not verification['model_or_test_scoring_performed']
    spec = importlib.util.spec_from_file_location('source_parser', source_root / 'parse.py')
    parser = importlib.util.module_from_spec(spec); spec.loader.exec_module(parser)
    verified = json.loads((source_root / 'validated_sources.json').read_text())
    observations = pd.read_csv(source_root / 'rank_observations.csv')
    return parser, verified, observations


def extract_source(source, observations, parser, source_root=SOURCE):
    assert source['publisher'] == 'dx' and source['feature_eligible'] and source['status'] == 'verified_predraft_mock'
    year, sid = source['draft_year'], f"dx_{source['draft_year']}"
    assert 2007 <= year <= 2014 and int(source['draft_date'][:4]) == year
    capture = datetime.datetime.strptime(source['source']['timestamp'], '%Y%m%d%H%M%S').replace(tzinfo=datetime.timezone.utc)
    available = datetime.datetime.fromisoformat(source['source_available_by_utc'])
    cutoff = datetime.datetime.fromisoformat(source['cutoff_utc'])
    assert capture == available and available.tzinfo is not None and cutoff.tzinfo is not None
    assert available < cutoff and source['source_last_updated_date'] < source['draft_date']
    original = source['source']['original']
    assert urllib.parse.urlparse(original).hostname in ['draftexpress.com', 'www.draftexpress.com']
    assert source['archive_url'] == f"https://web.archive.org/web/{source['source']['timestamp']}id_/{original}"
    path = source_root / 'private' / f'{sid}.html'
    assert sha(path) == source['html_sha256'], 'Archived HTML hash changed'
    raw, tree, encoding = parser.source_tree(path)
    ranks, date, update, boundary, body = parser.parse_dx(tree, year)
    assert date == source['source_last_updated_date'] <= capture.date().isoformat()
    assert update == source['source_update_text'] and boundary == source['body_boundary']
    assert hashlib.sha256(body).hexdigest() == source['table_sha256'], 'Table boundary/hash mismatch'
    rank_hash = hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest()
    assert rank_hash == source['rank_facts_sha256'] and len(ranks) == source['listed_count'] == 60
    collected = []
    for table in html.fragments_fromstring(body.decode(encoding)):
        for row in table.xpath('./tr|./tbody/tr'):
            cells = row.xpath('./td')
            if len(cells) >= 3 and re.fullmatch(r'\d+\.?', parser.txt(cells[0])):
                collected.append(cells[2])
    assert len(collected) == len(ranks) == 60
    lookup = observations[observations.source_id == sid].set_index('mock_rank')
    assert lookup.index.is_unique and lookup.pid.is_unique and set(lookup.index) <= set(range(1, 61))
    assert len(lookup) == source['matched_players']
    # Re-evaluate precisely the same validated identity rule using only these
    # allowed fields. No alias, fuzzy match, NBA outcome or modern bio lookup.
    identities = [{k: p[k] for k in ['pid', 'name', 'draft_year', 'draft_date']} for p in parser.PLAYERS]
    facts, provenance = [], []
    for rank, (cell, ranking) in enumerate(zip(collected, ranks), 1):
        values, info = parse_cell(cell)
        assert ranking['rank'] == rank and ranking['source_name'] == info['name'] and ranking['profile_href'] == info['profile_href']
        candidates = [p for p in identities if p['draft_year'] == year and parser.norm(p['name']) == parser.norm(info['name'])]
        if rank not in lookup.index:
            assert len(candidates) != 1, 'Validated unique identity unexpectedly missing from observations'
            continue
        match = lookup.loc[rank]
        assert len(candidates) == 1 and match.pid == candidates[0]['pid'], 'Rank observation identity mismatch'
        assert int(match.draft_year) == year and match.draft_date == candidates[0]['draft_date'] == source['draft_date']
        assert match.publisher == 'dx' and int(match.listed_count) == 60
        assert match.match_method == 'unique_exact_normalized_same_cohort_name'
        assert match.table_sha256 == source['table_sha256'] and match.rank_facts_sha256 == rank_hash
        assert match.capture_utc == source['source_available_by_utc'] and match.source_last_updated_date == date
        assert match.archive_url == source['archive_url'] and match.source_url == original
        facts.append(dict(pid=match.pid, draft_year=year, **values))
        provenance.append(dict(pid=match.pid, draft_year=year, source_id=sid, archive_url=source['archive_url'],
                               source_url=original, capture_utc=source['source_available_by_utc'], draft_date=source['draft_date'],
                               table_sha256=source['table_sha256'], html_sha256=source['html_sha256'],
                               profile_href=info['profile_href'], table_row_ordinal=rank, age_precision_years=info['reported_age_precision']))
    table_record = {k: source[k] for k in ['publisher', 'draft_year', 'archive_url', 'source_available_by_utc', 'draft_date', 'table_sha256', 'html_sha256', 'source_last_updated_date']}
    return facts, provenance, table_record


def main():
    parser, verified, observations = load_verified_inputs()
    tables, facts, provenance = [], [], []
    for source in verified:
        if source['publisher'] != 'dx' or not source.get('feature_eligible'):
            continue
        ff, pp, table = extract_source(source, observations, parser)
        facts.extend(ff); provenance.extend(pp); tables.append(table)
    frame = pd.DataFrame(facts)
    assert frame.pid.is_unique and len(tables) == 8 and set(frame.draft_year) == set(range(2007, 2015))
    assert list(frame) == ['pid', 'draft_year'] + FEATURES
    frame.to_csv(ROOT / 'features_eligible.csv', index=False)
    pd.DataFrame(provenance).to_csv(ROOT / 'row_provenance.csv', index=False)
    dictionary = {c: {'source': 'DraftExpress archived pre-draft mock player cell', 'note': 'Contemporaneously listed, not verified official measurement; no modern bios or post-draft fills'} for c in FEATURES}
    units = {'vmb_age_reported_years': 'listed years', 'vmb_listed_height_in': 'listed inches; shoe convention unknown',
             'vmb_listed_weight_lb': 'listed pounds', 'vmb_listed_bmi': 'kg/m^2 from same-cell listed values',
             'vmb_college_class_year': 'ordinal1-4; not inferred for international/high-school players'}
    for column in FEATURES:
        dictionary[column]['unit'] = units.get(column, 'indicator0/1; all missing when role unspecified')
    dictionary['vmb_age_reported_years']['note'] = 'Age shown in the captured page, often integer-rounded; NOT exact age on draft night. No birthday inferred.'
    dictionary['vmb_listed_bmi']['note'] = 'Derived only from same-cell listed weight and listed height; shoes convention unknown. Kept separate from official combine BMI.'
    dictionary['vmb_college_class_year']['note'] = 'Freshman1, Sophomore2, Junior3, Senior4; high school/international/unspecified remain missing.'
    for p in POS:
        dictionary['vmb_position_' + p.lower()]['note'] = 'Multi-position indicator from explicit listed position; all five stay missing if position unparsed.'
    (ROOT / 'metric_dictionary.json').write_text(json.dumps(dictionary, indent=2))
    manifest = dict(status='verified historical source facts; not model or benchmark certification', features=FEATURES, players=len(frame), sources=tables,
                    source_rank_observations_sha256=sha(SOURCE / 'rank_observations.csv'), source_verification_sha256=sha(SOURCE / 'verification.json'),
                    source_public_manifest_sha256=sha(SOURCE / 'public_manifest.json'), builder_sha256=sha(Path(__file__)),
                    coverage={str(y): int(n) for y, n in frame.groupby('draft_year').size().items()},
                    nonmissing={c: int(frame[c].notna().sum()) for c in FEATURES},
                    source_identity_policy='Reuse and independently recheck exact same-cohort unique matches from verified_consensus. No new aliases/fuzzy joins, actual picks or NBA outcomes.',
                    limitations=['Listing is contemporaneous but not an official combine measurement.', 'Archive availability and listed mock prospect population are selective.',
                                 'Reported age is not exact draft-night age and precision changes in2014.', 'No2015+inference coverage yet; no current biography or imputation fills.',
                                 'Original model eligibility/universe and held-out benchmark remain separately audited.'])
    manifest['files'] = {name: sha(ROOT / name) for name in ['features_eligible.csv', 'row_provenance.csv', 'metric_dictionary.json']}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'players': len(frame), 'features': len(FEATURES), 'years': manifest['coverage'], 'nonmissing': manifest['nonmissing']}))


if __name__ == '__main__':
    main()
