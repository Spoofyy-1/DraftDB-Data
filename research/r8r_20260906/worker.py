"""R8r F50 single-feature controls on the41-column raw college source backbone.

No model runs on import. Only baseline raw-source columns can reach the selector;
no legacy engineering, coverage, shrinkage or pretrained weight reuse is called.
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

def _matrix_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()).hexdigest()

def rho(predictions, truth):
    value = float(spearmanr(predictions, truth).statistic)
    return value if np.isfinite(value) else 0.0

def _eligible_columns(training, registered, rule):
    """No validation inputs or labels enter source coverage/uniqueness selection."""
    assert not rule['validation_coverage_used']
    audit = []
    for feature in registered:
        values = pd.to_numeric(training[feature], errors='raise')
        count, unique = int(values.notna().sum()), int(values.nunique())
        keep = count >= rule['min_training_observed'] and unique >= rule['min_training_unique']
        audit.append({'feature': feature, 'training_observed': count, 'training_unique': unique, 'eligible': keep})
    return [r['feature'] for r in audit if r['eligible']], audit

def _permuted(values, metadata, feature, seed, role):
    """Stable observed-value permutations within cohort, with exact original masks."""
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

def _slots(frame, features, variant, plan, role):
    slots, audit = {}, []
    for feature in features:
        values = pd.to_numeric(frame[feature], errors='raise').astype(float)
        assert not np.isinf(values.to_numpy()).any()
        value = values.copy() if variant['arm'] == 'real' else _permuted(values, frame, feature, variant['permutation_seed'], role)
        slot = plan['slot_mapping'][feature]
        slots[slot] = value
        cohorts = [values[frame.draft_year == year].dropna() for year in sorted(frame.draft_year.unique())]
        audit.append({'slot': slot, 'feature': feature,
                      'mask_hash': hashlib.sha256(value.isna().to_numpy().tobytes()).hexdigest(),
                      'observed': int(value.notna().sum()), 'unique_observed': int(value.nunique()),
                      'swappable_observed': sum(len(v) for v in cohorts if v.nunique() > 1),
                      'cohorts_with_variation': sum(v.nunique() > 1 for v in cohorts),
                      # Hex strings give a canonical multiset including both +0.0/-0.0;
                      # numeric sorting alone leaves equal signed zeros in input order.
                      'cohort_distribution_hash': _hash([[int(year), sorted(float(v).hex() for v in value[frame.draft_year == year].dropna())] for year in sorted(frame.draft_year.unique())])})
    return slots, audit

def _load_inputs():
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    expected = 3 + 12 * len(plan['active_families'])
    assert len(plan['variants']) * len(plan['seeds']) == plan['execution']['task_count'] == expected <= 603
    assert plan['seeds'] == [0, 101, 202] and plan['permutation_seeds'] == [9317, 18739, 28657]
    assert plan['baseline_variants'] == manifest['baseline_variants'] and set(plan['baseline_variants']) == {'source_college'}
    assert plan['candidate_features'] == manifest['source_features'] and len(set(plan['candidate_features'])) == 50
    assert set(plan['active_families']) | set(plan['excluded_families']) == set(plan['candidate_features'])
    assert not set(plan['active_families']) & set(plan['excluded_families'])
    assert all(plan['families'][c] == [c] for c in plan['candidate_features'])
    assert set(plan['slot_mapping'].values()) == {'slot_0'}
    for name, expected_hash in manifest['files'].items():
        assert Path(name).name == name
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected_hash
    for name in ['labels.csv', 'incumbent.json']:
        assert manifest['files'][name] == manifest['base_data_origin_hashes'][name]
    x = pd.read_csv(DATA / 'features.csv')
    source = pd.read_csv(DATA / 'source_features.csv')
    labels = pd.read_csv(DATA / 'labels.csv')
    provenance = json.loads((DATA / 'source_provenance.json').read_text())
    metadata = json.loads((DATA / 'source_metadata.json').read_text())
    dictionary = json.loads((DATA / 'source_dictionary.json').read_text())
    assert list(x) == plan['metadata_columns'] + plan['base_columns']
    assert list(source) == ['pid', 'draft_year'] + plan['candidate_features']
    assert source[['pid', 'draft_year']].equals(x[['pid', 'draft_year']])
    assert x.pid.is_unique and (x.draft_year <= 2018).all()
    assert len(plan['base_columns']) == 41 and plan['base_columns'] == manifest['base_columns']
    assert all(c.startswith(('ctx_base_', 'ctx_skill_')) and c not in ['ctx_base_age', 'ctx_base_height'] for c in plan['base_columns'])
    assert all(c.startswith('f50_') for c in plan['candidate_features'])
    assert set(dictionary) == set(plan['candidate_features'])
    assert labels.pid.isin(x.pid).all() and (labels.season_end <= 2018).all()
    assert not labels.duplicated(['pid', 'ordinal']).any() and labels.ordinal.between(1, 5).all()
    year_by_pid = x.set_index('pid').draft_year
    assert labels.pid.map(year_by_pid).equals(labels.draft_year)
    assert (labels.season_end >= labels.draft_year + labels.ordinal).all()
    assert np.isfinite(source[plan['candidate_features']].stack().dropna().to_numpy()).all()
    assert '45' not in metadata['source_fields']
    assert len({r['pid'] for r in provenance}) == len(provenance)
    for row in provenance:
        assert row['pid'] in year_by_pid and row['draft_year'] == year_by_pid[row['pid']]
        assert row['source_season'] <= row['draft_year'] <= 2018
        assert row['history_seasons'] and max(row['history_seasons']) == row['source_season']
        assert row['history_seasons'] == sorted(set(row['history_seasons']))
        assert row['source'] in metadata['source_hashes']
        assert row['source'] == f"torvik_{row['source_season']}.csv.gz"
    assert set(source.loc[source[plan['candidate_features']].notna().any(axis=1), 'pid']) <= {r['pid'] for r in provenance}
    joined = x.merge(source, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert len(joined) == len(x) and joined.pid.tolist() == x.pid.tolist()
    return plan, manifest, joined, labels


def _source_selection(training, plan, year):
    audit = []
    for feature in plan['candidate_features']:
        _, rows = _eligible_columns(training, [feature], plan['source_filter'])
        row = rows[0]
        row['swappable_training_observed'] = sum(int(g[feature].notna().sum()) for _, g in training.groupby('draft_year') if g[feature].nunique() > 1)
        audit.append(row)
    assert audit == plan['training_eligibility'][str(year)], 'Registered training eligibility changed'
    columns = {r['feature']: [r['feature']] if r['eligible'] else [] for r in audit}
    columns['baseline'] = []
    return columns, audit


def _prepared(backbone='source_college'):
    global _CACHE
    assert backbone == 'source_college'
    import legacy_kernel as E
    if _CACHE is not None:
        E.setup(_CACHE[1]['base_columns'])
        return _CACHE
    import xgboost as xgb
    plan, manifest, x, labels = _load_inputs()
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    assert cfg['icl_n'] == 32 and cfg['M'] == 400 and cfg['topk'] == 60
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
    columns = list(plan['base_columns'])
    E.setup(columns)
    study_hash = _hash({'plan': plan, 'data_files': manifest['files'],
                        'kernel': hashlib.sha256((ROOT / 'legacy_kernel.py').read_bytes()).hexdigest(),
                        'worker': hashlib.sha256((ROOT / 'worker.py').read_bytes()).hexdigest()})
    folds = []
    for year in plan['folds']:
        assert year in [2012, 2013, 2014]
        cutoff, k = year - 1, min(5, 2018 - year)
        tr = x[(x.draft_year >= int(g['win'])) & (x.draft_year <= cutoff - 1)].copy().reset_index(drop=True)
        te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
        assert len(tr) and len(te) and not set(tr.pid) & set(te.pid)
        assert (tr.draft_year <= year - 2).all() and (te.draft_year == year).all()
        used = labels[(labels.season_end <= cutoff) & labels.pid.isin(tr.pid)]
        assert len(used) and (used.season_end <= year - 1).all() and not set(used.pid) & set(te.pid)
        for ordinal in range(1, 6):
            tr[f'y_s{ordinal}_war'] = tr.pid.map(used[used.ordinal == ordinal].set_index('pid').war)
        # Intentionally no E.H.cols_for, fit_prior, build, feat_tx or add_feats.
        btr, bte = tr[columns].copy(), te[columns].copy()
        yy = E.label(tr, E.specs(g)[0], k)
        selector = xgb.XGBRegressor(max_depth=3, n_estimators=300, learning_rate=.05,
                                   subsample=.8, colsample_bytree=.6, n_jobs=2,
                                   device='cpu', tree_method='hist', random_state=11)
        selector.fit(btr, yy)
        selected = [c for _, c in sorted(zip(selector.feature_importances_, columns), reverse=True)[:min(cfg['topk'], len(columns))]]
        assert len(selected) == 41 and set(selected) == set(columns)
        source_columns, source_selection = _source_selection(tr, plan, year)
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        audit = {'study_hash': study_hash, 'backbone': backbone, 'baseline_source_variant': plan['baseline_variants'][backbone]['id'],
                 'ordered_base_columns': selected, 'base_columns_hash': _hash(selected),
                 'training_pid_hash': _hash(tr.pid.tolist()), 'validation_pid_hash': _hash(te.pid.tolist()),
                 'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                 'training_matrix_hash': _matrix_hash(btr[selected]), 'validation_matrix_hash': _matrix_hash(bte[selected]),
                 'source_selection': source_selection, 'source_selection_hash': _hash(source_selection),
                 'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                 'input_source': 'context', 'diagnostic_only': True}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te,
                      'btr': btr[selected].copy(), 'bte': bte[selected].copy(), 'yy': yy, 'truth': truth,
                      'source_columns': source_columns, 'audit': audit})
    _CACHE = E, plan, g, folds
    return _CACHE


def run_variant(vid, vseed=0, variant_override=None):
    start = time.time()
    entry = {'config': {'id': vid}, 'diagnostic_only': True}
    try:
        plan = json.loads((ROOT / 'plan.json').read_text())
        variant = next(v for v in plan['variants'] if v['id'] == vid)
        assert variant_override is None or variant_override == variant, 'Unregistered override prohibited'
        assert vseed in plan['seeds']
        E, plan, g, folds = _prepared(variant['backbone'])
        os.environ['SEED_SHIFT'] = str(vseed)
        rows = []
        for fold in folds:
            features = fold['source_columns'][variant['family']]
            assert len(features) <= 1
            assert set(fold['btr']) == set(plan['base_columns'])
            atr, ate = fold['btr'].copy(), fold['bte'].copy()
            tr_slots, tr_audit = _slots(fold['tr'], features, variant, plan, 'train')
            te_slots, te_audit = _slots(fold['te'], features, variant, plan, 'validation')
            changes = {}
            for role, original, slots in [('train', fold['tr'], tr_slots), ('validation', fold['te'], te_slots)]:
                changes[role] = {feature: int((original[feature].notna() & (slots[plan['slot_mapping'][feature]] != original[feature])).sum()) for feature in features}
            for slot in tr_slots:
                atr[slot], ate[slot] = tr_slots[slot], te_slots[slot]
            assert list(atr) == list(ate) == fold['audit']['ordered_base_columns'] + [plan['slot_mapping'][c] for c in features]
            assert _matrix_hash(atr[fold['audit']['ordered_base_columns']]) == fold['audit']['training_matrix_hash']
            assert _matrix_hash(ate[fold['audit']['ordered_base_columns']]) == fold['audit']['validation_matrix_hash']
            E.H.audit_features(list(atr))
            pred = E.H.predict('tabicl', atr, fold['yy'], ate, E.cfg_of('tabicl', g, list(atr)))
            assert len(pred) == len(ate) and np.isfinite(np.asarray(pred)).all()
            score = rho(pred, fold['truth'])
            row = {'season': fold['year'], 'k': fold['k'], 'n': len(ate), 'ntrain': len(atr),
                   'cutoff': fold['cutoff'], 'max_label_season': fold['audit']['max_label_season'],
                   'stack': score, 'draft': rho(-fold['te'].actual_pick, fold['truth']), 'members': {'tabicl': score},
                   'audit': {**fold['audit'], 'input_columns': list(atr), 'source_columns': features,
                             'raw_feature_count': len(atr.columns), 'training_nonconstant_columns': int((atr.nunique() > 1).sum()),
                             'train_slots': tr_audit, 'validation_slots': te_audit,
                             'slot_matrix_hashes': {'train': _matrix_hash(atr[list(tr_slots)]), 'validation': _matrix_hash(ate[list(te_slots)])},
                             'changed_source_values': changes},
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
    """Paired exploratory family summaries; never select a test candidate here."""
    plan = json.loads((ROOT / 'plan.json').read_text())
    registered = {v['id']: v for v in plan['variants']}
    by_task = {}
    for entry in candidates:
        if 'score' not in entry:
            continue
        task_id = entry.get('task_id', entry['config']['id'])
        vid, seed = task_id.rsplit('_seed', 1) if '_seed' in task_id else (entry['config']['id'], entry['seed'])
        seed = int(seed)
        assert vid in registered
        config = dict(entry['config'])
        assert config['id'] in [vid, task_id]
        config['id'] = vid  # Some existing runners append _seed to this field.
        assert config == registered[vid]
        assert 'seed' not in entry or int(entry['seed']) == seed
        assert seed in plan['seeds'] and (vid, seed) not in by_task and entry['diagnostic_only']
        assert {r['season'] for r in entry['rows']} == set(plan['folds']) and len(entry['rows']) == len(plan['folds'])
        assert np.isclose(entry['score'], np.mean([r['stack'] for r in entry['rows']]))
        by_task[(vid, seed)] = entry
    for year in plan['folds']:
        all_audits = [next(r['audit'] for r in entry['rows'] if r['season'] == year) for entry in by_task.values()]
        for field in ['study_hash', 'training_pid_hash', 'validation_pid_hash', 'training_labels_hash', 'source_selection_hash']:
            assert len({_hash(a[field]) for a in all_audits}) <= 1, f'Cross-backbone mismatch {year}/{field}'
        for backbone in plan['baseline_variants']:
            audits = [a for a in all_audits if a['backbone'] == backbone]
            for field in ['base_columns_hash', 'ordered_base_columns', 'training_matrix_hash', 'validation_matrix_hash', 'baseline_source_variant', 'source_selection']:
                assert len({_hash(a[field]) for a in audits}) <= 1, f'Base changed {backbone}/{year}/{field}'
            assert all(a['max_label_season'] <= year - 1 and a['training_max_draft_year'] <= year - 2 for a in audits)
    # Every particular shuffle is frozen across model seeds. Its value hashes
    # differ from the real arm, while the matched invariants below do not.
    for vid in registered:
        for year in plan['folds']:
            audits = [next(r['audit'] for r in by_task[(vid, seed)]['rows'] if r['season'] == year) for seed in plan['seeds'] if (vid, seed) in by_task]
            for field in ['slot_matrix_hashes', 'changed_source_values']:
                assert len({_hash(a[field]) for a in audits}) <= 1, f'Unfixed shuffle {vid}/{year}/{field}'
    baselines, statistics, pending = {}, [], []
    for backbone in plan['baseline_variants']:
        keys = [(plan['baselines'][backbone], seed) for seed in plan['seeds']]
        baseline = float(np.mean([by_task[k]['score'] for k in keys])) if all(k in by_task for k in keys) else None
        baselines[backbone] = baseline
        for family in plan['active_families']:
            peers = [v for v in plan['variants'] if v['backbone'] == backbone and v['family'] == family]
            required = [(v['id'], seed) for v in peers for seed in plan['seeds']]
            comparison_id = f'{backbone}__{family}'
            if not all(key in by_task for key in required):
                pending.append(comparison_id)
                continue
            real_variant = next(v for v in peers if v['arm'] == 'real')
            control_variants = [v for v in peers if v['arm'] == 'permuted']
            assert len(control_variants) == 3
            paired, real_scores, control_scores, individual = [], [], [], []
            for seed in plan['seeds']:
                real = by_task[(real_variant['id'], seed)]
                controls = [by_task[(v['id'], seed)] for v in control_variants]
                real_scores.append(real['score']); control_scores.extend(c['score'] for c in controls)
                for year in plan['folds']:
                    rr = next(r for r in real['rows'] if r['season'] == year)
                    cc = [next(r for r in c['rows'] if r['season'] == year) for c in controls]
                    for control, cv in zip(cc, control_variants):
                        for field in ['n', 'ntrain', 'cutoff', 'max_label_season']:
                            assert rr[field] == control[field]
                        for field in ['input_columns', 'source_columns', 'raw_feature_count', 'training_nonconstant_columns', 'train_slots', 'validation_slots']:
                            assert rr['audit'][field] == control['audit'][field], f'Unmatched {comparison_id}/{year}/{field}'
                        individual.append({'seed': seed, 'season': year, 'permutation_seed': cv['permutation_seed'],
                                           'gain': rr['stack'] - control['stack']})
                    mean_control = float(np.mean([c['stack'] for c in cc]))
                    paired.append({'seed': seed, 'season': year, 'real': rr['stack'], 'mean_control': mean_control,
                                   'gain': rr['stack'] - mean_control, 'source_columns': len(rr['audit']['source_columns']),
                                   'train_immovable_columns': [a['feature'] for a in rr['audit']['train_slots'] if a['swappable_observed'] == 0],
                                   'validation_immovable_columns': [a['feature'] for a in rr['audit']['validation_slots'] if a['swappable_observed'] == 0]})
            mean_real = float(np.mean(real_scores))
            statistics.append({'id': comparison_id, 'backbone': backbone, 'family': family, 'real_score': mean_real,
                               'matched_control_score': float(np.mean(control_scores)),
                               'paired_mean_gain': float(np.mean([p['gain'] for p in paired])),
                               'fold_gains': {str(y): float(np.mean([p['gain'] for p in paired if p['season'] == y])) for y in plan['folds']},
                               'seed_mean_gains': {str(seed): float(np.mean([p['gain'] for p in paired if p['seed'] == seed])) for seed in plan['seeds']},
                               'permutation_mean_gains': {str(seed): float(np.mean([p['gain'] for p in individual if p['permutation_seed'] == seed])) for seed in plan['permutation_seeds']},
                               'baseline_difference_context_only': None if baseline is None else mean_real - baseline,
                               'paired_rows': paired, 'individual_control_rows': individual, 'automatic_promotion': False})
    return {'statistics': statistics, 'pending_families': pending, 'completed_tasks': len(by_task),
            'expected_tasks': plan['execution']['task_count'], 'untestable_families': plan['excluded_families'], 'baseline_scores_context_only': baselines, 'diagnostic_only': True,
            'all_results_complete': len(by_task) == plan['execution']['task_count'],
            'combinations_registered': False,
            'interpretation': 'Pre-2019 source-only single-feature diagnostics; all50 hypotheses registered without choosing prior winners. No confirmation/test selection or automatic promotion. Same slot_0, masks and cohort marginals for real/control arms. Model seeds are not independent datasets;50 exploratory comparisons carry multiplicity. Baseline differences are context only. Review every completed result before separately preregistering any combinations. Retrospective source identity/vintage limits remain.'}
