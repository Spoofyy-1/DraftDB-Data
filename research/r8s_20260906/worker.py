"""R8s: source-only baseline plus combine/consensus factorial diagnostics.

Controls shuffle whole family vectors within cohort and exact missingness strata.
Import performs no model preparation or GPU work. All results remain diagnostic.
"""
import os
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
from pathlib import Path
import collections
import datetime
import hashlib
import json
import time
import traceback
import zoneinfo
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'results'
_CACHE = None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _matrix_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()).hexdigest()


def rho(pred, truth):
    result = float(spearmanr(pred, truth).statistic)
    return result if np.isfinite(result) else 0.0


def _load_inputs():
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    assert len(plan['variants']) * len(plan['seeds']) == 57
    assert plan['families'] == manifest['source_families']
    assert plan['baseline_source_variant'] == manifest['baseline_source_variant']
    for name, expected in manifest['files'].items():
        assert Path(name).name == name and hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected
    for name, expected in manifest['base_data_hashes'].items():
        assert manifest['files'][name] == expected
    x, labels = pd.read_csv(DATA / 'features.csv'), pd.read_csv(DATA / 'labels.csv')
    assert list(x) == ['pid', 'draft_year', 'was_drafted', 'actual_pick'] + plan['baseline_source_variant']['context_features']
    assert x.pid.is_unique and (x.draft_year <= 2018).all()
    year_by_pid = x.set_index('pid').draft_year
    assert labels.pid.isin(x.pid).all() and labels.pid.map(year_by_pid).equals(labels.draft_year)
    assert not labels.duplicated(['pid', 'ordinal']).any() and labels.ordinal.between(1, 5).all()
    assert (labels.season_end <= 2018).all() and (labels.season_end >= labels.draft_year + labels.ordinal).all()
    sources = {}
    for family in ['combine', 'consensus']:
        frame = pd.read_csv(DATA / f'{family}_features.csv')
        assert frame[['pid', 'draft_year']].equals(x[['pid', 'draft_year']])
        assert list(frame) == ['pid', 'draft_year'] + plan['families'][family]
        assert not set(plan['families'][family]) & set(x)
        assert np.isfinite(frame[plan['families'][family]].stack().dropna().to_numpy()).all()
        sources[family] = frame
    combine = pd.read_csv(DATA / 'combine_provenance.csv')
    cm = json.loads((DATA / 'combine_metadata.json').read_text())
    records = {r['filename']: r for r in cm['source_files']}
    assert combine.pid.is_unique and combine.pid.isin(x.pid).all()
    assert (combine.source_year == combine.draft_year).all() and (combine.draft_year <= 2018).all()
    assert combine.pid.map(year_by_pid).equals(combine.draft_year)
    assert set(sources['combine'].loc[sources['combine'][plan['families']['combine']].notna().any(axis=1), 'pid']) <= set(combine.pid)
    for row in combine.itertuples():
        record = records[row.source_filename]
        assert record['source_year'] == row.draft_year and record['all_row_seasons_verified']
        assert record['parameters']['SeasonYear'] == f'{row.draft_year}-{str(row.draft_year + 1)[2:]}'
        assert 0 <= row.source_row < record['rows']
        assert row.match_method in ['unique_nba_id', 'unique_exact_same_cohort_name']
    cons = pd.read_csv(DATA / 'consensus_provenance.csv')
    cs = {f"{r['publisher']}_{r['draft_year']}": r for r in json.loads((DATA / 'consensus_sources.json').read_text())}
    assert cons.draft_year.between(2007, 2014).all() and cons.pid.isin(x.pid).all()
    assert cons.pid.map(year_by_pid).equals(cons.draft_year)
    assert not cons.duplicated(['pid', 'publisher']).any()
    for row in cons.itertuples():
        source = cs[row.source_id]
        assert source['feature_eligible'] and source['draft_year'] == row.draft_year
        assert row.match_method == 'unique_exact_normalized_same_cohort_name'
        assert row.source_last_updated_date < row.draft_date
        cutoff = datetime.datetime.fromisoformat(row.draft_date).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        assert datetime.datetime.fromisoformat(row.capture_utc) < cutoff
        assert row.capture_utc == source['source_available_by_utc'] and row.rank_facts_sha256 == source['rank_facts_sha256']
        assert 1 <= row.mock_rank <= row.listed_count
    expected = x[['pid', 'draft_year']].copy()
    grouped = cons.groupby('pid').mock_rank
    count = grouped.count()
    expected['vcons_mock_mean_rank'] = expected.pid.map(grouped.mean())
    expected['vcons_mock_best_rank'] = expected.pid.map(grouped.min())
    expected['vcons_mock_rank_range'] = expected.pid.map((grouped.max() - grouped.min()).where(count >= 2))
    expected['vcons_mock_n_sources'] = expected.pid.map(count)
    pd.testing.assert_frame_equal(expected, sources['consensus'], check_dtype=False)
    for family in ['combine', 'consensus']:
        x = x.merge(sources[family], on=['pid', 'draft_year'], validate='one_to_one', sort=False)
    assert len(x) == len(year_by_pid)
    return plan, manifest, x, labels


def _eligible_columns(training, columns, rule):
    assert not rule['validation_coverage_used']
    audit = [{'feature': c, 'observed': int(training[c].notna().sum()), 'unique': int(training[c].nunique())} for c in columns]
    kept = [r['feature'] for r in audit if r['observed'] >= rule['min_training_observed'] and r['unique'] >= rule['min_training_unique']]
    return kept, audit


def _strata(values, metadata):
    assert values.index.equals(metadata.index) and metadata.pid.is_unique
    groups = collections.defaultdict(list)
    for index in metadata.sort_values('pid', kind='stable').index:
        pattern = ''.join('1' if missing else '0' for missing in values.loc[index].isna())
        groups[(int(metadata.loc[index, 'draft_year']), pattern)].append(index)
    return groups


def _vector_strings(values):
    return [json.dumps([None if pd.isna(v) else float(v) for v in row], separators=(',', ':'), allow_nan=False) for row in values.to_numpy()]


def _vector_invariants(values, metadata):
    groups, observed_rows, movable_rows = [], 0, 0
    for (year, pattern), indices in sorted(_strata(values, metadata).items()):
        vectors = _vector_strings(values.loc[indices])
        observed = '0' in pattern
        movable = observed and len(set(vectors)) > 1
        observed_rows += len(indices) if observed else 0
        movable_rows += len(indices) if movable else 0
        groups.append({'cohort': year, 'mask_pattern': pattern, 'rows': len(indices),
                       'pid_hash': _hash(metadata.loc[indices, 'pid'].tolist()),
                       'unique_vectors': len(set(vectors)), 'movable': movable,
                       'vector_multiset_hash': _hash(sorted(vectors))})
    return {'columns': list(values), 'mask_hash': hashlib.sha256(values.isna().to_numpy().tobytes()).hexdigest(),
            'observed_rows': observed_rows, 'swappable_observed_rows': movable_rows,
            'immovable_observed_rows': observed_rows - movable_rows, 'groups': groups}


def _vector_shuffle(values, metadata, family, seed, role):
    assert role in ['train', 'validation'] and family in ['combine', 'consensus']
    out = values.astype(float).copy()
    before = _vector_invariants(values, metadata)
    for (year, pattern), indices in _strata(values, metadata).items():
        seed_parts = [family, int(seed), role, year, pattern]
        stable_seed = int.from_bytes(hashlib.sha256(json.dumps(seed_parts).encode()).digest()[:8], 'little')
        original = values.loc[indices].to_numpy(dtype=float)
        out.loc[indices] = original[np.random.default_rng(stable_seed).permutation(len(indices))]
    assert out.isna().equals(values.isna())
    assert _vector_invariants(out, metadata) == before, 'Family structure changed during shuffle'
    return out


def _source_values(frame, features, family, arm, permutation_seed, role):
    original = frame[features].astype(float).copy()
    assert np.isfinite(original.stack().dropna().to_numpy()).all() and arm in ['real', 'permuted']
    values = original.copy() if arm == 'real' else _vector_shuffle(original, frame, family, permutation_seed, role)
    changed = original.notna() & values.ne(original)
    return values, {'features': features, 'invariants': _vector_invariants(values, frame),
                    'matrix_hash': _matrix_hash(values), 'changed_observed_values': int(changed.sum().sum()),
                    'changed_observed_rows': int(changed.any(axis=1).sum())}


def _prepared():
    global _CACHE
    if _CACHE is not None:
        _CACHE[0].setup(_CACHE[1]['baseline_source_variant']['context_features'])
        return _CACHE
    import legacy_kernel as E
    import xgboost as xgb
    plan, manifest, x, labels = _load_inputs()
    baseline = plan['baseline_source_variant']
    columns = list(baseline['context_features'])
    assert baseline['input_source'] == 'context' and len(columns) == len(set(columns)) == 41
    assert all(c.startswith(('ctx_base_', 'ctx_skill_')) for c in columns)
    assert not any(c in ['ctx_base_age', 'ctx_base_height'] for c in columns)
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
    E.setup(columns)
    signature = _hash({'plan': plan, 'data_files': manifest['files'],
                       'kernel': hashlib.sha256((ROOT / 'legacy_kernel.py').read_bytes()).hexdigest(),
                       'worker': hashlib.sha256((ROOT / 'worker.py').read_bytes()).hexdigest()})
    folds = []
    for year in plan['folds']:
        assert year in [2012, 2013, 2014]
        cutoff, k = year - 1, min(5, 2018 - year)
        tr = x[(x.draft_year >= g['win']) & (x.draft_year <= year - 2)].copy().reset_index(drop=True)
        te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
        used = labels[(labels.season_end <= cutoff) & labels.pid.isin(tr.pid)]
        assert len(tr) and len(te) and len(used) and not set(tr.pid) & set(te.pid)
        assert not set(used.pid) & set(te.pid) and (used.season_end <= year - 1).all()
        for ordinal in range(1, 6):
            tr[f'y_s{ordinal}_war'] = tr.pid.map(used[used.ordinal == ordinal].set_index('pid').war)
        # Direct source-only columns: no legacy build, prior, coverage, shrinkage
        # or derived-feature code is called before or after this selection.
        btr, bte = tr[columns].copy(), te[columns].copy()
        yy = E.label(tr, E.specs(g)[0], k)
        selector = xgb.XGBRegressor(max_depth=3, n_estimators=300, learning_rate=.05, subsample=.8,
                                   colsample_bytree=.6, n_jobs=2, device='cpu', tree_method='hist', random_state=11)
        selector.fit(btr, yy)
        selected = [c for _, c in sorted(zip(selector.feature_importances_, columns), reverse=True)]
        assert len(selected) == 41 and set(selected) == set(columns)
        source_columns, selection = {}, {}
        for family in ['combine', 'consensus']:
            source_columns[family], selection[family] = _eligible_columns(tr, plan['families'][family], plan['source_filter'])
        assert source_columns == plan['training_eligibility_registration'][str(year)]
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        audit = {'study_hash': signature, 'ordered_base_columns': selected, 'base_columns_hash': _hash(selected),
                 'training_pid_hash': _hash(tr.pid.tolist()), 'validation_pid_hash': _hash(te.pid.tolist()),
                 'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                 'training_matrix_hash': _matrix_hash(btr[selected]), 'validation_matrix_hash': _matrix_hash(bte[selected]),
                 'source_selection': selection, 'source_selection_hash': _hash(selection),
                 'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                 'source_only_baseline': True, 'diagnostic_only': True}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te, 'btr': btr[selected].copy(),
                      'bte': bte[selected].copy(), 'yy': yy, 'truth': truth, 'source_columns': source_columns, 'audit': audit})
    _CACHE = E, plan, g, folds
    return _CACHE


def _design(fold, variant, plan):
    atr, ate = fold['btr'].copy(), fold['bte'].copy()
    family_audits = {}
    ordered_slots = []
    for family in ['combine', 'consensus']:
        if family not in variant['arms']:
            continue
        features = fold['source_columns'][family]
        family_audits[family] = {}
        for role, frame, target in [('train', fold['tr'], atr), ('validation', fold['te'], ate)]:
            values, audit = _source_values(frame, features, family, variant['arms'][family], variant['permutation_seed'], role)
            for feature in features:
                target[plan['slot_mapping'][feature]] = values[feature]
            family_audits[family][role] = audit
        ordered_slots.extend(plan['slot_mapping'][feature] for feature in features)
    assert list(atr) == list(ate) == fold['audit']['ordered_base_columns'] + ordered_slots
    assert _matrix_hash(atr[fold['audit']['ordered_base_columns']]) == fold['audit']['training_matrix_hash']
    assert _matrix_hash(ate[fold['audit']['ordered_base_columns']]) == fold['audit']['validation_matrix_hash']
    return atr, ate, family_audits


def make_registered_model(cfg):
    from tabicl import TabICLRegressor
    parameters = dict(device='cuda', n_estimators=int(cfg.get('icl_n', 8)), **cfg.get('icl_kwargs', {}))
    model = TabICLRegressor(**parameters)
    actual = model.get_params()
    assert all(actual[key] == value for key, value in parameters.items()), 'Registered constructor parameters changed'
    return model, parameters


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}, 'diagnostic_only': True}
    try:
        E, plan, g, folds = _prepared()
        variant = next(v for v in plan['variants'] if v['id'] == vid)
        assert variant_override is None or variant_override == variant
        assert vseed in plan['seeds']
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            atr, ate, family_audits = _design(fold, variant, plan)
            E.H.audit_features(list(atr))
            # Fail closed if the installed model rejects registered parameters.
            model, registered_parameters = make_registered_model(E.cfg_of('tabicl', g, list(atr)))
            model.fit(atr.astype(float), fold['yy'])
            pred = model.predict(ate.astype(float))
            assert len(pred) == len(ate) and np.isfinite(np.asarray(pred)).all()
            score = rho(pred, fold['truth'])
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr), 'cutoff': fold['cutoff'],
                   'max_label_season': fold['audit']['max_label_season'], 'stack': score,
                   'draft': rho(-fold['te'].actual_pick, fold['truth']), 'members': {'tabicl': score},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'families': family_audits,
                             'registered_model_parameters': registered_parameters,
                             'raw_feature_count': len(atr.columns), 'training_nonconstant_columns': int((atr.nunique() > 1).sum())},
                   'predictions': [{'pid': pid, 'score': float(v)} for pid, v in zip(fold['te'].pid, pred)]}
            rows.append(row)
            print(json.dumps({'variant': vid, 'seed': vseed, 'fold': {k: v for k, v in row.items() if k not in ['audit', 'predictions']}, 'diagnostic_only': True}), flush=True)
        entry = {'config': dict(variant), 'seed': vseed, 'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True}
    except Exception as error:
        traceback.print_exc()
        entry['error'] = str(error)
    entry['seconds'] = round(time.time() - start, 1)
    return entry


def _check_matched(a, b):
    for field in ['n', 'ntrain', 'cutoff', 'max_label_season']:
        assert a[field] == b[field]
    for field in ['input_columns', 'raw_feature_count', 'training_nonconstant_columns']:
        assert a['audit'][field] == b['audit'][field]
    assert set(a['audit']['families']) == set(b['audit']['families'])
    for family in a['audit']['families']:
        for role in ['train', 'validation']:
            for field in ['features', 'invariants']:
                assert a['audit']['families'][family][role][field] == b['audit']['families'][family][role][field]


def summarize_matched(candidates):
    plan = json.loads((ROOT / 'plan.json').read_text())
    registered = {v['id']: v for v in plan['variants']}
    tasks = {}
    for entry in candidates:
        if 'score' not in entry:
            continue
        task = entry.get('task_id', entry['config']['id'])
        vid, seed = task.rsplit('_seed', 1) if '_seed' in task else (entry['config']['id'], entry['seed'])
        seed = int(seed)
        config = dict(entry['config'])
        assert config['id'] in [vid, task]
        config['id'] = vid
        assert vid in registered and config == registered[vid] and seed in plan['seeds']
        assert 'seed' not in entry or int(entry['seed']) == seed
        assert (vid, seed) not in tasks and entry['diagnostic_only']
        assert len(entry['rows']) == len(plan['folds']) and {r['season'] for r in entry['rows']} == set(plan['folds'])
        assert np.isclose(entry['score'], np.mean([r['stack'] for r in entry['rows']]))
        tasks[(vid, seed)] = entry
    for year in plan['folds']:
        audits = [next(r['audit'] for r in entry['rows'] if r['season'] == year) for entry in tasks.values()]
        for field in ['study_hash', 'ordered_base_columns', 'base_columns_hash', 'training_pid_hash', 'validation_pid_hash',
                      'training_labels_hash', 'training_matrix_hash', 'validation_matrix_hash', 'source_selection_hash']:
            assert len({_hash(a[field]) for a in audits}) <= 1, f'Unfixed base/selection: {year}/{field}'
        assert all(a['source_only_baseline'] and a['max_label_season'] <= year - 1 and a['training_max_draft_year'] <= year - 2 for a in audits)
    streams = collections.defaultdict(set)
    for (vid, _), entry in tasks.items():
        variant = registered[vid]
        for row in entry['rows']:
            assert set(row['audit']['families']) == set(variant['arms'])
            expected_slots = [plan['slot_mapping'][column]
                              for family in ['combine', 'consensus'] if family in variant['arms']
                              for column in plan['training_eligibility_registration'][str(row['season'])][family]]
            assert row['audit']['input_columns'] == row['audit']['ordered_base_columns'] + expected_slots
            assert row['audit']['raw_feature_count'] == len(row['audit']['input_columns'])
            for family, roles in row['audit']['families'].items():
                assert family in variant['arms']
                assert set(roles) == {'train', 'validation'}
                mode = 'real' if variant['arms'][family] == 'real' else variant['permutation_seed']
                for role, audit in roles.items():
                    assert audit['features'] == plan['training_eligibility_registration'][str(row['season'])][family]
                    streams[(family, mode, row['season'], role)].add(audit['matrix_hash'])
    assert all(len(hashes) == 1 for hashes in streams.values()), 'Family shuffle changed across solo/joint arms or fit seeds'
    def row(vid, seed, year):
        return next(r for r in tasks[(vid, seed)]['rows'] if r['season'] == year)
    statistics, pending = [], []
    for family in ['combine', 'consensus']:
        vids = [v['id'] for v in plan['variants'] if v['scope'] == family]
        required = [(vid, seed) for vid in vids for seed in plan['seeds']]
        if not all(k in tasks for k in required):
            pending.append(family)
            continue
        paired = []
        for seed in plan['seeds']:
            for year in plan['folds']:
                real = row(family + '_real', seed, year)
                controls = [row(f'{family}_shuffle{pseed}', seed, year) for pseed in plan['permutation_seeds']]
                for control in controls:
                    _check_matched(real, control)
                paired.append({'seed': seed, 'season': year, 'real': real['stack'], 'mean_control': float(np.mean([r['stack'] for r in controls])),
                               'gain': real['stack'] - float(np.mean([r['stack'] for r in controls]))})
        statistics.append({'id': family, 'paired_mean_gain': float(np.mean([p['gain'] for p in paired])), 'paired_rows': paired,
                           'fold_gains': {str(y): float(np.mean([p['gain'] for p in paired if p['season'] == y])) for y in plan['folds']}})
    factorial_vids = [v['id'] for v in plan['variants'] if v['scope'] == 'joint']
    factorial = None
    if all((vid, seed) in tasks for vid in factorial_vids for seed in plan['seeds']):
        contrasts = []
        for seed in plan['seeds']:
            for year in plan['folds']:
                rr = row('joint_RR', seed, year)
                for pseed in plan['permutation_seeds']:
                    rp, pr, pp = [row(f'joint_{code}_shuffle{pseed}', seed, year) for code in ['RP', 'PR', 'PP']]
                    for control in [rp, pr, pp]:
                        _check_matched(rr, control)
                    contrasts.append({'seed': seed, 'season': year, 'permutation_seed': pseed,
                                      'RR': rr['stack'], 'RP': rp['stack'], 'PR': pr['stack'], 'PP': pp['stack'],
                                      'consensus_given_combine': rr['stack'] - rp['stack'],
                                      'combine_given_consensus': rr['stack'] - pr['stack'],
                                      'interaction': rr['stack'] - rp['stack'] - pr['stack'] + pp['stack']})
        measures = ['consensus_given_combine', 'combine_given_consensus', 'interaction']
        factorial = {'contrasts': contrasts, 'mean_contrasts': {m: float(np.mean([r[m] for r in contrasts])) for m in measures},
                     'fold_contrasts': {str(y): {m: float(np.mean([r[m] for r in contrasts if r['season'] == y])) for m in measures} for y in plan['folds']}}
    else:
        pending.append('joint_factorial')
    baseline = float(np.mean([tasks[('baseline', seed)]['score'] for seed in plan['seeds']])) if all(('baseline', seed) in tasks for seed in plan['seeds']) else None
    return {'statistics': statistics, 'factorial': factorial, 'pending': pending, 'completed_tasks': len(tasks), 'expected_tasks': 57,
            'baseline_score_context_only': baseline, 'diagnostic_only': True, 'automatic_promotion': False,
            'interpretation': 'Pre-2019 exploratory contrasts on a fixed source-only college baseline. Whole-family row shuffles retain within-family structure and exact masks; immovable strata limit the contrast. Conditional RR-RP/PR comparisons are matched in shape. Repeated RR/seed/fold contrasts are not independent datasets. No clean test claim, significance test, or automatic promotion.'}
