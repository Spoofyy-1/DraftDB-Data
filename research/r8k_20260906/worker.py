"""Pre-2019 matched two-slot pair study; no external paths or labels loaded.

Base transformations/selection are cached once per fold in each process and are
identical across every real/control arm. Every candidate uses the same slot name.
"""
import os
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
from pathlib import Path
import hashlib
import json
import time
import traceback
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'results'
_CACHE = None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rho(predictions, truth):
    value = float(spearmanr(predictions, truth).statistic)
    return value if np.isfinite(value) else 0.0


def _permuted(values, metadata, feature, seed, role):
    """Retain exact missingness; never exchange values between draft cohorts."""
    out = pd.to_numeric(values, errors='raise').astype(float).copy()
    if not values.index.equals(metadata.index) or metadata.pid.duplicated().any():
        raise AssertionError('Invalid control row alignment')
    for year in sorted(metadata.draft_year.unique()):
        indices = metadata.loc[(metadata.draft_year == year) & values.notna()].sort_values('pid', kind='stable').index
        stable_seed = int.from_bytes(hashlib.sha256(json.dumps([feature, int(seed), role, int(year)]).encode()).digest()[:8], 'little')
        out.loc[indices] = np.random.default_rng(stable_seed).permutation(values.loc[indices].to_numpy())
    assert out.isna().equals(values.isna())
    for year in metadata.draft_year.unique():
        mask = metadata.draft_year == year
        assert np.array_equal(np.sort(out[mask].dropna()), np.sort(values[mask].dropna()))
    return out


def _prepared():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    import legacy_kernel as E
    import xgboost as xgb
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    for filename, expected in manifest['files'].items():
        if Path(filename).name != filename:
            raise AssertionError('Manifest may name only local data files')
        assert hashlib.sha256((DATA / filename).read_bytes()).hexdigest() == expected
    x = pd.read_csv(DATA / 'features.csv')
    labels = pd.read_csv(DATA / 'labels.csv')
    assert x.pid.is_unique and (x.draft_year < 2019).all()
    assert (labels.season_end <= 2018).all()
    assert not labels.duplicated(['pid', 'ordinal']).any()
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
    columns = [c for c in manifest['legacy_features'] if not any(c.startswith(p) for p in cfg['drop'])]
    assert not any(c.startswith(('f50_', 'slot_')) for c in columns)
    # Remove excluded source values too, so engineered descendants cannot revive them.
    for col in manifest['legacy_features']:
        if any(col.startswith(p) for p in cfg['drop']):
            x[col] = np.nan
    E.setup(columns)
    audit_signature = _hash({'plan': plan, 'data_files': manifest['files'], 'kernel': hashlib.sha256((ROOT / 'legacy_kernel.py').read_bytes()).hexdigest()})
    folds = []
    for year in plan['folds']:
        assert year <= 2018
        cutoff = year - 1
        k = min(5, 2018 - year)
        tr = x[(x.draft_year >= int(g['win'])) & (x.draft_year <= cutoff - 1)].copy().reset_index(drop=True)
        te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
        assert len(tr) and len(te) and not set(tr.pid) & set(te.pid)
        used = labels[(labels.season_end <= cutoff) & labels.pid.isin(tr.pid)]
        assert len(used) and (used.season_end <= cutoff).all()
        for ordinal in range(1, 6):
            tr[f'y_s{ordinal}_war'] = tr.pid.map(used[used.ordinal == ordinal].set_index('pid').war)
        opts = E.opts_of(g)
        base = E.H.cols_for(opts)
        all_columns = E.cols_of(g, base)
        assert not any(c.startswith(('f50_', 'slot_')) for c in all_columns)
        E.H.audit_features(all_columns)
        prior, coverage_quantiles = E.H.fit_prior(tr)
        btr = E.H.build(tr, prior, coverage_quantiles, opts)
        bte = E.H.build(te, prior, coverage_quantiles, opts)
        rates = [c for c in base if c.startswith(('col_', 'intl_')) and not c.startswith('col_gl_')]
        btr, bte = E.feat_tx(btr, bte, g['fx'], tr, te, rates)
        stats = E.stats_of(btr)
        btr = E.add_feats(btr, g['fx'], stats)
        bte = E.add_feats(bte, g['fx'], stats)
        yy = E.label(tr, E.specs(g)[0], k)
        selector = xgb.XGBRegressor(max_depth=3, n_estimators=300, learning_rate=.05,
                                   subsample=.8, colsample_bytree=.6, n_jobs=2,
                                   device='cpu', tree_method='hist', random_state=11)
        selector.fit(btr[all_columns], yy)
        selected = [c for _, c in sorted(zip(selector.feature_importances_, all_columns), reverse=True)[:cfg['topk']]]
        assert len(selected) == cfg['topk'] and len(set(selected)) == len(selected)
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        fold_audit = {'study_hash': audit_signature, 'ordered_base_columns': selected,
                      'base_columns_hash': _hash(selected), 'training_pid_hash': _hash(tr.pid.tolist()),
                      'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                      'training_matrix_hash': hashlib.sha256(pd.util.hash_pandas_object(btr[selected], index=True).to_numpy().tobytes()).hexdigest()}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te,
                      'btr': btr[selected].copy(), 'bte': bte[selected].copy(),
                      'yy': yy, 'truth': truth, 'used_max': int(used.season_end.max()), 'audit': fold_audit})
    _CACHE = E, plan, g, folds
    return _CACHE


def _slot_values(frame, features, arms, permutation_seed, role):
    slots = {}
    audit = []
    for i, (feature, arm) in enumerate(zip(features, arms)):
        values = pd.to_numeric(frame[feature], errors='raise').astype(float)
        assert not np.isinf(values.to_numpy()).any()
        if arm == 'real':
            value = values.copy()
        elif arm == 'permuted':
            value = _permuted(values, frame, feature, permutation_seed, role)
        else:
            raise ValueError('Only real and matched-permuted arms are valid in this study')
        name = f'slot_{i}'
        slots[name] = value
        audit.append({'slot': name, 'feature': feature, 'arm': arm,
                      'mask_hash': hashlib.sha256(value.isna().to_numpy().tobytes()).hexdigest(),
                      'observed': int(value.notna().sum()), 'unique_observed': int(value.nunique())})
    return slots, audit


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}}
    try:
        E, plan, g, folds = _prepared()
        # Future pairs require a separate registered batch, not an ad-hoc override.
        v = next(v for v in plan['variants'] if v['id'] == vid)
        if variant_override is not None and variant_override != v:
            raise AssertionError('Unregistered override prohibited')
        assert vseed in plan['seeds']
        features, arms = v['features'], v['arms']
        assert len(features) == len(arms) == 2
        assert plan["pair_phase"]["enabled"] and v["pair_id"] in plan["selected_pair_ids"]
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            atr, ate = fold['btr'].copy(), fold['bte'].copy()
            tr_slots, tr_audit = _slot_values(fold['tr'], features, arms, v['permutation_seed'], 'train')
            te_slots, te_audit = _slot_values(fold['te'], features, arms, v['permutation_seed'], 'validation')
            for name in tr_slots:
                atr[name], ate[name] = tr_slots[name], te_slots[name]
            assert list(atr) == list(ate)
            assert list(atr) == fold['audit']['ordered_base_columns'] + [f'slot_{i}' for i in range(len(features))]
            E.H.audit_features(list(atr))
            pred = E.H.predict('tabicl', atr, fold['yy'], ate, E.cfg_of('tabicl', g, list(atr)))
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr),
                   'cutoff': fold['cutoff'], 'max_label_season': fold['used_max'],
                   'stack': rho(pred, fold['truth']), 'draft': rho(-fold['te'].actual_pick, fold['truth']),
                   'members': {'tabicl': rho(pred, fold['truth'])},
                   'audit': {**fold['audit'], 'input_columns': list(atr),
                             'raw_feature_count': len(atr.columns),
                             'training_nonconstant_columns': int((atr.nunique(dropna=True) > 1).sum()),
                             'train_slots': tr_audit, 'validation_slots': te_audit},
                   'predictions': [{'pid': pid, 'score': float(score)} for pid, score in zip(fold['te'].pid, pred)]}
            rows.append(row)
            print(json.dumps({'variant': vid, 'seed': vseed, 'fold': {k: val for k, val in row.items() if k not in ['predictions', 'audit']}}), flush=True)
        entry = {'config': v, 'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows}
    except Exception as error:
        traceback.print_exc()
        entry['error'] = str(error)
    entry['seconds'] = round(time.time() - start, 1)
    return entry


def summarize_pairs(candidates):
    """Audit matched two-slot arms and report factorial paired contrasts."""
    plan = json.loads((ROOT / 'plan.json').read_text())
    by_task = {}
    for row in candidates:
        if 'score' not in row:
            continue
        task_id = row.get('task_id', row['config']['id'])
        if '_seed' in task_id:
            vid, seed = task_id.rsplit('_seed', 1)
            seed = int(seed)
        else:
            vid, seed = row['config']['id'], int(row['seed'])
        if (vid, seed) in by_task:
            raise AssertionError('Duplicate completed task')
        by_task[(vid, seed)] = row
    for year in plan['folds']:
        audits = [next(f['audit'] for f in row['rows'] if f['season'] == year) for row in by_task.values()]
        for field in ['base_columns_hash', 'training_pid_hash', 'training_labels_hash', 'training_matrix_hash', 'study_hash']:
            assert len({a[field] for a in audits}) <= 1, f'Unmatched fold {year}: {field}'
    results = []
    for pair in plan['pairs']:
        variants = [v for v in plan['variants'] if v['pair_id'] == pair['id']]
        assert len(variants) == 10
        required = [(v['id'], seed) for v in variants for seed in plan['seeds']]
        if not all(task in by_task for task in required):
            continue
        rr_variant = next(v for v in variants if v['arms'] == ['real', 'real'])
        fold_records = []
        for year in plan['folds']:
            per_seed = []
            for model_seed in plan['seeds']:
                rr_task = by_task[(rr_variant['id'], model_seed)]
                rr = next(f for f in rr_task['rows'] if f['season'] == year)
                controls = {'RP': [], 'PR': [], 'PP': []}
                replicate_contrasts = []
                for permutation in plan['permutation_seeds']:
                    scores = {'RR': rr['stack']}
                    for label, arms in [('RP', ['real', 'permuted']), ('PR', ['permuted', 'real']), ('PP', ['permuted', 'permuted'])]:
                        variant = next(v for v in variants if v['arms'] == arms and v['permutation_seed'] == permutation)
                        task = by_task[(variant['id'], model_seed)]
                        row = next(f for f in task['rows'] if f['season'] == year)
                        for field in ['input_columns', 'raw_feature_count', 'training_nonconstant_columns']:
                            assert rr['audit'][field] == row['audit'][field], f'Unmatched pair dimensions: {pair["id"]}'
                        assert rr['audit']['input_columns'][-2:] == ['slot_0', 'slot_1']
                        for role in ['train_slots', 'validation_slots']:
                            assert len(rr['audit'][role]) == len(row['audit'][role]) == 2
                            for a, b in zip(rr['audit'][role], row['audit'][role]):
                                for field in ['slot', 'feature', 'mask_hash', 'observed', 'unique_observed']:
                                    assert a[field] == b[field], f'Unmatched pair masks/marginals: {pair["id"]}/{role}/{field}'
                        scores[label] = row['stack']
                        controls[label].append(row['stack'])
                    replicate_contrasts.append({'permutation_seed': permutation,
                                                'joint_minus_A_only': scores['RR'] - scores['RP'],
                                                'joint_minus_B_only': scores['RR'] - scores['PR'],
                                                'interaction': scores['RR'] - scores['RP'] - scores['PR'] + scores['PP']})
                scores = {'RR': rr['stack'], **{label: float(np.mean(values)) for label, values in controls.items()}}
                per_seed.append({'model_seed': model_seed, **scores,
                                 'joint_minus_A_only': scores['RR'] - scores['RP'],
                                 'joint_minus_B_only': scores['RR'] - scores['PR'],
                                 'interaction': scores['RR'] - scores['RP'] - scores['PR'] + scores['PP'],
                                 'replicates': replicate_contrasts})
            fields = ['RR', 'RP', 'PR', 'PP', 'joint_minus_A_only', 'joint_minus_B_only', 'interaction']
            fold_records.append({'season': year, **{field: float(np.mean([row[field] for row in per_seed])) for field in fields}, 'paired_seeds': per_seed})
        averages = {field: float(np.mean([row[field] for row in fold_records])) for field in fields}
        gate = plan['pair_gate']
        passes = all(averages[field] >= gate['min_joint_minus_each_single']
                     and sum(row[field] > 0 for row in fold_records) >= gate['min_improved_folds_each']
                     and min(row[field] for row in fold_records) >= -gate['max_fold_regression_each']
                     for field in ['joint_minus_A_only', 'joint_minus_B_only'])
        if gate.get('require_positive_interaction'):
            passes = passes and averages['interaction'] > 0
        results.append({'id': pair['id'], 'features': pair['features'], **averages, 'folds': fold_records, 'passes': passes})
    results.sort(key=lambda row: (-min(row['joint_minus_A_only'], row['joint_minus_B_only']), row['id']))
    return {'pairs': results, 'provisional_pairs': [row['id'] for row in results if row['passes']],
            'interpretation': 'Pre-2019 paired representation effects. RR reused across permutations is not an independent replication. Interaction is reported separately from incremental value. No test selection.'}


summarize_matched = summarize_pairs
