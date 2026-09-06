"""Offline identity-only review of the 24 gaps in the 2012–2014 prior-draft pilot.

No labels, numeric NBA outcomes, actual-pick fields or 2019+ draft records are
parsed. Membership is already source-fixed and never depends on any key match.
Name/PID crosswalks are private metadata and must not enter a learner sandbox.
"""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
NBA = Path('/Users/kennakao/nba')
YEARS = (2012, 2013, 2014)

# Explicitly reviewed source spelling pairs. These are not general fuzzy rules.
# Dennis's two forms are independently printed by the NBA's initial/final lists
# for the same club. Glen's combine ID also occurs in the 2012–13 D-League source.
COMBINE_ALIASES = {
    (2013, 'Dennis Schroeder'): 'Dennis Schroder',
    (2013, 'Glen Rice Jr.'): 'Glen Rice',
}

def normalize(value):
    value = str(value).replace('ı', 'i').replace('đ', 'd').replace('ø', 'o')
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]', '', value)

def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def unique(records, description):
    if len(records) != 1:
        raise ValueError(f'{description}: expected exactly one record, got {len(records)}')
    return records[0]

def numeric_id(value):
    if value is None or str(value).lower() in ('', 'nan', 'none', '<na>'):
        return None
    number = float(value)
    if not number.is_integer() or number <= 0:
        raise ValueError('Malformed identity ID')
    return int(number)

def key_identity_id(row):
    """NBA-prefixed UID is identity metadata, not proof of NBA participation."""
    match = re.fullmatch(r'nba_(\d+)', str(row.get('player_uid', '')))
    uid = int(match[1]) if match else None
    nba = numeric_id(row.get('nba_id'))
    if uid and nba and uid != nba:
        raise ValueError('Conflicting identity UID and ID')
    return uid or nba

def combine_identity(path, year):
    data = json.loads(path.read_text())
    if year not in YEARS or data['parameters']['SeasonYear'] != f'{year}-{str(year+1)[2:]}':
        raise ValueError('Wrong requested combine season')
    table = unique([t for t in data['resultSets'] if t['name'] == 'DraftCombineStats'], 'combine table')
    headers = table['headers']
    result = []
    for raw in table['rowSet']:
        if int(raw[headers.index('SEASON')]) != year:
            raise ValueError('Combine row belongs to another season')
        result.append({
            'source_year': year,
            'player_name': raw[headers.index('PLAYER_NAME')],
            'source_player_id': numeric_id(raw[headers.index('PLAYER_ID')]),
        })
    if len({x['source_player_id'] for x in result}) != len(result):
        raise ValueError('Duplicate combine ID')
    return result

def csv_write(path, values, fields=None):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(values[0]))
        writer.writeheader()
        writer.writerows(values)

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def check_source_aliases(events):
    initial = unique([x for x in events if x['source_id'] == '2013_initial' and x['player_name_source'] == 'Dennis Schroder'], 'Dennis initial')
    final = unique([x for x in events if x['source_id'] == '2013_final' and x['player_name_source'] == 'Dennis Schroeder'], 'Dennis final')
    assert initial['affiliation_source'] == final['affiliation_source']
    assert final['status'] == 'eligible_final_early_entry'
    assert initial['evidence_available_date'] <= final['evidence_available_date'] < '2013-06-27'
    glpath = NBA / 'datarebuild/gleague_raw/gl_base_2012-13.json'
    gl = json.loads(glpath.read_text())
    assert gl['parameters']['Season'] == '2012-13'
    assert gl['parameters']['LeagueID'] == '20'
    evidence = []
    for table in gl['resultSets']:
        h = table['headers']
        if 'PLAYER_ID' not in h or 'PLAYER_NAME' not in h:
            continue
        for raw in table['rowSet']:
            if numeric_id(raw[h.index('PLAYER_ID')]) == 203318:
                evidence.append(raw[h.index('PLAYER_NAME')])
    assert evidence == ['Glen Rice']
    return glpath

def main():
    import pandas as pd
    private = ROOT / 'private'
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    out = ROOT / 'data'
    out.mkdir(exist_ok=True)
    prior = WORK / 'verified_prior_drafts/data'
    registry = rows(prior / 'membership_registry.csv')
    gaps = rows(prior / 'training_population_gaps.csv')
    all_suggestions = rows(prior / 'identity_crosswalk_suggestions.csv')
    variants = rows(prior / 'source_name_variants.csv')
    assert len(registry) == 180 and len(gaps) == 24
    assert collections.Counter(int(r['draft_year']) for r in registry) == {2012: 60, 2013: 60, 2014: 60}
    assert len({r['candidate_id'] for r in registry}) == 180
    assert {r['candidate_id'] for r in gaps} <= {r['candidate_id'] for r in registry}

    key_path = NBA / 'keys/player_key.parquet'
    legacy_path = NBA / 'datarebuild/identity/tabular_names.csv'
    train_path = WORK / 'r8l/data/features.csv'
    key = pd.read_parquet(key_path, columns=['pid', 'player_uid', 'player_name', 'nba_id']).to_dict('records')
    legacy = pd.read_csv(legacy_path, usecols=['pid', 'draft_year', 'player_name', 'nba_id']).to_dict('records')
    train = pd.read_csv(train_path, usecols=['pid', 'draft_year']).to_dict('records')
    train_index = {(r['pid'], int(r['draft_year'])) for r in train}
    assert len(train_index) == len(train)
    by_name = collections.defaultdict(list)
    by_id = collections.defaultdict(list)
    for item in key:
        by_name[normalize(item['player_name'])].append(item)
        identity = key_identity_id(item)
        if identity:
            by_id[identity].append(item)
    legacy_names = collections.defaultdict(list)
    legacy_ids = collections.defaultdict(list)
    for item in legacy:
        year = int(item['draft_year'])
        if year not in YEARS:
            continue
        legacy_names[(year, normalize(item['player_name']))].append(item)
        identity = numeric_id(item['nba_id'])
        if identity:
            legacy_ids[(year, identity)].append(item)

    event_path = WORK / 'verified_eligibility/data/entry_events.csv'
    events = rows(event_path)
    glpath = check_source_aliases(events)
    combines = {}
    combine_paths = []
    for year in YEARS:
        path = NBA / f'datarebuild/combine_raw/combine_{year}.json'
        combine_paths.append(path)
        combines[year] = combine_identity(path, year)

    reviewed, evidence, negatives = [], [], []
    for gap in gaps:
        cid, year, name = gap['candidate_id'], int(gap['draft_year']), gap['player_name_source']
        canonical = unique([r for r in registry if r['candidate_id'] == cid], 'membership')
        source_names = {normalize(v['player_name_source']) for v in variants if v['candidate_id'] == cid}
        comb_name = COMBINE_ALIASES.get((year, name), name)
        combine = [r for r in combines[year] if normalize(r['player_name']) == normalize(comb_name)]
        broad = legacy_row = None
        source_id = None
        if combine:
            combine = unique(combine, 'same-cohort combine name')
            source_id = combine['source_player_id']
            broad = unique(by_id[source_id], 'global identity ID')
            allowed_names = source_names | {normalize(comb_name)}
            # James Ennis's NBA source ID is the bridge to the III spelling.
            if (year, name) == (2013, 'James Ennis'):
                allowed_names.add(normalize('James Ennis III'))
            assert normalize(broad['player_name']) in allowed_names
            id_candidates = legacy_ids.get((year, source_id), [])
            if id_candidates:
                legacy_row = unique(id_candidates, 'legacy ID/cohort')
                assert normalize(legacy_row['player_name']) in allowed_names
            else:
                name_candidates = {r['pid']: r for n in allowed_names for r in legacy_names.get((year, n), [])}
                if name_candidates:
                    legacy_row = unique(list(name_candidates.values()), 'legacy exact name/cohort')
                    legacy_id = numeric_id(legacy_row['nba_id'])
                    assert legacy_id in (None, source_id)
            status = 'dated_combine_id_corroborated'
            confidence = 'reviewed_source_id_bridge'
            note = 'Exact official combine ID joins the broad UID; null nba_id is allowed. This proves an identity link, not NBA participation or any label.'
            if (year, name) in COMBINE_ALIASES:
                note += ' Explicit source spelling review is recorded; no generic suffix/transliteration rule.'
            evidence.append(dict(candidate_id=cid, evidence_type='official_combine_identity', source_year=year,
                source_name=combine['player_name'], source_player_id=source_id,
                source_path=str(combine_paths[YEARS.index(year)]), source_sha256=digest(combine_paths[YEARS.index(year)]),
                evidence_available_date='', date_basis='requested SeasonYear and every SEASON row agree; no independent historical snapshot'))
        else:
            exact = {r['pid']: r for n in source_names for r in by_name.get(n, [])}
            if len(exact) == 1:
                broad = next(iter(exact.values()))
                legacy_candidates = {r['pid']: r for n in source_names for r in legacy_names.get((year, n), [])}
                if len(legacy_candidates) == 1:
                    legacy_row = next(iter(legacy_candidates.values()))
                    left = numeric_id(legacy_row['nba_id'])
                    right = key_identity_id(broad)
                    assert left is None or right is None or left == right
                status = 'unique_exact_name_reviewed_provisional'
                confidence = 'dated_source_name_plus_unique_key_name_only'
                note = 'Source membership and exact unique name agree; independent dated ID corroboration is absent. Keep this link provisional.'
            else:
                status = 'unresolved_global_identity_source_membership_retained'
                confidence = 'source_only'
                note = 'No acceptable exact-name or dated-ID bridge in the full broad key. Retain candidate_id; do not infer absence from NBA or a zero label.'
        legacy_pid = legacy_row['pid'] if legacy_row else ''
        present = (legacy_pid, year) in train_index
        resolution = ('existing_research_row_recovered_by_alias' if present else
                      'legacy_identity_present_research_row_absent' if legacy_pid else
                      'broad_identity_only_research_row_absent' if broad else
                      'source_only_identity_research_row_absent')
        reviewed.append(dict(candidate_id=cid, draft_year=year, player_name_source=name,
            membership_available_date=canonical['membership_available_date'], membership_retained=True,
            mapping_status=status, confidence_basis=confidence, broad_pid=broad['pid'] if broad else '',
            broad_player_uid=broad['player_uid'] if broad else '', broad_name=broad['player_name'] if broad else '',
            legacy_pid=legacy_pid, legacy_name=legacy_row['player_name'] if legacy_row else '',
            official_predraft_id=source_id or '', existing_research_row=present,
            population_resolution=resolution, canonical_membership_id_for_unresolved=cid,
            identity_link_ready=(status == 'dated_combine_id_corroborated'),
            feature_row_built=False, label_row_built=False, model_ready=False, review_note=note))
        for event in events:
            if int(event['draft_year']) == year and normalize(event['player_name_source']) in source_names | {normalize(comb_name)}:
                evidence.append(dict(candidate_id=cid, evidence_type='primary_NBA_eligibility_name_and_affiliation', source_year=year,
                    source_name=event['player_name_source'], source_player_id='', source_path=event['source_url'],
                    source_sha256=event['source_capture_sha256'], evidence_available_date=event['evidence_available_date'],
                    date_basis=f"{event['status']}; {event['affiliation_source']}; line {event['source_view_line']}"))
        if name in ('Jeff Taylor', 'Glen Rice Jr.'):
            for other in by_name[normalize(comb_name)]:
                if broad and other['pid'] != broad['pid']:
                    negatives.append(dict(candidate_id=cid, rejected_broad_pid=other['pid'], rejected_name=other['player_name'],
                        reason='Name homonym with identity ID different from this cohort official combine ID; rejected without inspecting NBA participation'))
        if name == 'Marko Todorovic':
            for other in by_name[normalize('Marko Todorovich')]:
                negatives.append(dict(candidate_id=cid, rejected_broad_pid=other['pid'], rejected_name=other['player_name'],
                    reason='Similar spelling only; no exact source name or dated ID bridge. Never accept fuzzy-only identity match.'))

    # Re-check both explicit name aliases against their independent dated sources.
    gl_cid = unique([r for r in reviewed if r['player_name_source'] == 'Glen Rice Jr.'], 'Glen')['candidate_id']
    evidence.append(dict(candidate_id=gl_cid, evidence_type='predraft_DLeague_identity_only', source_year=2013,
        source_name='Glen Rice', source_player_id=203318, source_path=str(glpath), source_sha256=digest(glpath),
        evidence_available_date='', date_basis='LeagueID 20; Season 2012-13; regular season; name/ID only, no statistics parsed'))
    reviewed.sort(key=lambda r: r['candidate_id'])
    csv_write(private / 'reviewed_crosswalk.csv', reviewed)
    csv_write(private / 'evidence.csv', evidence)
    csv_write(private / 'rejected_matches.csv', negatives)
    unresolved = [r for r in reviewed if not r['identity_link_ready']]
    csv_write(private / 'unresolved_and_provisional.csv', unresolved)
    absent = [r for r in reviewed if not r['existing_research_row']]
    csv_write(private / 'missing_research_rows.csv', absent)
    for path in private.glob('*'):
        if path.is_file():
            path.chmod(0o600)

    public_fields = ['candidate_id', 'draft_year', 'membership_retained', 'mapping_status',
        'existing_research_row', 'population_resolution', 'identity_link_ready', 'feature_row_built', 'label_row_built', 'model_ready']
    csv_write(out / 'gap_statuses.csv', [{k: r[k] for k in public_fields} for r in reviewed])
    status_by_id = {r['candidate_id']: r for r in reviewed}
    all_rows = []
    inherited = {r['candidate_id']: r for r in all_suggestions}
    for r in sorted(registry, key=lambda r: r['candidate_id']):
        record = status_by_id.get(r['candidate_id'])
        all_rows.append(dict(candidate_id=r['candidate_id'], draft_year=int(r['draft_year']), membership_retained=True,
            review_scope='gap_identity_review' if record else 'original_non_gap_mapping_not_reaudited',
            existing_research_row=record['existing_research_row'] if record else inherited[r['candidate_id']]['matched_existing_training_pid'] == 'True'))
    assert len(all_rows) == 180 and sum(r['existing_research_row'] for r in all_rows) == 158
    csv_write(out / 'all_membership_statuses.csv', all_rows)
    coverage = dict(source_memberships=180, original_apparent_gaps=24,
        gap_mapping_status_counts=dict(collections.Counter(r['mapping_status'] for r in reviewed)),
        gap_population_resolution_counts=dict(collections.Counter(r['population_resolution'] for r in reviewed)),
        gaps_recovered_existing_research_rows=sum(r['existing_research_row'] for r in reviewed),
        selected_members_still_absent_from_research_rows=len(absent),
        total_source_members_matched_existing_research_rows=sum(r['existing_research_row'] for r in all_rows),
        inherited_non_gap_mappings_not_reaudited=156, broad_key_rows=len(key),
        identity_ready_but_missing_research_row=sum(r['identity_link_ready'] and not r['existing_research_row'] for r in reviewed),
        provisional_exact_name_links=sum(r['mapping_status'] == 'unique_exact_name_reviewed_provisional' for r in reviewed),
        unresolved_source_only=sum(r['mapping_status'].startswith('unresolved') for r in reviewed),
        by_year={str(y): dict(source_memberships=60, gap_rows=sum(r['draft_year'] == y for r in reviewed),
            recovered_existing=sum(r['draft_year'] == y and r['existing_research_row'] for r in reviewed),
            still_absent=sum(r['draft_year'] == y for r in absent)) for y in YEARS}, model_ready=False)
    dump(out / 'coverage.json', coverage)
    inputs = [prior / 'membership_registry.csv', prior / 'training_population_gaps.csv', prior / 'source_name_variants.csv',
        prior / 'identity_crosswalk_suggestions.csv', key_path, legacy_path, train_path, event_path, glpath] + combine_paths
    manifest = dict(schema_version=1, created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), years=list(YEARS),
        scope='24 apparent gaps only; preserve all 180 independently established prior selected memberships',
        inputs=[dict(name=p.name, sha256=digest(p)) for p in inputs],
        key_columns_parsed=['pid', 'player_uid', 'player_name', 'nba_id'],
        legacy_columns_parsed=['pid', 'draft_year', 'player_name', 'nba_id'], research_columns_parsed=['pid', 'draft_year'],
        official_combine_columns_parsed=['SEASON', 'PLAYER_ID', 'PLAYER_NAME'],
        NBA_outcome_values_inspected=False, WAR_values_inspected=False, actual_pick_fields_parsed=False,
        test_draft_sources_read=False, model_fits=0, test_scores=0, network_requests=0,
        membership_filter_uses_NBA_participation=False, membership_filter_uses_key_match=False,
        source_packages_mutated=False, private_crosswalks_allowed_in_model_sandbox=False,
        broad_pid_equals_legacy_pid_assumed=False, no_automatic_identity_or_label_promotion=True,
        limitations=['Four exact-name links remain provisional without independent dated ID corroboration.',
            'Ten source memberships have no accepted broad-key bridge; source-only IDs are preserved.',
            'Original 156 non-gap name mappings are inherited, not certified by this bounded review.',
            'Combine seasons identify historical records but independent historical snapshots are absent.',
            'Membership, identity, historical feature coverage and season-censored labels remain separate requirements.',
            'Missing NBA evidence must never be treated as a zero outcome.'])
    dump(out / 'manifest.json', manifest)
    print(json.dumps(coverage, indent=2))

if __name__ == '__main__':
    main()
