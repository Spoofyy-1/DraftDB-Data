"""R8q source/control tests. No model fitting, GPU execution or experiment scores."""
from pathlib import Path
import warnings
import copy
import hashlib
import importlib.util
import json
import sys
import types
import numpy as np
import pandas as pd
import worker as W
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)

ROOT = Path(__file__).resolve().parent
plan, manifest, x, labels = W._load_inputs()
folds, checks = [], 0
for year in plan['folds']:
    tr = x[(x.draft_year >= plan['backbone']['window']) & (x.draft_year <= year - 2)].copy().reset_index(drop=True)
    te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
    used = labels[(labels.season_end <= year - 1) & labels.pid.isin(tr.pid)]
    assert not set(tr.pid) & set(te.pid) and (used.season_end <= year - 1).all()
    features, selection, coverage = {}, {}, {}
    for family in ['anthropometry', 'athletics', 'shooting']:
        features[family], selection[family] = W._eligible_columns(tr, plan['families'][family], plan['source_filter'])
        columns = features[family]
        coverage[family] = {'columns': len(columns), 'training_covered': int(tr[columns].notna().any(axis=1).sum()),
                            'validation_covered': int(te[columns].notna().any(axis=1).sum())}
    features['all'] = sum([features[f] for f in ['anthropometry', 'athletics', 'shooting']], [])
    features['baseline'] = []
    audits, slot_hashes, changed = {}, {}, {}
    for variant in plan['variants']:
        pair, hashes, modifications = [], {}, {}
        for role, frame in [('train', tr), ('validation', te)]:
            values, audit = W._slots(frame, features[variant['family']], variant, plan, role)
            assert list(values) == [plan['slot_mapping'][c] for c in features[variant['family']]]
            value_frame = pd.DataFrame(values, index=frame.index)
            hashes[role] = W._matrix_hash(value_frame)
            modifications[role] = {c: int((frame[c].notna() & (frame[c] != values[plan['slot_mapping'][c]])).sum()) for c in features[variant['family']]}
            if variant['arm'] == 'real':
                assert not any(modifications[role].values())
            elif variant['arm'] == 'permuted':
                for col in features[variant['family']]:
                    permuted = W._permuted(frame[col], frame, col, variant['permutation_seed'], role)
                    reordered = frame.iloc[::-1]
                    other = W._permuted(reordered[col], reordered, col, variant['permutation_seed'], role)
                    assert permuted.equals(other.reindex(frame.index))
                    checks += 1
            pair.append(audit)
        audits[variant['id']], slot_hashes[variant['id']], changed[variant['id']] = pair, hashes, modifications
    for backbone in plan['baseline_variants']:
        for family in plan['active_families']:
            for seed in plan['permutation_seeds']:
                assert audits[f'{backbone}__{family}_real'] == audits[f'{backbone}__{family}_shuffle{seed}']
    for family in plan['active_families']:
        for arm in ['real'] + [f'shuffle{s}' for s in plan['permutation_seeds']]:
            assert audits[f'source_college__{family}_{arm}'] == audits[f'quarantined_legacy__{family}_{arm}']
            assert slot_hashes[f'source_college__{family}_{arm}'] == slot_hashes[f'quarantined_legacy__{family}_{arm}']
    print(json.dumps({'preflight_fold': year, 'coverage': coverage}), flush=True)
    folds.append({'season': year, 'training_rows': len(tr), 'validation_rows': len(te),
                  'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                  'coverage': coverage, 'features': features, 'selection': selection, 'slot_audits': audits,
                  'slot_hashes': slot_hashes, 'changed': changed})

# Coverage/uniqueness threshold fixtures: only the provided training frame is used.
training_fixture = pd.DataFrame({'below5': [1., 2., 3., 4., np.nan, np.nan],
                                 'constant': [1.] * 6, 'eligible': [1., 2., 1., 2., 1., np.nan],
                                 'validation_only': [np.nan] * 6})
eligible, selection = W._eligible_columns(training_fixture, list(training_fixture), plan['source_filter'])
assert eligible == ['eligible']

# Fixture scores only. These are never saved as experiment results or used by a model.
fixture = []
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows = []
        for fold in folds:
            family, arm, backbone = variant['family'], variant['arm'], variant['backbone']
            score = .30 + .01 * (fold['season'] - 2012) + seed / 100000
            if backbone == 'quarantined_legacy':
                score += .03
            if family != 'baseline':
                score += .02 if arm == 'real' else plan['permutation_seeds'].index(variant['permutation_seed']) * .001
            source_columns = fold['features'][family]
            audit = {k: 'fixture_only' for k in ['study_hash', 'training_pid_hash', 'validation_pid_hash', 'training_labels_hash']}
            audit.update({k: 'fixture_' + backbone for k in ['base_columns_hash', 'training_matrix_hash', 'validation_matrix_hash']})
            audit.update({'backbone': backbone, 'baseline_source_variant': plan['baseline_variants'][backbone]['id'],
                          'ordered_base_columns': ['fixture_' + backbone], 'source_selection': fold['selection'],
                          'source_selection_hash': W._hash(fold['selection']), 'max_label_season': fold['max_label_season'],
                          'training_max_draft_year': fold['training_max_draft_year'], 'source_columns': source_columns,
                          'input_columns': ['fixture_' + backbone] + [plan['slot_mapping'][c] for c in source_columns],
                          'raw_feature_count': 1 + len(source_columns), 'training_nonconstant_columns': 1 + len(source_columns),
                          'train_slots': fold['slot_audits'][variant['id']][0], 'validation_slots': fold['slot_audits'][variant['id']][1],
                          'slot_matrix_hashes': fold['slot_hashes'][variant['id']], 'changed_source_values': fold['changed'][variant['id']]})
            rows.append({'season': fold['season'], 'stack': score, 'n': fold['validation_rows'], 'ntrain': fold['training_rows'],
                         'cutoff': fold['season'] - 1, 'max_label_season': fold['max_label_season'], 'audit': audit})
        fixture.append({'task_id': f"{variant['id']}_seed{seed}", 'config': dict(variant), 'seed': seed,
                        'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True})
summary = W.summarize_matched(fixture)
assert len(summary['statistics']) == 6 and summary['completed_tasks'] == 78
assert all(np.isclose(s['paired_mean_gain'], .019) for s in summary['statistics'])
assert W.summarize_matched(fixture[:-1])['pending_families'] == ['quarantined_legacy__all']
assert W.summarize_matched([])['completed_tasks'] == 0
for entry in fixture:
    entry['config']['id'] = entry['task_id']
assert W.summarize_matched(fixture)['completed_tasks'] == 78
for entry in fixture:
    entry['config']['id'] = entry['config']['id'].rsplit('_seed', 1)[0]
rejections = []
for field in ['mask', 'base_training', 'base_validation', 'slot_values', 'cutoff', 'config', 'duplicate']:
    tampered = copy.deepcopy(fixture)
    target = next(r for r in tampered if r['config']['id'] == 'source_college__anthropometry_shuffle9317')
    target['rows'][0]['audit'] = copy.deepcopy(target['rows'][0]['audit'])
    if field == 'mask':
        target['rows'][0]['audit']['train_slots'][0]['mask_hash'] = 'changed'
    elif field == 'base_training':
        target['rows'][0]['audit']['training_matrix_hash'] = 'changed'
    elif field == 'base_validation':
        target['rows'][0]['audit']['validation_matrix_hash'] = 'changed'
    elif field == 'slot_values':
        target['rows'][0]['audit']['slot_matrix_hashes']['train'] = 'changed'
    elif field == 'cutoff':
        target['rows'][0]['audit']['max_label_season'] = 2019
    elif field == 'config':
        target['config']['permutation_seed'] = 0
    else:
        tampered.append(copy.deepcopy(target))
    try:
        W.summarize_matched(tampered)
    except AssertionError:
        rejections.append(field)
    else:
        raise AssertionError('Tampering not rejected: ' + field)

# Exercise both real baseline transformation branches, but replace XGBoost's
# selector with a fixed column-order fixture: no CPU or GPU model is trained.
# Then compare to the registered R8n implementation under that same fixture.
class SelectorFixture:
    calls = []
    def __init__(self, **kwargs):
        assert kwargs['random_state'] == 11 and kwargs['device'] == 'cpu'
    def fit(self, frame, target):
        assert not any(c.startswith(('vcmb_', 'slot_', 'f50_', 'report_')) for c in frame)
        self.calls.append(list(frame))
        self.feature_importances_ = np.arange(len(frame.columns), dtype=float)
        return self

sys.modules['xgboost'] = types.SimpleNamespace(XGBRegressor=SelectorFixture)
preparations = {}
for backbone in plan['baseline_variants']:
    preparations[backbone] = W._prepared(backbone)
assert len(SelectorFixture.calls) == 6
W._prepared('source_college')
assert len(SelectorFixture.calls) == 6, 'Cached base preparation was not reused'
spec = importlib.util.spec_from_file_location('r8n_reference_worker', ROOT.parent / 'r8n/worker.py')
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
comparison = []
for backbone, variant in plan['baseline_variants'].items():
    _, _, _, inherited_folds = reference._prepared(variant)
    _, _, _, local_folds = preparations[backbone]
    for actual, expected in zip(local_folds, inherited_folds):
        assert actual['year'] == expected['year']
        for key in ['btr', 'bte']:
            pd.testing.assert_frame_equal(actual[key], expected[key])
        assert np.array_equal(actual['yy'], expected['yy'])
        assert actual['tr'].pid.tolist() == expected['tr'].pid.tolist()
        assert actual['te'].pid.tolist() == expected['te'].pid.tolist()
        comparison.append({'backbone': backbone, 'season': actual['year'], 'columns': len(actual['btr'].columns),
                           'reference_matrices_and_training_labels_match': True})
# Verify source-only preparation never calls any legacy input transformation.
E = preparations['source_college'][0]
original_setup = E.setup
saved = {k: getattr(E, k) for k in ['opts_of', 'cols_of', 'feat_tx', 'stats_of', 'add_feats']}
def forbidden(*args, **kwargs):
    raise AssertionError('Source-only path invoked a legacy transform')
def strict_setup(columns):
    original_setup(columns)
    for name in ['cols_for', 'fit_prior', 'build']:
        setattr(E.H, name, forbidden)
try:
    E.setup = strict_setup
    for k in saved:
        setattr(E, k, forbidden)
    W._CACHE.pop('source_college')
    W._prepared('source_college')
finally:
    E.setup = original_setup
    for k, value in saved.items():
        setattr(E, k, value)

report = {'status': 'passed_without_model_execution', 'tasks': 78, 'model_universe_rows': len(x),
          'source_observations': int(x[manifest['source_features']].notna().sum().sum()),
          'untestable_families': plan['excluded_families'],
          'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ['worker.py', 'plan.json', 'prepare_data.py', 'preflight.py', 'legacy_kernel.py', 'README.md']},
          'cohort_permutation_reorder_checks': checks, 'paired_summary_fixture_passed': True,
          'incomplete_family_withheld': True, 'runner_task_id_config_compatibility': True, 'tamper_rejections': rejections, 'training_only_filter_thresholds_passed': True,
          'fixed_order_selector_fixture_reference_replay': comparison, 'source_only_legacy_transform_bypass_passed': True,
          'cpu_top60_selector_executed': False, 'gpu_model_executed': False,
          'folds': [{k: v for k, v in f.items() if k not in ['slot_audits', 'slot_hashes', 'changed', 'selection']} for f in folds]}
(ROOT / 'preflight.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k not in ['folds', 'fixed_order_selector_fixture_reference_replay']}, indent=2))
