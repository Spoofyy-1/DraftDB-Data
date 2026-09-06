"""Pre-2019 cohort maturity study; no test data or future-season labels loaded.

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
    key = (variant["window"], str(variant["maturity"]))
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
    assert hashlib.sha256((DATA / 'features.csv').read_bytes()).hexdigest() == plan['eligibility_registration']['source_features_sha256']
    # Recheck the entire registry using only cohort dates before any fitting/scoring.
    for registration in plan['eligibility']:
        counts = []
        for record in registration['fold_counts']:
            cutoff, k = record['cutoff'], record['k']
            threshold = k if registration['maturity'] == 'k' else registration['maturity']
            max_cohort = min(cutoff - 1, cutoff - threshold)
            count = int(((x.draft_year >= registration['window']) & (x.draft_year <= max_cohort)).sum())
            assert count == record['ntrain'] and max_cohort == record['max_training_cohort']
            counts.append(count)
        assert registration['eligible'] == all(n >= 80 for n in counts)
    eligibility = next(v for v in plan['eligibility'] if v['id'] == variant['id'])
    assert eligibility['eligible']
    labels = pd.read_csv(DATA / 'labels.csv')
    assert x.pid.is_unique and (x.draft_year < 2019).all()
    assert (labels.season_end <= 2018).all()
    assert not labels.duplicated(['pid', 'ordinal']).any()
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    g = {**incumbent, 'noscout': 1, 'win': variant['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
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
        threshold = k if variant['maturity'] == 'k' else variant['maturity']
        max_cohort = min(cutoff - 1, cutoff - threshold)
        tr = x[(x.draft_year >= int(g['win'])) & (x.draft_year <= max_cohort)].copy().reset_index(drop=True)
        registered_fold = next(row for row in eligibility['fold_counts'] if row['season'] == year)
        assert len(tr) == registered_fold['ntrain'] and len(tr) >= 80
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
                      'yy': yy, 'truth': truth, 'used_max': int(used.season_end.max()), 'audit': fold_audit,
                      'max_training_cohort': max_cohort, 'maturity_threshold': threshold,
                      'observed_target_count_distribution': {str(int(n)): int(count) for n, count in tr[[f'y_s{ordinal}_war' for ordinal in range(1, k+1)]].notna().sum(axis=1).value_counts().sort_index().items()}})
    _CACHE[key] = E, plan, g, folds
    return _CACHE[key]


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}}
    try:
        plan = json.loads((ROOT / 'plan.json').read_text())
        variant = next(v for v in plan['variants'] if v['id'] == vid)
        if variant_override is not None and variant_override != variant:
            raise AssertionError('Unregistered variant prohibited')
        assert vseed in plan['seeds']
        E, plan, g, folds = _prepared(variant)
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            atr, ate = fold['btr'], fold['bte']
            assert len(atr.columns) == len(ate.columns) == 60
            assert not any(c.startswith(('f50_', 'slot_')) for c in atr)
            prediction = E.H.predict('tabicl', atr, fold['yy'], ate, E.cfg_of('tabicl', g, list(atr)))
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr),
                   'cutoff': fold['cutoff'], 'max_label_season': fold['used_max'],
                   'max_training_cohort': fold['max_training_cohort'],
                   'maturity_threshold': fold['maturity_threshold'],
                   'observed_target_count_distribution': fold['observed_target_count_distribution'],
                   'stack': rho(prediction, fold['truth']), 'draft': rho(-fold['te'].actual_pick, fold['truth']),
                   'members': {'tabicl': rho(prediction, fold['truth'])},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'raw_feature_count': 60,
                             'training_nonconstant_columns': int((atr.nunique(dropna=True) > 1).sum())},
                   'predictions': [{'pid': pid, 'score': float(score)} for pid, score in zip(fold['te'].pid, prediction)]}
            rows.append(row)
            print(json.dumps({'variant': vid, 'seed': vseed, 'fold': {k: value for k, value in row.items() if k not in ['audit', 'predictions']}}), flush=True)
        entry = {'config': variant, 'score': float(np.mean([row['stack'] for row in rows])), 'rows': rows}
    except Exception as error:
        traceback.print_exc()
        entry['error'] = str(error)
    entry['seconds'] = round(time.time() - start, 1)
    return entry


def summarize_maturity(candidates):
    plan = json.loads((ROOT / 'plan.json').read_text())
    groups = {}
    for row in candidates:
        if 'score' not in row:
            continue
        task_id = row.get('task_id', row['config']['id'])
        if '_seed' in task_id:
            vid, seed = task_id.rsplit('_seed', 1)
            seed = int(seed)
        else:
            vid, seed = row['config']['id'], int(row['seed'])
        groups.setdefault(vid, {})
        assert seed not in groups[vid], 'Duplicate model seed'
        groups[vid][seed] = row
    statistics = []
    for variant in plan['variants']:
        rows = groups.get(variant['id'], {})
        if set(rows) != set(plan['seeds']):
            continue
        for year in plan['folds']:
            audits = [next(f['audit'] for f in r['rows'] if f['season'] == year) for r in rows.values()]
            for field in ['base_columns_hash', 'training_pid_hash', 'training_labels_hash', 'training_matrix_hash', 'study_hash']:
                assert len({a[field] for a in audits}) == 1, f'Model seeds do not share one configuration: {variant["id"]}/{year}/{field}'
        folds = {str(year): float(np.mean([next(f['stack'] for f in row['rows'] if f['season'] == year) for row in rows.values()])) for year in plan['folds']}
        statistics.append({'id': variant['id'], 'window': variant['window'], 'maturity': variant['maturity'],
                           'score': float(np.mean([row['score'] for row in rows.values()])),
                           'fit_seed_std': float(np.std([row['score'] for row in rows.values()])), 'folds': folds})
    baseline = next((row for row in statistics if row['id'] == plan['baseline']), None)
    if baseline is not None:
        for row in statistics:
            row['gain_vs_exact_baseline'] = row['score'] - baseline['score']
            row['fold_gains_vs_exact_baseline'] = {year: score - baseline['folds'][year] for year, score in row['folds'].items()}
    statistics.sort(key=lambda row: (-row['score'], row['id']))
    return {'statistics': statistics, 'eligibility': plan['eligibility'],
            'interpretation': 'Calendar-cohort censoring diagnosis using only pre-2019 development. Cohort age is not a filter on NBA survival or seasons played. Fit-seed variability is not generalization uncertainty.'}


summarize_matched = summarize_maturity
