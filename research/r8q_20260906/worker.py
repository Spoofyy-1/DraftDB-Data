"""R8q: pre-2019 verified-combine matched controls on two fixed R8n backbones.

No GPU/model work happens on import. The source-only path bypasses all legacy
engineering, coverage and shrinkage. No held-out outcome file is accessible here.
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
FORBIDDEN_BASE = ('bio_', 'med_', 'cons_', 'col_lu_', 'col_z_', 'col_bpm_', 'col_first_bpm', 'scout_', 'vcmb_', 'slot_', 'f50_', 'report_')
BIO_DESCENDANTS = ['x_rim', 'x_age_x_shoot', 'x_old_shooter', 'x_young_prod', 'x_old_prod', 'x_young_cons', 'x_cls_age', 'x_cls_height', 'x_cons_vs_prod', 'x_cons_missing']


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _matrix_hash(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()).hexdigest()


def rho(predictions, truth):
    value = float(spearmanr(predictions, truth).statistic)
    return value if np.isfinite(value) else 0.0


def _load_inputs():
    plan = json.loads((ROOT / 'plan.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert plan['diagnostic_only'] and plan['no_confirmation_or_test_scoring']
    assert len(plan['variants']) * len(plan['seeds']) == plan['execution']['task_count'] == 78
    assert plan['baseline_variants'] == manifest['baseline_variants']
    assert set(plan['baseline_variants']) == {'source_college', 'quarantined_legacy'}
    assert plan['active_families'] == ['anthropometry', 'athletics', 'all']
    assert plan['excluded_families']['shooting']['status'] == 'untestable_no_training_eligible_columns'
    for name, expected in manifest['files'].items():
        assert Path(name).name == name
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected
    for name, expected in manifest['base_data_hashes'].items():
        assert manifest['files'][name] == expected
    x = pd.read_csv(DATA / 'features.csv')
    labels = pd.read_csv(DATA / 'labels.csv')
    source = pd.read_csv(DATA / 'source_features.csv')
    provenance = pd.read_csv(DATA / 'source_provenance.csv')
    dictionary = json.loads((DATA / 'source_dictionary.json').read_text())
    metadata = json.loads((DATA / 'source_metadata.json').read_text())
    registered = plan['families']['all']
    assert registered == manifest['source_features'] and len(set(registered)) == 37
    assert plan['families'] == manifest['source_families']
    assert registered == sum([plan['families'][f] for f in ['anthropometry', 'athletics', 'shooting']], [])
    assert all(c.startswith('vcmb_') for c in registered)
    assert len(set(plan['slot_mapping'].values())) == len(registered)
    assert x.pid.is_unique and (x.draft_year < 2019).all()
    assert labels.pid.isin(x.pid).all() and (labels.season_end <= 2018).all()
    assert not labels.duplicated(['pid', 'ordinal']).any() and labels.ordinal.between(1, 5).all()
    year_by_pid = x.set_index('pid').draft_year
    assert labels.pid.map(year_by_pid).equals(labels.draft_year)
    assert (labels.season_end >= labels.draft_year + labels.ordinal).all()
    assert source[['pid', 'draft_year']].equals(x[['pid', 'draft_year']])
    assert list(source) == ['pid', 'draft_year'] + registered and not set(registered) & set(x)
    observed = source[registered].stack().dropna()
    assert np.isfinite(observed.to_numpy()).all()
    assert provenance.pid.is_unique and provenance.pid.isin(x.pid).all()
    assert (provenance.draft_year <= 2018).all() and (provenance.source_year == provenance.draft_year).all()
    assert provenance.pid.map(year_by_pid).equals(provenance.draft_year)
    assert set(source.loc[source[registered].notna().any(axis=1), 'pid']) <= set(provenance.pid)
    source_files = {r['filename']: r for r in metadata['source_files']}
    for row in provenance.itertuples():
        record = source_files[row.source_filename]
        year = int(row.draft_year)
        assert record['source_year'] == year <= 2018 and record['all_row_seasons_verified']
        assert record['parameters']['SeasonYear'] == f'{year}-{str(year+1)[2:]}'
        assert 0 <= row.source_row < record['rows']
        assert row.match_method in ['unique_nba_id', 'unique_exact_same_cohort_name']
    for family in ['anthropometry', 'athletics', 'shooting']:
        assert all(dictionary[c]['experiment_family'] == family for c in plan['families'][family])
    joined = x.merge(source, on=['pid', 'draft_year'], how='left', validate='one_to_one', sort=False)
    assert joined.pid.tolist() == x.pid.tolist() and len(joined) == len(x)
    return plan, manifest, joined, labels


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
                      'cohort_distribution_hash': _hash([[int(year), sorted(value[frame.draft_year == year].dropna().tolist())] for year in sorted(frame.draft_year.unique())])})
    return slots, audit


def _check_base_matrices(btr, bte, selected, variant):
    assert list(btr[selected]) == list(bte[selected]) == selected
    assert not any(c.startswith(FORBIDDEN_BASE) for c in selected)
    if variant['input_source'] == 'context':
        assert len(selected) == 41 and set(selected) == set(variant['context_features'])
        assert all(c.startswith(('ctx_base_', 'ctx_skill_')) for c in selected)
        assert not any(c in ['ctx_base_age', 'ctx_base_height'] for c in selected)
    else:
        assert len(selected) == 60
        # Preserve R8n's exact feature/selection shape. These continuous
        # descendants must be wholly missing after source quarantine.
        for column in set(BIO_DESCENDANTS) & set(selected):
            assert btr[column].isna().all() and bte[column].isna().all(), f'Unsafe descendant {column}'


def _prepared(backbone):
    import legacy_kernel as E
    if backbone in _CACHE:
        cached = _CACHE[backbone]
        E.setup(cached[4])  # Restore global legacy namespace if another backbone ran.
        return cached[:4]
    import xgboost as xgb
    plan, manifest, x, labels = _load_inputs()
    variant = plan['baseline_variants'][backbone]
    incumbent = json.loads((DATA / 'incumbent.json').read_text())['champ']
    assert not any(incumbent.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert incumbent['labelmix'] == 'single' and incumbent['meta'] == 'rankavg'
    cfg = plan['backbone']
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'], 'M': cfg['M'], 'icl_n': cfg['icl_n']}
    assert cfg['icl_n'] == 32 and cfg['topk'] == 60 and cfg['M'] == 400
    drop = cfg['drop'] + variant['additional_drop']
    columns = list(variant['context_features']) if variant['input_source'] == 'context' else [c for c in manifest['legacy_features'] if not any(c.startswith(p) for p in drop)]
    assert not any(c.startswith(FORBIDDEN_BASE) for c in columns)
    for col in manifest['legacy_features']:
        if variant['input_source'] == 'context' or any(col.startswith(p) for p in drop):
            x[col] = np.nan
    E.setup(columns)
    study_hash = _hash({'plan': plan, 'data_files': manifest['files'], 'kernel': hashlib.sha256((ROOT / 'legacy_kernel.py').read_bytes()).hexdigest(), 'worker': hashlib.sha256((ROOT / 'worker.py').read_bytes()).hexdigest()})
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
        if variant['input_source'] == 'context':
            all_columns = list(columns)
            btr, bte = tr[all_columns].copy(), te[all_columns].copy()
        else:
            opts = E.opts_of(g)
            base = E.H.cols_for(opts)
            all_columns = E.cols_of(g, base)
            assert not any(c.startswith(FORBIDDEN_BASE) for c in all_columns)
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
        assert not any(c.startswith(('vcmb_', 'slot_', 'f50_', 'report_')) for c in all_columns)
        selector.fit(btr[all_columns], yy)
        selected = [c for _, c in sorted(zip(selector.feature_importances_, all_columns), reverse=True)[:min(60, len(all_columns))]]
        assert len(set(selected)) == len(selected)
        _check_base_matrices(btr, bte, selected, variant)
        source_columns, source_selection = {}, {}
        for family in ['anthropometry', 'athletics', 'shooting']:
            source_columns[family], source_selection[family] = _eligible_columns(tr, plan['families'][family], plan['source_filter'])
        source_columns['all'] = sum([source_columns[f] for f in ['anthropometry', 'athletics', 'shooting']], [])
        source_columns['baseline'] = []
        assert source_columns['shooting'] == plan['excluded_families']['shooting']['eligibility_by_fold'][str(year)] == []
        truth_map = labels[(labels.season_end <= 2018) & (labels.ordinal <= k)].groupby('pid').war.sum()
        truth = te.pid.map(truth_map).fillna(0)
        audit = {'study_hash': study_hash, 'backbone': backbone, 'baseline_source_variant': variant['id'],
                 'ordered_base_columns': selected, 'base_columns_hash': _hash(selected),
                 'training_pid_hash': _hash(tr.pid.tolist()), 'validation_pid_hash': _hash(te.pid.tolist()),
                 'training_labels_hash': hashlib.sha256(np.asarray(yy, dtype=np.float64).tobytes()).hexdigest(),
                 'training_matrix_hash': _matrix_hash(btr[selected]), 'validation_matrix_hash': _matrix_hash(bte[selected]),
                 'source_selection': source_selection, 'source_selection_hash': _hash(source_selection),
                 'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                 'input_source': variant['input_source'], 'diagnostic_only': True}
        folds.append({'year': year, 'cutoff': cutoff, 'k': k, 'tr': tr, 'te': te,
                      'btr': btr[selected].copy(), 'bte': bte[selected].copy(), 'yy': yy, 'truth': truth,
                      'source_columns': source_columns, 'audit': audit})
    _CACHE[backbone] = E, plan, g, folds, columns
    return _CACHE[backbone][:4]


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
            'interpretation': 'Pre-2019 diagnostics; no confirmation/test selection or automatic promotion. Matched shuffles preserve masks and cohort marginals but break covariance and derived-field algebra. Paired gains include usable family joint structure. Three model/shuffle seeds are not independent datasets. Six active exploratory comparisons; shooting untestable in these training folds; no significance claim. All-versus-single families with different shapes do not establish complementarity.'}
