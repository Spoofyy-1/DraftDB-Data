"""Bounded eight-member population repair inventory; offline, no model runs.

Only these source-fixed historical cohort identities can have WAR parsed, and
only actual source seasons ending by 2018. Missing records never create zeros.
Calendar candidates remain quarantined pending independent source-ID review.
"""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
NBA = Path('/Users/kennakao/nba')
YEARS = {2012, 2013, 2014}
MAX_SEASON = 2018
CROSSWALK = WORK / 'verified_prior_drafts_identity/private/reviewed_crosswalk.csv'
RAPTOR = WORK / 'audit/historical_RAPTOR_by_player.csv'
OLD_TRAIN = WORK / 'audit/train.csv'

def normalize(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().casefold()
    return re.sub('[^a-z0-9]', '', s)

def load_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write_csv(path, rows, fields=None):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def pilot_members(crosswalk):
    result = [r for r in crosswalk if r['identity_link_ready'] == 'True' and r['existing_research_row'] == 'False']
    assert len(result) == 8 and len({r['candidate_id'] for r in result}) == 8
    assert all(int(r['draft_year']) in YEARS for r in result)
    return sorted(result, key=lambda r: r['candidate_id'])

def candidate_calendar(member, source_rows, cutoff):
    """Use calendar/date evidence before reading WAR; never infer calendar years.

    Returns source metadata only. A global name collision is explicitly retained
    as a provenance issue even when its older identity predates the known cohort.
    """
    if cutoff > MAX_SEASON:
        raise ValueError('Pilot refuses NBA seasons later than 2018')
    year = int(member['draft_year'])
    if year not in YEARS:
        raise ValueError('Out-of-pilot cohort')
    names = {normalize(member[k]) for k in ['player_name_source', 'broad_name', 'legacy_name'] if member[k]}
    historical = [r for r in source_rows if int(r['season']) <= cutoff and normalize(r['player_name']) in names]
    eligible = [r for r in historical if int(r['season']) > year]
    ids = {r['player_id'] for r in eligible}
    if len(ids) != 1:
        return [], dict(status='no_eligible_source_record' if not ids else 'ambiguous_eligible_source_identity',
            historical_name_id_count=len({r['player_id'] for r in historical}), eligible_identity_count=len(ids))
    eligible.sort(key=lambda r: int(r['season']))
    if len({int(r['season']) for r in eligible}) != len(eligible):
        raise ValueError('Duplicate source season')
    return eligible[:5], dict(status='unique_calendar_candidate_pending_explicit_ID_bridge',
        historical_name_id_count=len({r['player_id'] for r in historical}), eligible_identity_count=1)

def approved_labels(candidates):
    """Explicitly fail closed: this inventory has no approved label identities."""
    return [r for r in candidates if r.get('independent_source_id_bridge_verified') is True
            and r.get('existing_ordinal_value_agrees') is True and int(r['season_end']) <= MAX_SEASON]

def main():
    out, private = ROOT / 'data', ROOT / 'private'
    out.mkdir(exist_ok=True)
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    members = pilot_members(load_csv(CROSSWALK))
    write_csv(private / 'member_crosswalk.csv', members)
    write_csv(out / 'pilot_member_index.csv', [dict(candidate_id=r['candidate_id'], draft_year=int(r['draft_year'])) for r in members])

    source_path = WORK / 'verified_combine/build.py'
    spec = importlib.util.spec_from_file_location('verified_combine_repair', source_path)
    combine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(combine)
    sources, source_manifests = {}, []
    for year in sorted(YEARS):
        path = NBA / f'datarebuild/combine_raw/combine_{year}.json'
        sources[year], info = combine.read_source(path, year)
        source_manifests.append(info)
    feature_rows, feature_provenance = [], []
    for member in members:
        year, identity = int(member['draft_year']), int(member['official_predraft_id'])
        found = [r for r in sources[year] if r['_id'] == identity]
        assert len(found) == 1
        row = found[0]
        transformed = combine.transform(row)
        feature_rows.append(dict(candidate_id=member['candidate_id'], draft_year=year, **transformed))
        feature_provenance.append(dict(candidate_id=member['candidate_id'], draft_year=year, source_year=year,
            source_filename=f'combine_{year}.json', source_sha256=source_manifests[sorted(YEARS).index(year)]['sha256'],
            source_row=row['_source_position'], source_name=row['PLAYER_NAME'], official_source_id=identity,
            identity_method='previously_corroborated_unique_official_combine_ID',
            populated_features=sum(math.isfinite(v) for v in transformed.values()),
            date_basis='request SeasonYear and every row SEASON agree; independent historical snapshot unavailable',
            no_imputation=True, no_current_bio=True))
    write_csv(out / 'combine_feature_candidates.csv', feature_rows)
    write_csv(private / 'combine_row_provenance.csv', feature_provenance)
    dump(out / 'combine_feature_dictionary.json', combine.feature_dictionary())
    dump(out / 'combine_sources.json', source_manifests)

    # Read identity/season metadata before touching any numeric target field.
    # Source rows outside the eight reviewed names or after 2018 are discarded.
    accepted_names = {normalize(r[k]) for r in members for k in ['player_name_source', 'broad_name', 'legacy_name'] if r[k]}
    source_rows = []
    with RAPTOR.open() as f:
        for r in csv.DictReader(f):
            season = int(r['season'])
            if season > MAX_SEASON or normalize(r['player_name']) not in accepted_names:
                continue
            source_rows.append(r)
    legacy_pids = {r['legacy_pid'] for r in members if r['legacy_pid']}
    old_train = {}
    with OLD_TRAIN.open() as f:
        for r in csv.DictReader(f):
            if r['pid'] in legacy_pids:
                assert int(r['draft_year']) in YEARS
                old_train[r['pid']] = r

    label_candidates, inventory, cutoff_inventory, label_provenance = [], [], [], []
    for member in members:
        cid, year = member['candidate_id'], int(member['draft_year'])
        candidate, audit = candidate_calendar(member, source_rows, MAX_SEASON)
        legacy = old_train.get(member['legacy_pid'])
        comparisons = []
        for ordinal, source in enumerate(candidate, 1):
            season = int(source['season'])
            assert year < season <= MAX_SEASON
            # Numeric WAR parsing is restricted to a calendar selected in advance
            # by this member's source names and actual historical source dates.
            value = float(source['war_total'])
            assert math.isfinite(value)
            existing = legacy.get(f'y_s{ordinal}_war', '') if legacy else ''
            agrees = bool(existing.strip()) and math.isclose(float(existing), value, abs_tol=1e-5, rel_tol=0)
            comparisons.append(agrees)
            label_candidates.append(dict(candidate_id=cid, draft_year=year, ordinal=ordinal, season_end=season,
                war=value, existing_ordinal_value_agrees=agrees, independent_source_id_bridge_verified=False,
                status='quarantined_pending_explicit_NBA_ID_to_RAPTOR_ID_bridge', model_ready=False))
            label_provenance.append(dict(candidate_id=cid, draft_year=year, ordinal=ordinal, season_end=season,
                source_name=source['player_name'], raptor_source_id=source['player_id'],
                raptor_source_sha256=sha(RAPTOR), prior_training_source_sha256=sha(OLD_TRAIN),
                existing_ordinal_value_agrees=agrees,
                identity_method='exact_reviewed_source_name_plus_unique_postcohort_calendar; explicit_cross_system_ID_bridge_pending',
                historical_name_id_count=audit['historical_name_id_count'],
                no_source_year_inference=True, no_future_ordinal_cells_used=True))
        inventory.append(dict(candidate_id=cid, draft_year=year, membership_retained=True,
            combine_record_verified=True, combine_populated_features=next(r['populated_features'] for r in feature_provenance if r['candidate_id'] == cid),
            eligible_calendar_candidate_seasons=len(candidate), legacy_training_row_present=legacy is not None,
            existing_ordinal_cells_compared=len(comparisons), existing_ordinal_cells_all_agree=all(comparisons) if comparisons else '',
            label_status=audit['status'], historical_name_id_count=audit['historical_name_id_count'],
            independent_source_id_bridge_verified=False, inferred_zero=False, model_ready=False))
        for cutoff in range(2012, MAX_SEASON + 1):
            eligible, _ = candidate_calendar(member, source_rows, cutoff)
            information_cutoff = f'{cutoff}-12-31'
            prior_member = year < cutoff + 1 and member['membership_available_date'] <= information_cutoff
            cutoff_inventory.append(dict(candidate_id=cid, draft_year=year, prediction_year=cutoff + 1,
                allowed_season_end=cutoff, membership_information_cutoff_date=information_cutoff,
                prior_cohort_membership_eligible=prior_member,
                calendar_candidate_count=len(eligible) if prior_member else 0,
                actual_source_seasons='|'.join(str(r['season']) for r in eligible) if prior_member else '',
                labels_approved_for_model=0, missing_outcome_is_zero=False))
    label_fields = ['candidate_id','draft_year','ordinal','season_end','war','existing_ordinal_value_agrees',
        'independent_source_id_bridge_verified','status','model_ready']
    write_csv(private / 'label_candidates_through2018.csv', label_candidates, label_fields)
    write_csv(private / 'label_provenance.csv', label_provenance)
    write_csv(private / 'label_inventory_by_cutoff.csv', cutoff_inventory)
    write_csv(private / 'join_inventory.csv', inventory)
    write_csv(private / 'approved_labels.csv', approved_labels(label_candidates), label_fields)
    assert not approved_labels(label_candidates)
    assert len(inventory) == 8 and all(r['membership_retained'] for r in inventory)
    for path in private.iterdir():
        if path.is_file():
            path.chmod(0o600)
    coverage = dict(pilot_members=8, combine_rows_verified=8, combine_candidate_features=len(combine.FEATURES),
        combine_feature_values_observed=sum(r['populated_features'] for r in feature_provenance),
        candidate_calendar_players=sum(r['eligible_calendar_candidate_seasons'] > 0 for r in inventory),
        candidate_season_WAR_records=len(label_candidates),
        candidate_records_agreeing_with_existing_ordinal_WAR=sum(r['existing_ordinal_value_agrees'] for r in label_candidates),
        missing_eligible_label_records=sum(r['eligible_calendar_candidate_seasons'] == 0 for r in inventory),
        explicit_cross_system_source_ID_bridges_pending=sum(r['eligible_calendar_candidate_seasons'] > 0 for r in inventory),
        labels_approved_for_model=0, zero_labels_inferred_from_absence=0, max_outcome_season_end=2018,
        features_or_labels_mutated_in_existing_packages=False, model_fits=0, benchmark_scores=0, network_requests=0,
        membership_preserved_independent_of_availability=True, model_ready=False)
    dump(out / 'coverage.json', coverage)
    manifest = dict(schema_version=1, created_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        years=sorted(YEARS), pilot_members=8, task='dated feature and censored-label join inventory, not a training run',
        source_files=[dict(filename=p.name, sha256=sha(p)) for p in [CROSSWALK, RAPTOR, OLD_TRAIN, source_path]],
        model_feature_columns=['candidate_id','draft_year'] + combine.FEATURES,
        approved_label_rows=0, candidate_label_rows_quarantined=len(label_candidates),
        outcome_access_policy='Only pilot members; select actual source seasons <=2018 before numeric WAR parsing; compare only corresponding existing ordinal cells',
        membership_cutoff_basis='Illustrative inventory uses December31 of the previous year; source membership availability date is independently checked against it',
        no_current_or_future_cohort_answers_opened=True, actual_draft_position_values_inspected_or_used=False,
        private_identity_and_label_metadata_excluded_from_public=True, no_automatic_model_promotion=True,
        limitations=['Two label-calendar candidates require an explicit cross-system NBA-ID to RAPTOR/Basketball-Reference-ID bridge.',
            'Agreement with existing WAR is a consistency check, not independent identity evidence.',
            'Six missing source records are unresolved; neither nonparticipation nor zero WAR is inferred.',
            'Combine historical season attribution is verified, but archived publication timestamps are unavailable.',
            'Feature and label joins never change the eight-member source-defined population.',
            'The complete 180-player registry and original test pools are unchanged.'])
    dump(out / 'manifest.json', manifest)
    print(json.dumps(coverage, indent=2))

if __name__ == '__main__':
    main()
