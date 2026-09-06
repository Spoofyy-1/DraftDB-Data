"""Pre-2019 source provenance quarantine study; no held-out outcomes loaded.

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
_CACHE = {}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rho(predictions, truth):
    value = float(spearmanr(predictions, truth).statistic)
    return value if np.isfinite(value) else 0.0


def _prepared(variant):
    key = variant["id"]
    if key in _CACHE:
        return _CACHE[key]
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
    drop = cfg['drop'] + variant['additional_drop']
    if variant['input_source'] == 'context':
        columns = variant['context_features']
        assert all(c.startswith(('ctx_base_', 'ctx_skill_')) and c not in ['ctx_base_age', 'ctx_base_height'] for c in columns)
    else:
        columns = [c for c in manifest['legacy_features'] if not any(c.startswith(p) for p in drop)]
    assert not any(c.startswith(('f50_', 'slot_')) for c in columns)
    # Remove excluded source values too, so engineered descendants cannot revive them.
    for col in manifest['legacy_features']:
        if variant['input_source'] == 'context' or any(col.startswith(p) for p in drop):
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
        if variant['input_source'] == 'context':
            all_columns = list(columns)
            btr, bte = tr[all_columns].copy(), te[all_columns].copy()
        else:
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
        selected = [c for _, c in sorted(zip(selector.feature_importances_, all_columns), reverse=True)[:min(cfg['topk'], len(all_columns))]]
        assert len(selected) == min(cfg['topk'], len(all_columns)) and len(set(selected)) == len(selected)
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        fold_audit = {'study_hash': audit_signature, 'ordered_base_columns': selected,
                      'base_columns_hash': _hash(selected), 'training_pid_hash': _hash(tr.pid.tolist()),
                      'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                      'input_source': variant['input_source'], 'variant': variant['id'], 'training_matrix_hash': hashlib.sha256(pd.util.hash_pandas_object(btr[selected], index=True).to_numpy().tobytes()).hexdigest()}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te,
                      'btr': btr[selected].copy(), 'bte': bte[selected].copy(),
                      'yy': yy, 'truth': truth, 'used_max': int(used.season_end.max()), 'audit': fold_audit})
    _CACHE[key] = E, plan, g, folds
    return _CACHE[key]


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}}
    try:
        plan = json.loads((ROOT / 'plan.json').read_text())
        v = next(v for v in plan['variants'] if v['id'] == vid)
        if variant_override is not None and variant_override != v:
            raise AssertionError('Unregistered variant prohibited')
        assert vseed in plan['seeds']
        E, plan, g, folds = _prepared(v)
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            atr, ate = fold['btr'], fold['bte']
            assert list(atr) == list(ate)
            if v['input_source'] == 'context':
                assert set(atr) <= set(plan['source_control_features'])
            elif 'bio_' in v['additional_drop']:
                assert not any(c.startswith('bio_') for c in atr)
                # All raw bio inputs are NaN before engineering, so x_rim cannot revive NBA-listed height.
                if 'x_rim' in atr:
                    assert atr.x_rim.isna().all() and ate.x_rim.isna().all()
            predictions = E.H.predict('tabicl', atr, fold['yy'], ate, E.cfg_of('tabicl', g, list(atr)))
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr),
                   'cutoff': fold['cutoff'], 'max_label_season': fold['used_max'],
                   'stack': rho(predictions, fold['truth']), 'draft': rho(-fold['te'].actual_pick, fold['truth']),
                   'members': {'tabicl': rho(predictions, fold['truth'])},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'raw_feature_count': len(atr.columns),
                             'training_nonconstant_columns': int((atr.nunique(dropna=True) > 1).sum())},
                   'predictions': [{'pid': pid, 'score': float(score)} for pid, score in zip(fold['te'].pid, predictions)]}
            rows.append(row)
            print(json.dumps({'variant': vid, 'seed': vseed, 'fold': {k: value for k, value in row.items() if k not in ['audit', 'predictions']}}), flush=True)
        entry = {'config': v, 'score': float(np.mean([row['stack'] for row in rows])), 'rows': rows}
    except Exception as error:
        traceback.print_exc()
        entry['error'] = str(error)
    entry['seconds'] = round(time.time() - start, 1)
    return entry


def summarize_quarantine(candidates):
    plan = json.loads((ROOT / 'plan.json').read_text())
    groups = {}
    for row in candidates:
        if 'score' not in row:
            continue
        task = row.get('task_id', row['config']['id'])
        vid, seed = task.rsplit('_seed', 1) if '_seed' in task else (row['config']['id'], row['seed'])
        seed = int(seed)
        assert seed not in groups.setdefault(vid, {})
        groups[vid][seed] = row
    stats = []
    for v in plan['variants']:
        rows = groups.get(v['id'], {})
        if set(rows) != set(plan['seeds']):
            continue
        for year in plan['folds']:
            audits = [next(f['audit'] for f in row['rows'] if f['season'] == year) for row in rows.values()]
            for field in ['base_columns_hash', 'training_pid_hash', 'training_labels_hash', 'training_matrix_hash', 'study_hash']:
                assert len({a[field] for a in audits}) == 1, f'Inconsistent model seeds: {v["id"]}/{year}/{field}'
        stats.append({'id': v['id'], 'input_source': v['input_source'],
                      'score': float(np.mean([row['score'] for row in rows.values()])),
                      'fit_seed_std': float(np.std([row['score'] for row in rows.values()])),
                      'folds': {str(year): float(np.mean([next(f['stack'] for f in row['rows'] if f['season'] == year) for row in rows.values()])) for year in plan['folds']}})
    base = next((row for row in stats if row['id'] == plan['baseline']), None)
    if base is not None:
        for row in stats:
            row['diagnostic_difference_vs_uncertified_baseline'] = row['score'] - base['score']
    return {'statistics': stats, 'interpretation': 'Pre-2019 source quarantine diagnosis. A higher score cannot certify source provenance; inherited non-bio fields remain uncertain. No test scoring or automatic promotion.'}


summarize_matched = summarize_quarantine
