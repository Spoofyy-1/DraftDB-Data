"""R8r input/control tests; artificial fixtures never become model data or results."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys
import types
import warnings
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
    features, selection = W._source_selection(tr, plan, year)
    audits, hashes, changes = {}, {}, {}
    for variant in plan['variants']:
        pair, value_hashes, modified = [], {}, {}
        for role, frame in [('train', tr), ('validation', te)]:
            columns = features[variant['family']]
            values, audit = W._slots(frame, columns, variant, plan, role)
            assert list(values) == (['slot_0'] if columns else [])
            value_hashes[role] = W._matrix_hash(pd.DataFrame(values, index=frame.index))
            modified[role] = {c: int((frame[c].notna() & (frame[c] != values['slot_0'])).sum()) for c in columns}
            if variant['arm'] == 'real':
                assert not any(modified[role].values())
            elif variant['arm'] == 'permuted':
                for col in columns:
                    permuted = W._permuted(frame[col], frame, col, variant['permutation_seed'], role)
                    reordered = frame.iloc[::-1]
                    other = W._permuted(reordered[col], reordered, col, variant['permutation_seed'], role)
                    assert permuted.equals(other.reindex(frame.index))
                    checks += 1
            pair.append(audit)
        audits[variant['id']], hashes[variant['id']], changes[variant['id']] = pair, value_hashes, modified
    for feature in plan['active_families']:
        for seed in plan['permutation_seeds']:
            assert audits[feature + '_real'] == audits[f'{feature}_shuffle{seed}']
    print(json.dumps({'preflight_fold': year, 'eligible_features': sum(bool(features[c]) for c in plan['candidate_features']),
                      'training_rows': len(tr), 'validation_rows': len(te)}), flush=True)
    folds.append({'season': year, 'training_rows': len(tr), 'validation_rows': len(te),
                  'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                  'features': features, 'selection': selection, 'slot_audits': audits, 'slot_hashes': hashes, 'changes': changes})

# Training-only coverage and nonconstant thresholds; no validation argument exists.
eligibility_fixture = pd.DataFrame({'few': [1., 2., 3., 4., np.nan, np.nan], 'constant': [1.] * 6,
                                   'eligible': [1., 2., 1., 2., 1., np.nan], 'missing': [np.nan] * 6})
assert W._eligible_columns(eligibility_fixture, list(eligibility_fixture), plan['source_filter'])[0] == ['eligible']
# A wholly untestable feature would not be queued; no feature has that status here.
for feature in plan['candidate_features']:
    eligible = any(row['eligible'] and row['swappable_training_observed'] > 0 for fold in folds for row in fold['selection'] if row['feature'] == feature)
    assert eligible == (feature in plan['active_families'])

# Artificial score fixtures validate aggregation only; never saved as run results.
fixture = []
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows = []
        for fold in folds:
            family, arm = variant['family'], variant['arm']
            score = .3 + .01 * (fold['season'] - 2012) + seed / 100000
            if family != 'baseline':
                score += .02 if arm == 'real' else plan['permutation_seeds'].index(variant['permutation_seed']) * .001
            columns = fold['features'][family]
            audit = {k: 'fixture_only' for k in ['study_hash', 'training_pid_hash', 'validation_pid_hash', 'training_labels_hash', 'base_columns_hash', 'training_matrix_hash', 'validation_matrix_hash']}
            audit.update({'backbone': 'source_college', 'baseline_source_variant': plan['baseline_variants']['source_college']['id'],
                          'ordered_base_columns': ['fixture_base'], 'source_selection': fold['selection'], 'source_selection_hash': W._hash(fold['selection']),
                          'max_label_season': fold['max_label_season'], 'training_max_draft_year': fold['training_max_draft_year'],
                          'source_columns': columns, 'input_columns': ['fixture_base'] + (['slot_0'] if columns else []),
                          'raw_feature_count': 1 + len(columns), 'training_nonconstant_columns': 1 + len(columns),
                          'train_slots': fold['slot_audits'][variant['id']][0], 'validation_slots': fold['slot_audits'][variant['id']][1],
                          'slot_matrix_hashes': fold['slot_hashes'][variant['id']], 'changed_source_values': fold['changes'][variant['id']]})
            rows.append({'season': fold['season'], 'stack': score, 'n': fold['validation_rows'], 'ntrain': fold['training_rows'],
                         'cutoff': fold['season'] - 1, 'max_label_season': fold['max_label_season'], 'audit': audit})
        fixture.append({'task_id': f"{variant['id']}_seed{seed}", 'config': dict(variant), 'seed': seed,
                        'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True})
summary = W.summarize_matched(fixture)
assert len(summary['statistics']) == len(plan['active_families']) and summary['all_results_complete']
assert all(np.isclose(s['paired_mean_gain'], .019) for s in summary['statistics'])
assert not summary['combinations_registered']
assert W.summarize_matched(fixture[:-1])['pending_families'] == ['source_college__' + plan['active_families'][-1]]
assert not W.summarize_matched(fixture[:-1])['all_results_complete']
assert W.summarize_matched([])['completed_tasks'] == 0
for entry in fixture:
    entry['config']['id'] = entry['task_id']
assert W.summarize_matched(fixture)['all_results_complete']
for entry in fixture:
    entry['config']['id'] = entry['config']['id'].rsplit('_seed', 1)[0]
rejections = []
for field in ['mask', 'base_training', 'base_validation', 'slot_values', 'cutoff', 'config', 'duplicate']:
    altered = copy.deepcopy(fixture)
    target = next(r for r in altered if r['config']['id'] == plan['active_families'][0] + '_shuffle9317')
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
        altered.append(copy.deepcopy(target))
    try:
        W.summarize_matched(altered)
    except AssertionError:
        rejections.append(field)
    else:
        raise AssertionError('Unrejected tamper: ' + field)

# Replace only the CPU selector with a fixed-order fixture, not a trained model.
class SelectorFixture:
    calls = []
    def __init__(self, **kw):
        assert kw['random_state'] == 11 and kw['device'] == 'cpu'
    def fit(self, frame, target):
        assert list(frame) == plan['base_columns'] and len(frame.columns) == 41
        self.calls.append(list(frame))
        self.feature_importances_ = np.arange(len(frame.columns), dtype=float)
        return self
sys.modules['xgboost'] = types.SimpleNamespace(XGBRegressor=SelectorFixture)
E, _, _, actual_folds = W._prepared()
assert len(SelectorFixture.calls) == 3
W._prepared()
assert len(SelectorFixture.calls) == 3
spec = importlib.util.spec_from_file_location('r8n_reference_worker', ROOT.parent / 'r8n/worker.py')
reference = importlib.util.module_from_spec(spec); spec.loader.exec_module(reference)
_, _, _, expected_folds = reference._prepared(plan['baseline_variants']['source_college'])
comparisons = []
for actual, expected in zip(actual_folds, expected_folds):
    assert actual['year'] == expected['year']
    pd.testing.assert_frame_equal(actual['btr'], expected['btr'])
    pd.testing.assert_frame_equal(actual['bte'], expected['bte'])
    assert np.array_equal(actual['yy'], expected['yy'])
    assert actual['tr'].pid.tolist() == expected['tr'].pid.tolist()
    assert actual['te'].pid.tolist() == expected['te'].pid.tolist()
    comparisons.append({'season': actual['year'], 'columns': len(actual['btr'].columns), 'reference_matrices_and_labels_match': True})
# All legacy data transformations must remain unreachable from source preparation.
old_setup = E.setup
saved = {k: getattr(E, k) for k in ['opts_of', 'cols_of', 'feat_tx', 'stats_of', 'add_feats']}
def forbidden(*args, **kwargs):
    raise AssertionError('Legacy transformation invoked in source-only study')
def setup_with_traps(columns):
    old_setup(columns)
    for name in ['cols_for', 'fit_prior', 'build']:
        setattr(E.H, name, forbidden)
try:
    E.setup = setup_with_traps
    for name in saved:
        setattr(E, name, forbidden)
    W._CACHE = None
    W._prepared()
finally:
    E.setup = old_setup
    for name, value in saved.items():
        setattr(E, name, value)
report = {'status': 'passed_without_model_execution', 'tasks': plan['execution']['task_count'], 'active_features': len(plan['active_families']),
          'excluded_features': plan['excluded_families'], 'model_universe_rows': len(x), 'baseline_columns': 41,
          'source_observations': int(x[plan['candidate_features']].notna().sum().sum()),
          'cohort_permutation_reorder_checks': checks, 'paired_summary_fixture_passed': True,
          'incomplete_results_prevent_combination_phase': True, 'runner_task_id_config_compatibility': True,
          'tamper_rejections': rejections, 'training_only_filter_thresholds_passed': True,
          'fixed_order_selector_fixture_reference_replay': comparisons, 'legacy_transform_bypass_passed': True,
          'cpu_top60_selector_executed': False, 'gpu_model_executed': False,
          'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ['worker.py', 'plan.json', 'prepare_data.py', 'preflight.py', 'legacy_kernel.py', 'README.md']},
          'folds': [{k: v for k, v in f.items() if k not in ['slot_audits', 'slot_hashes', 'changes', 'selection']} for f in folds]}
(ROOT / 'preflight.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k not in ['folds', 'code_sha256', 'fixed_order_selector_fixture_reference_replay']}, indent=2))
