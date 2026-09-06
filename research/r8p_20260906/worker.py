"""R8p development diagnostics: fixed base and source-family matched controls.

Importing this module does not prepare models or launch GPU work. The inherited
baseline remains uncertified; no result from this study is a clean test claim.
"""
import os
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
from pathlib import Path
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
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _matrix_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()).hexdigest()


def rho(predictions, truth):
    value = float(spearmanr(predictions, truth).statistic)
    return value if np.isfinite(value) else 0.0


def _load_inputs():
    """Allowlisted local bundle, including row-level source/calendar assertions."""
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    assert len(plan['variants']) * len(plan['seeds']) == 39
    assert plan['baseline_source_variant'] == manifest['baseline_variant']
    for filename, expected in manifest['files'].items():
        assert Path(filename).name == filename, 'Only local data files are allowed'
        assert hashlib.sha256((DATA / filename).read_bytes()).hexdigest() == expected
    for name, expected in manifest['base_data_hashes'].items():
        assert manifest['files'][name] == expected, 'Inherited base data changed'
    x = pd.read_csv(DATA / 'features.csv')
    labels = pd.read_csv(DATA / 'labels.csv')
    source = pd.read_csv(DATA / 'source_features.csv')
    provenance = pd.read_csv(DATA / 'source_provenance.csv')
    dictionary = json.loads((DATA / 'source_dictionary.json').read_text())
    registered = plan['families']['numeric'] + plan['families']['text']
    assert registered == manifest['source_features']
    assert plan['families'] == manifest['source_families']
    assert x.pid.is_unique and (x.draft_year < 2019).all()
    assert labels.pid.isin(x.pid).all() and (labels.season_end <= 2018).all()
    assert not labels.duplicated(['pid', 'ordinal']).any()
    assert labels.ordinal.between(1, 5).all()
    year_by_pid = x.set_index('pid').draft_year
    assert labels.pid.map(year_by_pid).equals(labels.draft_year)
    assert (labels.season_end >= labels.draft_year + labels.ordinal).all()
    assert source[['pid', 'draft_year']].equals(x[['pid', 'draft_year']])
    assert list(source) == ['pid', 'draft_year'] + registered
    assert not set(registered) & set(x), 'Source values must not enter base preprocessing'
    assert not any('agent' in c or 'invited' in c or 'listed_' in c for c in registered)
    assert all(dictionary[c]['family'] == 'synergy_situational' for c in plan['families']['numeric'])
    assert all(dictionary[c]['family'] == 'fixed_lexicon_text' for c in plan['families']['text'])
    assert (provenance.draft_year <= 2014).all() and provenance.pid.isin(x.pid).all()
    assert not provenance.duplicated(['pid', 'metric']).any()
    assert set(provenance.metric) <= set(registered)
    assert not provenance.source_id.str.startswith('nba').any()
    for row in provenance.itertuples():
        assert row.draft_year == year_by_pid[row.pid]
        assert row.publication_date < row.draft_date
        cutoff = datetime.datetime.fromisoformat(row.draft_date).replace(tzinfo=zoneinfo.ZoneInfo('America/New_York'))
        assert datetime.datetime.fromisoformat(row.capture_utc) < cutoff
    observed = source.set_index(['pid', 'draft_year'])[registered].stack().dropna().rename('value')
    observed.index.names = ['pid', 'draft_year', 'metric']
    expected = provenance.set_index(['pid', 'draft_year', 'metric']).value
    pd.testing.assert_series_equal(observed.sort_index(), expected.sort_index(), check_names=False)
    assert np.isfinite(observed.to_numpy()).all()
    joined = x.merge(source, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined.pid.tolist() == x.pid.tolist() and len(joined) == len(x)
    return plan, manifest, joined, labels


def _eligible_columns(training, registered, rule):
    """This selector has no validation input or target argument by construction."""
    assert not rule['validation_coverage_used']
    audit = []
    for feature in registered:
        values = pd.to_numeric(training[feature], errors='raise')
        count, unique = int(values.notna().sum()), int(values.nunique())
        keep = count >= rule['min_training_observed'] and unique >= rule['min_training_unique']
        audit.append({'feature': feature, 'training_observed': count, 'training_unique': unique, 'eligible': keep})
    return [row['feature'] for row in audit if row['eligible']], audit


def _permuted(values, metadata, feature, seed, role):
    """Keep exact NaN positions and within-cohort distributions for each column."""
    assert values.index.equals(metadata.index) and metadata.pid.is_unique
    assert role in ['train', 'validation']
    out = pd.to_numeric(values, errors='raise').astype(float).copy()
    for year in sorted(metadata.draft_year.unique()):
        indices = metadata.loc[(metadata.draft_year == year) & values.notna()].sort_values('pid', kind='stable').index
        stable_seed = int.from_bytes(hashlib.sha256(json.dumps([feature, int(seed), role, int(year)]).encode()).digest()[:8], 'little')
        out.loc[indices] = np.random.default_rng(stable_seed).permutation(values.loc[indices].to_numpy())
        assert np.array_equal(np.sort(out.loc[indices]), np.sort(values.loc[indices]))
    assert out.isna().equals(values.isna())
    return out


def _prepared():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    import legacy_kernel as E
    import xgboost as xgb
    plan, manifest, x, labels = _load_inputs()
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    assert cfg['topk'] == 60
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
    drop = cfg['drop'] + plan['baseline_source_variant']['additional_drop']
    columns = [c for c in manifest['legacy_features'] if not any(c.startswith(prefix) for prefix in drop)]
    assert not any(c.startswith(('f50_', 'slot_', 'report_')) for c in columns)
    for col in manifest['legacy_features']:
        if any(col.startswith(prefix) for prefix in drop):
            x[col] = np.nan
    E.setup(columns)
    study_hash = _hash({'plan': plan, 'data_files': manifest['files'], 'kernel': hashlib.sha256((ROOT / 'legacy_kernel.py').read_bytes()).hexdigest()})
    folds = []
    for year in plan['folds']:
        assert year in [2012, 2013, 2014]
        cutoff, k = year - 1, min(5, 2018 - year)
        tr = x[(x.draft_year >= int(g['win'])) & (x.draft_year <= cutoff - 1)].copy().reset_index(drop=True)
        te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
        assert len(tr) and len(te) and not set(tr.pid) & set(te.pid)
        assert (tr.draft_year <= year - 2).all() and (te.draft_year == year).all()
        used = labels[(labels.season_end <= cutoff) & labels.pid.isin(tr.pid)]
        assert len(used) and (used.season_end <= year - 1).all()
        assert not set(used.pid) & set(te.pid)
        for ordinal in range(1, 6):
            tr[f'y_s{ordinal}_war'] = tr.pid.map(used[used.ordinal == ordinal].set_index('pid').war)
        opts = E.opts_of(g)
        base = E.H.cols_for(opts)
        all_columns = E.cols_of(g, base)
        assert not any(c.startswith(('f50_', 'slot_', 'report_')) for c in all_columns)
        E.H.audit_features(all_columns)
        prior, quantiles = E.H.fit_prior(tr)
        btr, bte = E.H.build(tr, prior, quantiles, opts), E.H.build(te, prior, quantiles, opts)
        rates = [c for c in base if c.startswith(('col_', 'intl_')) and not c.startswith('col_gl_')]
        btr, bte = E.feat_tx(btr, bte, g['fx'], tr, te, rates)
        stats = E.stats_of(btr)
        btr, bte = E.add_feats(btr, g['fx'], stats), E.add_feats(bte, g['fx'], stats)
        yy = E.label(tr, E.specs(g)[0], k)
        selector = xgb.XGBRegressor(max_depth=3, n_estimators=300, learning_rate=.05,
                                   subsample=.8, colsample_bytree=.6, n_jobs=2,
                                   device='cpu', tree_method='hist', random_state=11)
        selector.fit(btr[all_columns], yy)
        selected = [c for _, c in sorted(zip(selector.feature_importances_, all_columns), reverse=True)[:60]]
        assert len(selected) == 60 and len(set(selected)) == 60
        assert not any(c.startswith('bio_') for c in selected)
        if 'x_rim' in selected:
            assert btr.x_rim.isna().all() and bte.x_rim.isna().all()
        source_columns, source_selection = {}, {}
        for family in ['numeric', 'text']:
            source_columns[family], source_selection[family] = _eligible_columns(tr, plan['families'][family], plan['source_filter'])
        source_columns['joint'] = source_columns['numeric'] + source_columns['text']
        source_columns['baseline'] = []
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        audit = {'study_hash': study_hash, 'ordered_base_columns': selected, 'base_columns_hash': _hash(selected),
                 'training_pid_hash': _hash(tr.pid.tolist()), 'validation_pid_hash': _hash(te.pid.tolist()),
                 'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                 'training_matrix_hash': _matrix_hash(btr[selected]),
                 'baseline_source_variant': plan['baseline_source_variant']['id'],
                 'source_selection': source_selection, 'source_selection_hash': _hash(source_selection),
                 'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                 'diagnostic_only': True}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te,
                      'btr': btr[selected].copy(), 'bte': bte[selected].copy(), 'yy': yy, 'truth': truth,
                      'source_columns': source_columns, 'audit': audit})
    _CACHE = E, plan, g, folds
    return _CACHE


def _slots(frame, features, variant, plan, role):
    slots, audit = {}, []
    for feature in features:
        values = pd.to_numeric(frame[feature], errors='raise').astype(float)
        assert not np.isinf(values.to_numpy()).any()
        value = values.copy() if variant['arm'] == 'real' else _permuted(values, frame, feature, variant['permutation_seed'], role)
        slot = plan['slot_mapping'][feature]
        slots[slot] = value
        audit.append({'slot': slot, 'feature': feature,
                      'mask_hash': hashlib.sha256(value.isna().to_numpy().tobytes()).hexdigest(),
                      'observed': int(value.notna().sum()), 'unique_observed': int(value.nunique()),
                      'cohort_distribution_hash': _hash([[int(year), sorted(value[frame.draft_year == year].dropna().tolist())] for year in sorted(frame.draft_year.unique())])})
    return slots, audit


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}, 'diagnostic_only': True}
    try:
        E, plan, g, folds = _prepared()
        variant = next(v for v in plan['variants'] if v['id'] == vid)
        assert variant_override is None or variant_override == variant, 'Unregistered override prohibited'
        assert vseed in plan['seeds']
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            features = fold['source_columns'][variant['family']]
            atr, ate = fold['btr'].copy(), fold['bte'].copy()
            tr_slots, tr_audit = _slots(fold['tr'], features, variant, plan, 'train')
            te_slots, te_audit = _slots(fold['te'], features, variant, plan, 'validation')
            for slot in tr_slots:
                atr[slot], ate[slot] = tr_slots[slot], te_slots[slot]
            assert list(atr) == list(ate) == fold['audit']['ordered_base_columns'] + [plan['slot_mapping'][c] for c in features]
            assert _matrix_hash(atr[fold['audit']['ordered_base_columns']]) == fold['audit']['training_matrix_hash']
            E.H.audit_features(list(atr))
            pred = E.H.predict('tabicl', atr, fold['yy'], ate, E.cfg_of('tabicl', g, list(atr)))
            assert len(pred) == len(ate) and np.isfinite(np.asarray(pred)).all(), 'Invalid model predictions'
            score = rho(pred, fold['truth'])
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr),
                   'cutoff': fold['cutoff'], 'max_label_season': fold['audit']['max_label_season'],
                   'stack': score, 'draft': rho(-fold['te'].actual_pick, fold['truth']), 'members': {'tabicl': score},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'source_columns': features,
                             'raw_feature_count': len(atr.columns), 'training_nonconstant_columns': int((atr.nunique() > 1).sum()),
                             'train_slots': tr_audit, 'validation_slots': te_audit},
                   'predictions': [{'pid': pid, 'score': float(value)} for pid, value in zip(fold['te'].pid, pred)]}
            rows.append(row)
            print(json.dumps({'variant': vid, 'seed': vseed, 'fold': {k: v for k, v in row.items() if k not in ['audit', 'predictions']}, 'diagnostic_only': True}), flush=True)
        entry = {'config': dict(variant), 'seed': vseed, 'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True}
    except Exception as error:
        traceback.print_exc()
        entry['error'] = str(error)
    entry['seconds'] = round(time.time() - start, 1)
    return entry


def summarize_matched(candidates):
    """Summarize complete paired families; preserve the model-seed pairing."""
    plan = json.loads((ROOT / 'plan.json').read_text())
    by_task = {}
    registered = {v['id'] for v in plan['variants']}
    for row in candidates:
        if 'score' not in row:
            continue
        task_id = row.get('task_id', row['config']['id'])
        vid, seed = task_id.rsplit('_seed', 1) if '_seed' in task_id else (row['config']['id'], row['seed'])
        seed = int(seed)
        assert vid in registered and seed in plan['seeds'] and (vid, seed) not in by_task
        assert {r['season'] for r in row['rows']} == set(plan['folds']) and len(row['rows']) == len(plan['folds'])
        assert np.isclose(row['score'], np.mean([r['stack'] for r in row['rows']]))
        assert row['diagnostic_only']
        by_task[(vid, seed)] = row
    for year in plan['folds']:
        audits = [next(f['audit'] for f in r['rows'] if f['season'] == year) for r in by_task.values()]
        for field in ['study_hash', 'base_columns_hash', 'training_pid_hash', 'validation_pid_hash', 'training_labels_hash', 'training_matrix_hash', 'source_selection_hash']:
            assert len({a[field] for a in audits}) <= 1, f'Base or source selector changed: {year}/{field}'
        assert all(a['max_label_season'] <= year - 1 and a['training_max_draft_year'] <= year - 2 for a in audits)
    baseline_keys = [('baseline', seed) for seed in plan['seeds']]
    baseline = float(np.mean([by_task[k]['score'] for k in baseline_keys])) if all(k in by_task for k in baseline_keys) else None
    statistics, pending = [], []
    for family in ['numeric', 'text', 'joint']:
        peers = [v for v in plan['variants'] if v['family'] == family]
        required = [(v['id'], seed) for v in peers for seed in plan['seeds']]
        if not all(key in by_task for key in required):
            pending.append(family)
            continue
        real_variant = next(v for v in peers if v['arm'] == 'real')
        control_variants = [v for v in peers if v['arm'] == 'permuted']
        assert len(control_variants) == 3
        paired, real_scores, control_scores = [], [], []
        for seed in plan['seeds']:
            real = by_task[(real_variant['id'], seed)]
            controls = [by_task[(v['id'], seed)] for v in control_variants]
            real_scores.append(real['score']); control_scores.extend(c['score'] for c in controls)
            for year in plan['folds']:
                rr = next(r for r in real['rows'] if r['season'] == year)
                cc = [next(r for r in c['rows'] if r['season'] == year) for c in controls]
                for control in cc:
                    for field in ['n', 'ntrain', 'cutoff', 'max_label_season']:
                        assert rr[field] == control[field]
                    for field in ['input_columns', 'source_columns', 'raw_feature_count', 'training_nonconstant_columns', 'train_slots', 'validation_slots']:
                        assert rr['audit'][field] == control['audit'][field], f'Unmatched {family}/{year}/{field}'
                mean_control = float(np.mean([c['stack'] for c in cc]))
                paired.append({'seed': seed, 'season': year, 'real': rr['stack'], 'mean_control': mean_control,
                               'gain': rr['stack'] - mean_control, 'source_columns': len(rr['audit']['source_columns'])})
        mean_real = float(np.mean(real_scores))
        statistics.append({'id': family, 'real_score': mean_real, 'matched_control_score': float(np.mean(control_scores)),
                           'paired_mean_gain': float(np.mean([p['gain'] for p in paired])),
                           'fold_gains': {str(y): float(np.mean([p['gain'] for p in paired if p['season'] == y])) for y in plan['folds']},
                           'seed_mean_gains': {str(seed): float(np.mean([p['gain'] for p in paired if p['seed'] == seed])) for seed in plan['seeds']},
                           'baseline_difference_context_only': None if baseline is None else mean_real - baseline,
                           'paired_rows': paired, 'automatic_promotion': False})
    return {'statistics': statistics, 'pending_families': pending, 'completed_tasks': len(by_task),
            'expected_tasks': 39, 'baseline_score_context_only': baseline, 'diagnostic_only': True,
            'interpretation': 'Pre-2019 family diagnostics on an uncertified inherited baseline. Real-minus-same-mask-shuffled gains are paired by model seed and fold. No test selection, significance claim, or automatic promotion; joint is not a factorial interaction test.'}
