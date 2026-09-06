"""R8v: fixed model-family comparison on canonical college+consensus.

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
import math
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


def _canonical_rows(frame):
    """Identity determines presentation order only, never a predictor."""
    assert frame.pid.is_unique and frame.pid.map(lambda p: isinstance(p, str)).all()
    indices = sorted(range(len(frame)), key=lambda i: (hashlib.sha256(frame.iloc[i].pid.encode()).hexdigest(), frame.iloc[i].pid))
    return frame.iloc[indices].copy().reset_index(drop=True)


def _exact_vector_keys(frame):
    # Use exact float representations, but normalize equivalent zeros/NaNs.
    # No tolerance or decimal rounding can merge distinct numerical vectors.
    assert np.isfinite(frame.stack().dropna().to_numpy(dtype=float)).all()
    return [tuple(None if pd.isna(v) else ('0x0.0p+0' if float(v) == 0 else float(v).hex()) for v in row)
            for row in frame.to_numpy()]


def _canonical_predictions(frame, raw, pids):
    raw = np.asarray(raw, dtype=float)
    assert len(raw) == len(frame) == len(pids) and len(set(pids)) == len(pids) and np.isfinite(raw).all()
    groups = collections.defaultdict(list)
    vector_keys = _exact_vector_keys(frame)
    for i, key in enumerate(vector_keys):
        groups[key].append(i)
    result = raw.copy()
    duplicates = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        mean = math.fsum(sorted(float(raw[i]) for i in indices)) / len(indices)
        result[indices] = mean
        duplicates.append({'pids': sorted(pids[i] for i in indices), 'rows': len(indices),
                           'all_predictors_missing': bool(frame.iloc[indices].isna().all().all()),
                           'raw_min': float(raw[indices].min()), 'raw_max': float(raw[indices].max()),
                           'assigned_score': mean})
    audit = {'policy': 'sha256_pid_exact_vector_mean_v1', 'rows': len(raw), 'distinct_input_vectors': len(groups),
             'duplicate_groups': sorted(duplicates, key=lambda g: g['pids']),
             'changed_rows': int(np.count_nonzero(result != raw)),
             'max_abs_change': float(np.max(np.abs(result - raw))),
             'raw_prediction_hash': hashlib.sha256(raw.tobytes()).hexdigest(),
             'canonical_prediction_hash': hashlib.sha256(result.tobytes()).hexdigest(),
             'row_vector_hashes': [_hash(key) for key in vector_keys],
             'distinct_vectors_quantized': False}
    return result, audit


def _load_inputs():
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    assert plan['ordering_policy']['version'] == 'sha256_pid_exact_vector_mean_v1'
    assert len(plan['tasks']) == 48 and len({(t['variant'],t['seed']) for t in plan['tasks']}) == 48
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
    for family in ['combine', 'consensus', 'bio']:
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
    bio = pd.read_csv(DATA / 'bio_provenance.csv')
    bm = json.loads((DATA / 'bio_metadata.json').read_text())
    bv = json.loads((DATA / 'bio_verification.json').read_text())
    assert bv['matched_players'] == bm['players'] == 374 and bv['source_cells_checked'] == 480
    assert not bv['models_or_NBA_outcomes_used'] and bm['features'] == plan['families']['bio']
    assert bio.pid.is_unique and bio.draft_year.between(2007, 2014).all()
    bio = bio[bio.pid.isin(x.pid)].copy()
    assert bio.pid.map(year_by_pid).equals(bio.draft_year)
    observed = sources['bio'].loc[sources['bio'][plan['families']['bio']].notna().any(axis=1), 'pid']
    assert set(observed) == set(bio.pid)
    bio_sources = {f"dx_{source['draft_year']}": source for source in bm['sources']}
    dx = cons[cons.publisher == 'dx'].set_index('pid')
    for row in bio.itertuples():
        source = bio_sources[row.source_id]
        assert row.pid in dx.index and dx.loc[row.pid, 'source_id'] == row.source_id
        assert row.table_row_ordinal == dx.loc[row.pid, 'mock_rank']
        assert row.table_sha256 == source['table_sha256'] and row.html_sha256 == source['html_sha256']
        assert row.archive_url == source['archive_url'] and row.capture_utc == source['source_available_by_utc']
        assert row.draft_date == source['draft_date'] and source['source_last_updated_date'] < row.draft_date
        cutoff = datetime.datetime.fromisoformat(row.draft_date).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        assert datetime.datetime.fromisoformat(row.capture_utc) < cutoff and 1 <= row.table_row_ordinal <= 60
        assert pd.isna(row.age_precision_years) or row.age_precision_years in [1., .1]
    for family in ['combine', 'consensus', 'bio']:
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
    assert role in ['train', 'validation'] and (family == 'consensus' or family.startswith('bio:'))
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
        tr = _canonical_rows(x[(x.draft_year >= g['win']) & (x.draft_year <= year - 2)])
        te = _canonical_rows(x[(x.draft_year == year) & (x.was_drafted == 1)])
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
        for family in ['combine', 'consensus', 'bio']:
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
                 'source_only_baseline': True, 'diagnostic_only': True, 'ordering_policy_hash': _hash(plan['ordering_policy'])}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te, 'btr': btr[selected].copy(),
                      'bte': bte[selected].copy(), 'yy': yy, 'truth': truth, 'source_columns': source_columns, 'audit': audit})
    _CACHE = E, plan, g, folds
    return _CACHE


def _design(fold, variant, plan):
    atr, ate = fold['btr'].copy(), fold['bte'].copy()
    assert variant['arms'].get('consensus') == 'real' and 'combine' not in variant['arms']
    assert variant['feature'] is None if variant['bio_arm'] == 'absent' else variant['feature'] in plan['single_features']
    family_audits, ordered_slots = {}, []
    for family in ['consensus', 'bio']:
        if family not in variant['arms']: continue
        features = fold['source_columns']['consensus'] if family == 'consensus' else [variant['feature']]
        assert all(c in fold['source_columns'][family] for c in features)
        family_audits[family] = {}
        stream = family if family == 'consensus' else 'bio:' + variant['feature']
        for role, frame, target in [('train', fold['tr'], atr), ('validation', fold['te'], ate)]:
            values, audit = _source_values(frame, features, stream, variant['arms'][family], variant['permutation_seed'], role)
            for feature in features:
                target[plan['slot_mapping'][feature] if family == 'consensus' else plan['common_bio_slot']] = values[feature]
            family_audits[family][role] = audit
        ordered_slots.extend(plan['slot_mapping'][feature] if family == 'consensus' else plan['common_bio_slot'] for feature in features)
    assert list(atr) == list(ate) == fold['audit']['ordered_base_columns'] + ordered_slots
    assert len(atr.columns) == (45 if variant['bio_arm'] == 'absent' else 46)
    assert _matrix_hash(atr[fold['audit']['ordered_base_columns']]) == fold['audit']['training_matrix_hash']
    assert _matrix_hash(ate[fold['audit']['ordered_base_columns']]) == fold['audit']['validation_matrix_hash']
    return atr, ate, family_audits


def _jsonable(value):
    if isinstance(value, (float,np.floating)) and not np.isfinite(value): return str(value)
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, dict): return {str(k): _jsonable(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [_jsonable(v) for v in value]
    if isinstance(value, (str,int,float,bool,type(None))): return value
    return repr(value)


def make_registered_model(spec, seed):
    parameters = {k: seed if v == 'task_seed' else v for k,v in spec['parameters'].items()}
    assert seed in spec['seeds']
    if spec['family'] == 'tabicl':
        from tabicl import TabICLRegressor
        model = TabICLRegressor(**parameters)
    elif spec['family'] == 'extratrees':
        from sklearn.ensemble import ExtraTreesRegressor
        model = ExtraTreesRegressor(**parameters)
        assert model.__sklearn_tags__().input_tags.allow_nan, 'Installed ExtraTrees lacks registered native NaN support'
    elif spec['family'] == 'xgb':
        from xgboost import XGBRegressor
        assert parameters['device'] == 'cpu' and parameters['tree_method'] == 'hist'
        model = XGBRegressor(**parameters)
    elif spec['family'] == 'ridge':
        from sklearn.linear_model import Ridge
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        model = Pipeline([('imputer', SimpleImputer(**spec['preprocessing']['imputer'])),
                          ('scaler', StandardScaler(**spec['preprocessing']['scaler'])),
                          ('regressor', Ridge(**parameters))])
        assert all(model.named_steps['imputer'].get_params()[k] == v for k,v in spec['preprocessing']['imputer'].items())
        assert all(model.named_steps['scaler'].get_params()[k] == v for k,v in spec['preprocessing']['scaler'].items())
    else: raise AssertionError('Unregistered model family')
    actual = model.named_steps['regressor'].get_params() if spec['family'] == 'ridge' else model.get_params()
    assert all(actual[k] == v for k,v in parameters.items()), 'Registered constructor parameter changed'
    return model, parameters


def _predict_model(spec, seed, atr, yy, ate):
    import importlib.metadata
    model, parameters = make_registered_model(spec, seed)
    assert list(atr) == list(ate) and 'actual_pick' not in atr
    model.fit(atr.astype(float), yy)
    raw = np.asarray(model.predict(ate.astype(float)), dtype=float)
    audit = {'family': spec['family'], 'registered_parameters': parameters,
             'input_features': len(atr.columns), 'training_rows': len(atr),
             'validation_rows': len(ate), 'training_only_preprocessing': True,
             'installed_versions': {name: importlib.metadata.version(name) for name in ['scikit-learn','xgboost','tabicl']}}
    if spec['family'] == 'ridge':
        imputer, scaler = model.named_steps['imputer'], model.named_steps['scaler']
        transformed = imputer.transform(atr.astype(float))
        assert int(scaler.n_samples_seen_) == len(atr)
        audit['preprocessing'] = {'imputer_training_statistics': _jsonable(imputer.statistics_),
            'missing_indicator_input_indices': imputer.indicator_.features_.tolist(),
            'scaler_training_mean': _jsonable(scaler.mean_), 'scaler_training_scale': _jsonable(scaler.scale_),
            'scaler_training_samples_seen': int(scaler.n_samples_seen_), 'transformed_width': transformed.shape[1],
            'training_transformed_hash': hashlib.sha256(np.asarray(transformed,dtype=np.float64).tobytes()).hexdigest()}
        assert np.isfinite(imputer.statistics_).all() and np.isfinite(scaler.mean_).all() and np.isfinite(scaler.scale_).all()
    elif spec['family'] == 'tabicl':
        generator=model.ensemble_generator_
        actual_count=sum(len(group) for group in generator.ensemble_configs_.values())
        audit.update(effective_estimator_count=actual_count, effective_feature_count=int(generator.n_features_in_),
                     effective_constructor=_jsonable(model.get_params(deep=False)))
        assert 0 < actual_count <= parameters['n_estimators']
    else:
        audit['native_nan_processing'] = True
        audit['effective_constructor'] = _jsonable(model.get_params(deep=False))
    return raw, audit


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}, 'diagnostic_only': True}
    try:
        E, plan, g, folds = _prepared()
        variant = next(v for v in plan['variants'] if v['id'] == vid)
        assert variant_override is None or variant_override == variant
        assert {'variant':vid,'seed':vseed} in plan['tasks']
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            atr, ate, family_audits = _design(fold, variant, plan)
            E.H.audit_features(list(atr))
            spec=plan['models'][variant['model_id']]
            raw_pred, model_audit = _predict_model(spec, vseed, atr, fold['yy'], ate)
            assert len(raw_pred) == len(ate) and np.isfinite(raw_pred).all()
            pred, tie_audit = _canonical_predictions(ate, raw_pred, fold['te'].pid.tolist())
            score = rho(pred, fold['truth'])
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr), 'cutoff': fold['cutoff'],
                   'max_label_season': fold['audit']['max_label_season'], 'stack': score,
                   'draft': rho(-fold['te'].actual_pick, fold['truth']), 'members': {variant['model_id']: score},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'families': family_audits,
                             'registered_model_parameters': model_audit['registered_parameters'], 'model': model_audit, 'canonical_prediction_ties': tie_audit,
                             'raw_feature_count': len(atr.columns), 'training_nonconstant_columns': int((atr.nunique() > 1).sum())},
                   'predictions': [{'pid': pid, 'score': float(v), 'raw_score': float(raw)} for pid, v, raw in zip(fold['te'].pid, pred, raw_pred)]}
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


def _validate_tie_record(row):
    tie = row['audit']['canonical_prediction_ties']
    assert tie['policy'] == 'sha256_pid_exact_vector_mean_v1' and not tie['distinct_vectors_quantized']
    records = row['predictions']
    pids = [record['pid'] for record in records]
    assert len(pids) == len(set(pids)) == row['n'] == tie['rows']
    assert pids == sorted(pids, key=lambda pid: (hashlib.sha256(pid.encode()).hexdigest(), pid))
    raw = np.asarray([record['raw_score'] for record in records], dtype=float)
    canonical = np.asarray([record['score'] for record in records], dtype=float)
    assert np.isfinite(raw).all() and np.isfinite(canonical).all()
    assert hashlib.sha256(raw.tobytes()).hexdigest() == tie['raw_prediction_hash']
    assert hashlib.sha256(canonical.tobytes()).hexdigest() == tie['canonical_prediction_hash']
    expected = raw.copy()
    seen = set()
    vectors = tie['row_vector_hashes']
    assert len(vectors) == row['n'] and all(isinstance(v, str) and len(v) == 64 for v in vectors)
    expected_groups = collections.defaultdict(list)
    for pid, vector in zip(pids, vectors): expected_groups[vector].append(pid)
    assert sorted(sorted(group) for group in expected_groups.values() if len(group) > 1) == sorted(group['pids'] for group in tie['duplicate_groups'])
    for group in tie['duplicate_groups']:
        assert group['rows'] == len(group['pids']) >= 2 and group['pids'] == sorted(set(group['pids']))
        assert not seen & set(group['pids']) and set(group['pids']) <= set(pids)
        seen.update(group['pids'])
        indices = [pids.index(pid) for pid in group['pids']]
        assigned = math.fsum(sorted(float(raw[i]) for i in indices)) / len(indices)
        assert assigned == group['assigned_score']
        assert float(raw[indices].min()) == group['raw_min'] and float(raw[indices].max()) == group['raw_max']
        expected[indices] = assigned
    assert np.array_equal(expected, canonical)
    assert tie['distinct_input_vectors'] == row['n'] - sum(g['rows'] - 1 for g in tie['duplicate_groups'])
    assert tie['changed_rows'] == int(np.count_nonzero(raw != canonical))
    assert tie['max_abs_change'] == float(np.max(np.abs(raw - canonical)))


def summarize_matched(candidates):
    plan=json.loads((ROOT/'plan.json').read_text())
    registered={v['id']:v for v in plan['variants']}
    allowed={(t['variant'],t['seed']) for t in plan['tasks']}
    tasks={}
    for entry in candidates:
        if 'score' not in entry: continue
        task=entry.get('task_id',entry['config']['id'])
        vid,seed=task.rsplit('_seed',1) if '_seed' in task else (entry['config']['id'],entry['seed'])
        seed=int(seed);config=dict(entry['config']);config['id']=vid
        assert (vid,seed) in allowed and config==registered[vid] and entry['seed']==seed and (vid,seed) not in tasks
        assert entry['diagnostic_only'] and {r['season'] for r in entry['rows']}==set(plan['folds']) and len(entry['rows'])==len(plan['folds'])
        assert np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]))
        variant=registered[vid];spec=plan['models'][variant['model_id']]
        expected={k:seed if v=='task_seed' else v for k,v in spec['parameters'].items()}
        for row in entry['rows']:
            audit=row['audit'];assert audit['registered_model_parameters']==expected
            assert audit['model']['registered_parameters']==expected and audit['model']['family']==spec['family']
            assert audit['ordering_policy_hash']==_hash(plan['ordering_policy'])
            assert audit['max_label_season']<=row['season']-1 and audit['training_max_draft_year']<=row['season']-2
            assert audit['model']['training_rows']==row['ntrain'] and audit['model']['validation_rows']==row['n']
            assert audit['model']['training_only_preprocessing']
            model_audit=audit['model']
            if spec['family']=='ridge':
                assert 'preprocessing' in model_audit
                prep=model_audit['preprocessing'];indices=prep['missing_indicator_input_indices']
                assert len(prep['imputer_training_statistics'])==audit['raw_feature_count']
                assert indices==sorted(set(indices)) and all(0<=i<audit['raw_feature_count'] for i in indices)
                assert prep['transformed_width']==audit['raw_feature_count']+len(indices)
                assert len(prep['scaler_training_mean'])==len(prep['scaler_training_scale'])==prep['transformed_width']
                assert prep['scaler_training_samples_seen']==row['ntrain']
                assert all(np.isfinite(prep[k]).all() for k in ['imputer_training_statistics','scaler_training_mean','scaler_training_scale'])
                assert len(prep['training_transformed_hash'])==64
            else:
                assert 'effective_constructor' in model_audit
                assert all(model_audit['effective_constructor'][k]==v for k,v in expected.items())
                if spec['family']=='tabicl':
                    assert 'effective_estimator_count' in model_audit and 'effective_feature_count' in model_audit
                    assert model_audit['effective_constructor']['feat_shuffle_method']=='latin'
                    assert 0<model_audit['effective_feature_count']<=audit['raw_feature_count']
                    assert model_audit['effective_estimator_count']==min(expected['n_estimators'],model_audit['effective_feature_count'])
                else:assert model_audit['native_nan_processing']
            slots=[plan['slot_mapping'][c] for c in plan['families']['consensus']]
            if variant['feature']:slots.append(plan['common_bio_slot'])
            assert audit['input_columns']==audit['ordered_base_columns']+slots
            assert audit['raw_feature_count']==audit['model']['input_features']==len(audit['input_columns'])
            assert set(audit['families'])==set(variant['arms'])
            _validate_tie_record(row)
        tasks[(vid,seed)]=entry
    for year in plan['folds']:
        audits=[next(r['audit'] for r in e['rows'] if r['season']==year) for e in tasks.values()]
        for key in ['study_hash','ordered_base_columns','base_columns_hash','training_pid_hash','validation_pid_hash','training_labels_hash','training_matrix_hash','validation_matrix_hash','source_selection_hash','ordering_policy_hash']:
            assert len({_hash(a[key]) for a in audits})<=1,('Changed fixed baseline',year,key)
        for family in ['consensus','bio']:
            values=[a['families'][family] for a in audits if family in a['families']]
            assert len({_hash(value) for value in values})<=1,('Changed source family',year,family)
    references=json.loads((ROOT/'baseline_reference.json').read_text())['references']
    replay=[];missing=[]
    for ref in references:
        key=(ref['background']+'_tabicl32',ref['seed'])
        if key not in tasks:missing.append(key);continue
        current=tasks[key]
        assert current['score']==ref['score'],('Baseline score changed',key)
        for a,b in zip(current['rows'],ref['rows']):
            assert a['season']==b['season'] and a['stack']==b['stack'] and a['predictions']==b['predictions'],('Baseline predictions changed',key,a['season'])
        replay.append({'background':ref['background'],'seed':ref['seed'],'exact_score_and_predictions':True})
    statistics=[]
    if not missing:
        for vid,variant in registered.items():
            seeds=plan['models'][variant['model_id']]['seeds']
            if not all((vid,s) in tasks for s in seeds):continue
            entries=[tasks[(vid,s)] for s in seeds]
            statistics.append({'id':vid,'background':variant['background'],'model_id':variant['model_id'],'seed_count':len(seeds),
                'mean_score':float(np.mean([e['score'] for e in entries])),
                'seed_scores':{str(s):tasks[(vid,s)]['score'] for s in seeds},
                'fold_scores':{str(y):float(np.mean([next(r['stack'] for r in e['rows'] if r['season']==y) for e in entries])) for y in plan['folds']}})
    return {'statistics':statistics,'completed_tasks':len(tasks),'expected_tasks':48,'baseline_replay_checks':replay,
        'baseline_replay_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,
        'interpretation':'Registered model-family diagnostic on fixed pre2019 folds, with optional SG chosen on prior development results. No blends, significance claim, promotion or held-out measurement.'}
