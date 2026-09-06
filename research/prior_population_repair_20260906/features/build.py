"""Bounded no-network feature repair for eight retained source-membership IDs."""
from pathlib import Path
import copy
import csv
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import re
import zoneinfo
import numpy as np
import pandas as pd
from lxml import html

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
KEY = WORK / 'verified_prior_drafts_identity/private/reviewed_crosswalk.csv'
MOCK = WORK / 'verified_consensus'
BIO = WORK / 'verified_mock_bio'
REPORTS = WORK / 'source_validation/expansion'
RAW = Path('/Users/kennakao/nba/datarebuild/tracking_raw')
FIELDS = {3:'gp',4:'minutes_share',6:'usage',7:'efg',8:'ts',9:'orb',10:'drb',11:'ast_pct',12:'tov_pct',13:'ftm',14:'fta',15:'ft_pct',16:'fg2m',17:'fg2a',18:'fg2_pct',19:'fg3m',20:'fg3a',21:'fg3_pct',22:'blk_pct',23:'stl_pct',24:'ftr',30:'fouls40',35:'ast_tov',36:'rim_made',37:'rim_attempts',38:'mid_made',39:'mid_attempts',42:'dunk_made',43:'dunk_attempts',54:'mpg',57:'oreb_pg',58:'dreb_pg',60:'ast_pg',61:'stl_pg',62:'blk_pg',63:'pts_pg'}


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def scalar(v):
    try: x = float(v); return x if np.isfinite(x) else np.nan
    except ValueError: return np.nan


def main():
    key = pd.read_csv(KEY)
    key = key[key.identity_link_ready & ~key.existing_research_row].copy().reset_index(drop=True)
    assert len(key) == key.candidate_id.nunique() == 8
    assert (key.mapping_status == 'dated_combine_id_corroborated').all()
    assert key.draft_year.between(2012, 2014).all()
    base = key[['candidate_id', 'draft_year']].copy()
    aliases = {r.candidate_id: set(str(v) for v in [r.player_name_source, r.broad_name, r.legacy_name] if pd.notna(v)) for r in key.itertuples()}
    key.to_csv(ROOT / 'private/identity_crosswalk.csv', index=False)
    P = load('repair_mock_parser', MOCK / 'parse.py')
    B = load('repair_reviewed_bio', BIO / 'build.py')
    X = load('repair_typed_bio', WORK / 'verified_mock_bio_extension/build.py')
    pins = {}
    for directory, manifest_name in [(MOCK, 'public_manifest.json'), (BIO, 'PUBLIC_ALLOWLIST.json'), (REPORTS, 'public_manifest.json')]:
        manifest = json.loads((directory / manifest_name).read_text())
        assert all(sha(directory / name) == record['sha256'] for name, record in manifest['files'].items())
        pins[str(directory.relative_to(WORK))] = {'manifest': manifest_name, 'sha256': sha(directory / manifest_name)}
    normalized = {cid: {P.norm(n) for n in names} for cid, names in aliases.items()}
    ctx_columns = json.loads((WORK / 'r8t/plan.json').read_text())['baseline_source_variant']['context_features']
    assert len(ctx_columns) == 41 and all(c.startswith(('ctx_base_', 'ctx_skill_')) for c in ctx_columns)
    assert 'ctx_base_age' not in ctx_columns and 'ctx_base_height' not in ctx_columns
    college = base.copy()
    for c in ctx_columns: college[c] = np.nan
    source_rows, raw_hashes = [], {}
    # Only the allowlisted source fields are selected. NBA pick column45,
    # birthdate66, height26 and every later season are excluded.
    for year in [2011, 2012, 2013, 2014]:
        file = RAW / f'torvik_{year}.csv.gz'; raw_hashes[file.name] = sha(file)
        selected_columns = sorted(set([0, 1, 31, 32] + list(FIELDS)))
        table = pd.read_csv(file, header=None, usecols=selected_columns, dtype=str)
        assert table[31].astype(int).eq(year).all()
        for i, row in table.iterrows():
            source_rows.append({'name': row[0], 'name_normalized': P.norm(row[0]), 'team': row[1], 'source_season': year, 'source_player_id': row[32],
                                'source_row': int(i), 'source_file': file.name, **{name: scalar(row[index]) for index, name in FIELDS.items()}})
    college_provenance, private_rows, unresolved = [], [], []
    for i, subject in key.iterrows():
        candidates = [r for r in source_rows if r['source_season'] <= subject.draft_year and r['name_normalized'] in normalized[subject.candidate_id]]
        if not candidates:
            unresolved.append({'candidate_id': subject.candidate_id, 'family': 'college', 'reason': 'No exact reviewed name in pre-draft college cache; no new alias inferred'})
            continue
        lastyear = max(r['source_season'] for r in candidates)
        last = [r for r in candidates if r['source_season'] == lastyear]
        assert len(last) == 1, 'Duplicate/ambiguous final college row; no arbitrary source selection'
        row = last[0]
        if subject.draft_year - lastyear > 1:
            unresolved.append({'candidate_id': subject.candidate_id, 'family': 'college', 'reason': 'Last college source older than inherited one-year gap limit'})
            continue
        f = {'ctx_base_' + c: row[c] for c in FIELDS.values()}
        total = row['fg2a'] + row['fg3a']; f['ctx_base_three_share'] = row['fg3a'] / total if total > 0 else np.nan
        f['ctx_skill_defense_discipline'] = (row['stl_pct'] + row['blk_pct']) / (row['fouls40'] + 1) if row['fouls40'] >= 0 else np.nan
        f['ctx_skill_creation_control'] = row['ast_pct'] / (row['tov_pct'] + 1) if row['tov_pct'] >= 0 else np.nan
        f['ctx_skill_usage_efficiency'] = (row['usage'] - 20) * (row['ts'] - 50) / 100
        f['ctx_skill_ft_volume'] = row['ft_pct'] * np.log1p(row['fta']) if row['fta'] >= 0 else np.nan
        assert set(f) == set(ctx_columns)
        for c in ctx_columns: college.loc[i, c] = f[c]
        college_provenance.append({'candidate_id': subject.candidate_id, 'draft_year': int(subject.draft_year), 'source_file': row['source_file'],
                                   'source_sha256': raw_hashes[row['source_file']], 'source_row_zero_based': row['source_row'], 'source_season': lastyear,
                                   'source_year_gap': int(subject.draft_year - lastyear), 'match': 'Unique exact normalized reviewed name in latest permitted season',
                                   'original_release_vintage_verified': False, 'limitation': 'Retrospectively retrieved historical-season facts; source season is valid but original publication vintage is unavailable'})
        private_rows.append({'candidate_id': subject.candidate_id, **{c: row[c] for c in ['name', 'team', 'source_player_id', 'source_season', 'source_row', 'source_file']}})
    college.to_csv(ROOT / 'college_features.csv', index=False)
    pd.DataFrame(private_rows).to_csv(ROOT / 'private/college_source_identities.csv', index=False)
    (ROOT / 'college_provenance.json').write_text(json.dumps(college_provenance, indent=2))

    # Recover exact-name mock facts even where an earlier package had no global
    # player ID. Approved source-derived candidate IDs remain the only join key.
    rank_rows, bio_rows, mock_provenance, private_mock = [], [], [], []
    sources = json.loads((MOCK / 'validated_sources.json').read_text())
    dates = {}
    for source in sources:
        if source['draft_year'] not in [2012, 2013, 2014] or source['publisher'] not in ['dx', 'nbadraft'] or not source['feature_eligible']: continue
        year, publisher = source['draft_year'], source['publisher']; sid = f'{publisher}_{year}'; dates[year] = source['draft_date']
        capture = dt.datetime.fromisoformat(source['source_available_by_utc']); cutoff = dt.datetime.fromisoformat(source['draft_date']).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        assert capture < cutoff and source['source_last_updated_date'] < source['draft_date']
        raw, tree, encoding = P.source_tree(MOCK / 'private' / f'{sid}.html'); assert hashlib.sha256(raw).hexdigest() == source['html_sha256']
        ranks, updated, update_text, boundary, evidence = (P.parse_dx if publisher == 'dx' else P.parse_nbadraft)(tree, year)
        assert updated == source['source_last_updated_date'] and hashlib.sha256(evidence).hexdigest() == source['table_sha256']
        assert hashlib.sha256(json.dumps(ranks, sort_keys=True).encode()).hexdigest() == source['rank_facts_sha256']
        cells = []
        for table in html.fragments_fromstring(evidence.decode(encoding)):
            for row in table.xpath('./tr|./tbody/tr'):
                tds = row.xpath('./td')
                if len(tds) >= 3 and re.fullmatch(r'\d+\.?', P.txt(tds[0])): cells.append(tds)
        assert len(cells) == len(ranks) == 60
        for rank, tds in zip(ranks, cells):
            candidates = [r for r in key.itertuples() if r.draft_year == year and P.norm(rank['source_name']) in normalized[r.candidate_id]]
            assert len(candidates) <= 1
            if not candidates: continue
            subject = candidates[0]; cid = subject.candidate_id
            if publisher == 'dx':
                values, info = B.parse_cell(tds[2]); assert info['name'] == rank['source_name'] and info['profile_href'] == rank['profile_href']
            else:
                values, info = X.typed_fields({'height': P.txt(tds[3]), 'weight': P.txt(tds[4]), 'position': P.txt(tds[5]), 'class': P.txt(tds[7])}, 'ndnet')
            rank_rows.append({'candidate_id': cid, 'draft_year': year, 'publisher': publisher, 'mock_rank': rank['rank']})
            bio_rows.append({'candidate_id': cid, 'draft_year': year, 'publisher': publisher, **values})
            mock_provenance.append({'candidate_id': cid, 'draft_year': year, 'source_id': sid, 'mock_row_ordinal': rank['rank'], 'archive_url': source['archive_url'],
                                    'capture_utc': source['source_available_by_utc'], 'draft_date': source['draft_date'], 'update_date': updated,
                                    'table_sha256': source['table_sha256'], 'rank_facts_sha256': source['rank_facts_sha256'],
                                    'match': 'Unique exact normalized name from reviewed crosswalk, same draft cohort'})
            private_mock.append({'candidate_id': cid, 'source_id': sid, 'source_name': rank['source_name'], 'profile_href': rank['profile_href']})
    rank = base.copy(); vcons = ['vcons_mock_mean_rank', 'vcons_mock_best_rank', 'vcons_mock_rank_range', 'vcons_mock_n_sources']
    for c in vcons: rank[c] = np.nan
    bio = base.copy()
    for c in B.FEATURES: bio[c] = np.nan
    for i, subject in key.iterrows():
        values = [r['mock_rank'] for r in rank_rows if r['candidate_id'] == subject.candidate_id]
        if values:
            rank.loc[i, vcons] = [np.mean(values), min(values), max(values) - min(values) if len(values) >= 2 else np.nan, len(values)]
        choices = [r for r in bio_rows if r['candidate_id'] == subject.candidate_id]
        if choices:
            chosen = sorted(choices, key=lambda r: ['dx', 'nbadraft'].index(r['publisher']))[0]
            for c in B.FEATURES: bio.loc[i, c] = chosen[c]
    rank.to_csv(ROOT / 'consensus_features.csv', index=False); bio.to_csv(ROOT / 'bio_features.csv', index=False)
    pd.DataFrame(rank_rows).to_csv(ROOT / 'mock_rank_observations.csv', index=False)
    pd.DataFrame(bio_rows).to_csv(ROOT / 'mock_bio_observations.csv', index=False)
    (ROOT / 'mock_provenance.json').write_text(json.dumps(mock_provenance, indent=2))
    (ROOT / 'private/mock_source_identities.json').write_text(json.dumps(private_mock, indent=2))

    # Re-key only already validated report rows with reviewed broad/legacy IDs.
    report_sources = json.loads((REPORTS / 'source_manifest.json').read_text())
    report_obs = pd.read_csv(REPORTS / 'observations_eligible.csv')
    report_frames, report_provenance = {}, []
    for family, filename in [('synergy', 'synergy_features_eligible.csv'), ('text', 'text_features_eligible.csv')]:
        old = pd.read_csv(REPORTS / filename); columns = list(old)[2:]
        new = base.copy()
        for c in columns: new[c] = np.nan
        for i, subject in key.iterrows():
            ids = {p for p in [subject.broad_pid, subject.legacy_pid] if pd.notna(p)}
            found = old[old.pid.isin(ids) & old.draft_year.eq(subject.draft_year)]
            assert len(found) <= 1
            if found.empty: continue
            for c in columns: new.loc[i, c] = found.iloc[0][c]
            facts = report_obs[report_obs.pid.isin(ids) & report_obs.draft_year.eq(subject.draft_year) & report_obs.metric.isin(columns)]
            for r in facts.itertuples():
                assert r.publication_date < dates[subject.draft_year]
                assert dt.datetime.fromisoformat(r.capture_utc) < dt.datetime.fromisoformat(dates[subject.draft_year]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
                assert report_sources[r.source_id]['feature_eligible']
                report_provenance.append({'candidate_id': subject.candidate_id, 'draft_year': int(subject.draft_year), 'family': family,
                                          'metric': r.metric, 'source_id': r.source_id, 'publication_date': r.publication_date,
                                          'capture_utc': r.capture_utc, 'archive_url': r.archive_url, 'evidence_sha256': r.evidence_sha256,
                                          'method': 'Rekey pinned validated feature row through reviewed identity crosswalk'})
        report_frames[family] = new
    # Two newly matched, single-subject sections in already verified2014 bodies.
    rules = json.loads((REPORTS / 'extraction_rules.json').read_text())
    metric_dictionary = json.loads((REPORTS / 'metric_dictionary.json').read_text())
    section_specs = [('Xavier Thames', 'dx4617', {'report_pullup_fga_pg': 4.9, 'report_pullup_fg_pct': 40.0}),
                     ('Alec Brown', 'dx4618', {'report_poss_pg': 14.9, 'report_transition_poss_pct': 10.8, 'report_spotup_ppp': 1.14})]
    new_facts = []
    for source_name, sid, values in section_specs:
        candidates = [r for r in key.itertuples() if r.draft_year == 2014 and P.norm(source_name) in normalized[r.candidate_id]]
        assert len(candidates) == 1; subject = candidates[0]; source = report_sources[sid]
        assert source['feature_eligible'] and source['draft_year'] == 2014 and source['publication_date'] < dates[2014]
        assert dt.datetime.fromisoformat(source['capture_utc']) < dt.datetime.fromisoformat(dates[2014]).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        body_file = REPORTS / 'private' / f'{sid}.body.txt'; body_bytes = body_file.read_bytes(); assert hashlib.sha256(body_bytes).hexdigest() == source['body_sha256']; body = body_bytes.decode('utf-8')
        blocks = [' '.join(b.split()) for b in re.split(r'(?:^|\n)\s*[-•]\s*', body)[1:]]
        sections = [b for b in blocks if source_name in b[:80]]; assert len(sections) == 1
        section = sections[0]; section_hash = hashlib.sha256(section.encode()).hexdigest()
        expected = {'dx4617': ['4.9 dribble jump shots per-game', '40% clip'], 'dx4618': ['14.9 possessions per-game', '10.8%', '1.14 points per possession']}[sid]
        assert all(token in section for token in expected)
        idx = report_frames['synergy'].index[report_frames['synergy'].candidate_id.eq(subject.candidate_id)][0]
        for metric, value in values.items():
            assert metric in report_frames['synergy'] and pd.isna(report_frames['synergy'].loc[idx, metric])
            report_frames['synergy'].loc[idx, metric] = value
            new_facts.append({'candidate_id': subject.candidate_id, 'draft_year': 2014, 'metric': metric, 'value': value,
                              'source_id': sid, 'publication_date': source['publication_date'], 'capture_utc': source['capture_utc'],
                              'archive_url': source['archive_url'], 'body_sha256': source['body_sha256'], 'section_sha256': section_hash,
                              'unit': metric_dictionary[metric]['unit'], 'denominator': metric_dictionary[metric]['denominator'],
                              'method': 'Explicit numeric sentence verified within one named-player pre-draft section; existing metric definition only'})
        wc = len(re.findall(r'\b\w+\b', section)); assert wc >= 30
        textvalues = {'report_text_words': wc, **{f'report_text_{name}_per1k': 1000 * len(re.findall(pattern, section, re.I)) / wc for name, pattern in rules['lexicons'].items()}}
        assert set(textvalues) == set(report_frames['text'].columns[2:])
        for metric, value in textvalues.items(): report_frames['text'].loc[idx, metric] = value
        report_provenance.append({'candidate_id': subject.candidate_id, 'draft_year': 2014, 'family': 'new_synergy_and_fixed_lexicon', 'source_id': sid,
                                  'publication_date': source['publication_date'], 'capture_utc': source['capture_utc'], 'archive_url': source['archive_url'],
                                  'body_sha256': source['body_sha256'], 'section_sha256': section_hash, 'word_count': wc, 'literal_lexicon_sha256': sha(REPORTS / 'extraction_rules.json')})
    for family, frame in report_frames.items(): frame.to_csv(ROOT / f'{family}_features.csv', index=False)
    (ROOT / 'report_provenance.json').write_text(json.dumps(report_provenance, indent=2))
    (ROOT / 'new_report_numeric_facts.json').write_text(json.dumps(new_facts, indent=2))
    full = base.copy()
    families = {'college': college, 'consensus': rank, 'bio': bio, **report_frames}
    for frame in families.values():
        assert frame[['candidate_id', 'draft_year']].equals(base)
        full = full.merge(frame, on=['candidate_id', 'draft_year'], validate='one_to_one', how='left', sort=False)
    assert full[['candidate_id', 'draft_year']].equals(base)
    assert np.isfinite(full.iloc[:, 2:].stack().dropna().to_numpy()).all()
    full.to_csv(ROOT / 'numeric_feature_join.csv', index=False)
    inventory = []
    for i, subject in key.iterrows():
        inventory.append({'candidate_id': subject.candidate_id, 'draft_year': int(subject.draft_year),
                          'nonmissing_by_family': {family: int(frame.iloc[i, 2:].notna().sum()) for family, frame in families.items()},
                          'retained_even_if_missing': True, 'no_participation_or_label_selection': True})
    manifest = {'status': 'Feature-only candidate repair; no model-ready or benchmark claim', 'retained_candidates': 8,
                'identity_metadata': 'private/identity_crosswalk.csv', 'identity_crosswalk_sha256': sha(KEY), 'pinned_source_packages': pins,
                'raw_college_file_hashes': raw_hashes, 'college_source_field_indices': FIELDS,
                'families': {family: list(frame.columns[2:]) for family, frame in families.items()},
                'inventory': inventory, 'unresolved': unresolved,
                'limitations': ['Jeff Taylor has only an uncorroborated Jeffery Taylor college-cache name; college remains missing.',
                                'Glen Rice final college source2012 is carried for draft2013 under existing one-year-gap policy.',
                                'Torvik season facts are retrospective; original release vintages unavailable.',
                                'Source mock/scouting coverage remains selective; eight source-membership rows are retained independently of later participation.',
                                'NDnet size uses listing conventions; no official measurements or current bios are substituted.'],
                'network_calls': 0, 'labels_or_outcomes_read': False, 'models_or_publishing_performed': False}
    manifest['files'] = {p.name: sha(p) for p in ROOT.iterdir() if p.is_file() and p.name != 'manifest.json'}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'rows': len(full), 'numeric_columns': len(full.columns)-2, 'family_covered': {f: int(d.iloc[:,2:].notna().any(axis=1).sum()) for f,d in families.items()}, 'inventory': inventory}, indent=2))


if __name__ == '__main__': main()
