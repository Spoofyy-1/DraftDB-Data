"""Offline identity bridge review. No WAR values, features, or models are read.

Current Wikidata records are permitted only as stable identity crosswalks.
Private projections deliberately exclude measurements and career statistics.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
PRIVATE = ROOT / 'private'
CROSSWALK = WORK / 'verified_prior_drafts_identity/private/reviewed_crosswalk.csv'
PRIOR_PROVENANCE = WORK / 'prior_population_repair/private/label_provenance.csv'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def write_csv(path, values):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)

def normalize(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', value)

def claims(entity, property_id):
    return [r for r in entity['identity_claims_only'] if r['property'] == property_id and r['rank'] != 'deprecated']

def single_value(entity, property_id):
    values = claims(entity, property_id)
    if len(values) != 1:
        raise ValueError('Missing or ambiguous published identity property')
    return values[0]['value']

def identity_pair(entity):
    nba = single_value(entity, 'P3647')
    bref = single_value(entity, 'P2685')
    dob = single_value(entity, 'P569')
    if not isinstance(nba, str) or not nba.isdigit() or int(nba) <= 0:
        raise ValueError('Malformed NBA identity')
    if not isinstance(bref, str) or not re.fullmatch('[a-z]/[a-z0-9]+', bref):
        raise ValueError('Malformed Basketball-Reference identity')
    if dob['precision'] != 11 or not re.fullmatch(r'\+\d{4}-\d{2}-\d{2}T00:00:00Z', dob['time']):
        raise ValueError('Birth date lacks exact day precision')
    return dict(nba_id=int(nba), basketball_reference_id=bref, raptor_player_id=bref.split('/')[1],
                birth_date=dob['time'][1:11])

def verify_bridge(member, entity, expected_calendar_source_ids):
    """Source IDs establish identity; WAR agreement never participates."""
    if entity['status_code'] != 200 or not isinstance(entity['lastrevid'], int):
        raise ValueError('Unverified source response/revision')
    if member['identity_link_ready'] != 'True' or member['mapping_status'] != 'dated_combine_id_corroborated':
        raise ValueError('Source membership lacks reviewed official identity')
    pair = identity_pair(entity)
    if pair['nba_id'] != int(member['official_predraft_id']):
        raise ValueError('Published NBA ID differs from official predraft identity')
    if set(expected_calendar_source_ids) != {pair['raptor_player_id']}:
        raise ValueError('Published Basketball-Reference ID differs from proposed source calendar')
    if int(member['draft_year']) not in {2012, 2013}:
        raise ValueError('Out-of-pilot identity')
    return pair

def cache_dob(text):
    match = re.search(r'\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})(?:\||}})', text)
    if not match:
        raise ValueError('Cached birth date not explicitly parseable')
    return dt.date(*map(int, match.groups())).isoformat()

def main():
    out = ROOT / 'data'
    out.mkdir(exist_ok=True)
    PRIVATE.chmod(0o700)
    config = json.loads((PRIVATE / 'review_config.json').read_text())
    cross = {r['candidate_id']: r for r in rows(CROSSWALK)}
    assert len(config) == 2 and set(config) <= set(cross)
    # This file carries provenance metadata only, not numeric WAR cells.
    previous = rows(PRIOR_PROVENANCE)
    evidence = json.loads((PRIVATE / 'wrong_person_cache_projections.json').read_text())
    labels = json.loads((PRIVATE / 'property_and_school_labels.json').read_text())['labels']
    assert labels['P2685'] == 'Basketball Reference NBA player ID'
    assert labels['P3647'] == 'NBA.com player ID'
    assert labels['P569'] == 'date of birth'
    bridges, cache_audit, proposals, sources = [], [], [], []
    for cid, choice in sorted(config.items()):
        member = cross[cid]
        target_path = PRIVATE / f"{choice['target_entity']}_identity_only.json"
        wrong_path = PRIVATE / f"{choice['wrong_entity']}_identity_only.json"
        target, wrong = [json.loads(p.read_text()) for p in [target_path, wrong_path]]
        metadata = [r for r in previous if r['candidate_id'] == cid]
        pair = verify_bridge(member, target, [r['raptor_source_id'] for r in metadata])
        other = identity_pair(wrong)
        assert pair['nba_id'] != other['nba_id'] and pair['raptor_player_id'] != other['raptor_player_id']
        assert pair['birth_date'] != other['birth_date']
        child_ids = {c['value']['id'] for c in claims(wrong, 'P40')}
        assert target['entity_id'] in child_ids, 'The rejected source identity must explicitly identify this child entity'
        school = [labels[c['value']['id']] for c in claims(target, 'P69')]
        wrong_school = [labels[c['value']['id']] for c in claims(wrong, 'P69')]
        nba_claim = claims(target, 'P3647')[0]
        bref_claim = claims(target, 'P2685')[0]
        source_url = f"https://www.wikidata.org/w/index.php?title={target['entity_id']}&oldid={target['lastrevid']}"
        bridges.append(dict(candidate_id=cid, draft_year=int(member['draft_year']),
            source_name=member['player_name_source'], broad_pid=member['broad_pid'], legacy_pid=member['legacy_pid'],
            official_predraft_nba_id=pair['nba_id'], basketball_reference_id=pair['basketball_reference_id'],
            raptor_player_id=pair['raptor_player_id'], entity_id=target['entity_id'], entity_label=target['label']['value'],
            birth_date=pair['birth_date'], identity_schools='|'.join(school),
            entity_revision=target['lastrevid'], source_revision_url=source_url,
            source_response_sha256=target['response_sha256'], stored_identity_projection_sha256=sha(target_path),
            nba_claim_id=nba_claim['claim_id'], bref_claim_id=bref_claim['claim_id'],
            nba_claim_reference_count=len(nba_claim['references']), bref_claim_reference_count=len(bref_claim['references']),
            verification_method='exact published NBA and Basketball-Reference IDs on one nondeprecated Wikidata entity; NBA ID independently matches official historical combine identity',
            bridge_verified=True, WAR_used_to_establish_identity=False, model_bundle_changed=False))
        matched_caches = [r for r in evidence if r['private_legacy_pid'] == member['legacy_pid']]
        assert len(matched_caches) == 2
        prerev = next(r for r in matched_caches if r['cache_type'] == 'prerev_')
        cached_identity = prerev['identity_fields_only']
        assert cache_dob(cached_identity['birth_date']) == other['birth_date']
        assert cache_dob(cached_identity['birth_date']) != pair['birth_date']
        assert normalize(cached_identity['name']) == normalize(wrong['label']['value'])
        assert int(cached_identity['draft_year']) < int(member['draft_year'])
        assert prerev['revision_timestamp'][:10] < member['membership_available_date']
        for cache in matched_caches:
            file = Path(cache['local_cache_path'])
            assert sha(file) == cache['sha256'], 'Original wrong-person cache changed'
            assert cache['title'] == prerev['title']
            assert cache['identity_fields_only']['draft_year'] == cached_identity['draft_year']
            cache_audit.append(dict(candidate_id=cid, legacy_pid=member['legacy_pid'], source_cache_path=str(file),
                source_cache_sha256=cache['sha256'], source_cache_type=cache['cache_type'],
                intended_name=target['label']['value'], intended_nba_id=pair['nba_id'],
                intended_birth_date=pair['birth_date'], intended_draft_year=member['draft_year'],
                intended_identity_schools='|'.join(school), wrong_cache_page_title=cache['title'],
                wrong_entity=wrong['entity_id'], wrong_person_name=wrong['label']['value'],
                wrong_person_nba_id=other['nba_id'], wrong_person_birth_date=other['birth_date'],
                wrong_person_draft_year=cached_identity['draft_year'], wrong_person_schools='|'.join(wrong_school),
                cached_college=cache['identity_fields_only']['college'], revision_id=prerev['revision_id'],
                revision_timestamp=prerev['revision_timestamp'],
                archived_revision_url='https://en.wikipedia.org/w/index.php?oldid='+str(prerev['revision_id']),
                result='verified_wrong_person_father_cache', original_cache_modified=False))
        for r in metadata:
            assert int(r['draft_year']) == int(member['draft_year'])
            assert int(member['draft_year']) < int(r['season_end']) <= 2018
            assert r['raptor_source_id'] == pair['raptor_player_id']
            proposals.append(dict(candidate_id=cid, draft_year=int(r['draft_year']), ordinal=int(r['ordinal']),
                season_end=int(r['season_end']), official_nba_id=pair['nba_id'], raptor_player_id=pair['raptor_player_id'],
                identity_bridge_verified=True, identity_source_revision_url=source_url,
                prior_calendar_provenance_sha256=sha(PRIOR_PROVENANCE), WAR_values_read_in_this_review=False,
                disposition='proposed_identity_verified_calendar_entry; parent review and bundle rebuild still required',
                existing_bundle_modified=False))
        for path, entity in [(target_path, target), (wrong_path, wrong)]:
            sources.append(dict(entity_id=entity['entity_id'], revision=entity['lastrevid'],
                entity_url=entity['url'], identity_projection_sha256=sha(path),
                full_response_sha256=entity['response_sha256'], retrieved_at_utc=entity['retrieved_at_utc']))
    assert len(bridges) == 2 and len(proposals) == 5 and len(cache_audit) == 4
    assert len({(r['candidate_id'], r['season_end']) for r in proposals}) == 5
    write_csv(PRIVATE / 'verified_identity_crosswalk.csv', bridges)
    write_csv(PRIVATE / 'wrong_person_cache_audit.csv', cache_audit)
    write_csv(PRIVATE / 'proposed_calendar_entries.csv', proposals)
    dump(PRIVATE / 'source_manifest.json', sources)
    log = json.loads((PRIVATE / 'network_log.json').read_text())
    assert log['count_so_far'] <= 12
    assert all(r['status_code'] == 200 for r in log['direct_requests'])
    allowed_properties = {'P2685','P3647','P569','P69','P40','P22','P13216','P3531'}
    for file in PRIVATE.glob('Q*_identity_only.json'):
        obj = json.loads(file.read_text())
        assert {r['property'] for r in obj['identity_claims_only']} <= allowed_properties
    for file in PRIVATE.iterdir():
        if file.is_file(): file.chmod(0o600)
    summary = dict(identities_requested=2, exact_published_cross_system_bridges_verified=2,
        official_historical_combine_IDs_corroborated=2, father_homonyms_distinguished=2,
        wrong_person_cache_subjects=2, wrong_person_cache_files=4, wrong_cached_revisions_predate_target_draft=True,
        proposed_calendar_metadata_entries=5, proposed_calendar_entries_end_no_later_than=2018,
        numeric_WAR_values_read=0, numeric_WAR_values_used_as_identity_proof=0,
        current_measurements_or_features_imported=0, current_or_future_test_outcomes_read=0,
        initiated_queries_and_HTTP_requests=log['count_so_far'], request_cap=12,
        model_fits=0, benchmark_scores=0, existing_bundles_modified=False,
        original_caches_modified=False, automatic_calendar_or_label_promotion=False,
        public_output_scope='aggregate counts and verification only; identities and proposed calendars private',
        limitations=['The exact published ID registry is community-maintained Wikidata; NBA-ID statements have no attached reference in these snapshots.',
            'The NBA IDs independently match already verified official predraft combine records; WAR agreement is not identity evidence.',
            'Current stable identity claims are used only for cross-system identity correction, never as model features.',
            'This review resolves identity only. Parent must independently apply historical season cutoff and existing label definition when rebuilding bundles.'])
    dump(out / 'verification.json', summary)
    dump(out / 'manifest.json', dict(schema_version=1, created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        scope='Two historical identities and their four wrong-person caches only',
        crosswalk_input_sha256=sha(CROSSWALK), prior_calendar_provenance_sha256=sha(PRIOR_PROVENANCE),
        private_bridge_output_sha256=sha(PRIVATE / 'verified_identity_crosswalk.csv'),
        private_wrong_cache_audit_sha256=sha(PRIVATE / 'wrong_person_cache_audit.csv'),
        private_calendar_proposals_sha256=sha(PRIVATE / 'proposed_calendar_entries.csv'),
        numeric_features_exported=0, numeric_label_values_exported=0, identities_exported_publicly=0,
        initiated_network_requests=log['count_so_far'], network_request_cap=12,
        existing_files_mutated=False, model_sandbox_allowlist=[]))
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
