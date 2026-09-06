"""R8t source, full-family controls, ordering and exact-vector tie fixtures; no model preparation."""
from pathlib import Path
import copy
import hashlib
import json
import importlib.util
import os
import sys
import types
import numpy as np
import pandas as pd
import worker as W

ROOT = Path(__file__).resolve().parent
plan, manifest, x, labels = W._load_inputs()
bio_root = ROOT.parent / 'verified_mock_bio'
allowlist = json.loads((bio_root / 'PUBLIC_ALLOWLIST.json').read_text())
assert hashlib.sha256((bio_root / 'PUBLIC_ALLOWLIST.json').read_bytes()).hexdigest() == manifest['bio_public_allowlist_sha256']
for name, record in allowlist['files'].items():
    digest = hashlib.sha256((bio_root / name).read_bytes()).hexdigest()
    assert digest == record['sha256'] == manifest['source_package_hashes']['bio'][name]
spec = importlib.util.spec_from_file_location('r8t_bio_replay', bio_root / 'build.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
parser, verified_sources, original_observations = builder.load_verified_inputs()
replayed = []
for source in verified_sources:
    if source['publisher'] == 'dx' and source['feature_eligible']:
        facts, _, _ = builder.extract_source(source, original_observations, parser)
        replayed.extend(facts)
replay = pd.DataFrame(replayed)
assert len(replay) == 374 and list(replay) == ['pid', 'draft_year'] + plan['families']['bio']
assert hashlib.sha256(replay.to_csv(index=False).encode()).hexdigest() == allowlist['files']['features_eligible.csv']['sha256']
frozen = json.loads((ROOT.parent / 'r8s/data/manifest.json').read_text())
for name in ['features.csv', 'labels.csv', 'incumbent.json', 'consensus_features.csv', 'consensus_provenance.csv', 'consensus_sources.json']:
    assert manifest['files'][name] == frozen['files'][name]
folds, designs, coverage, order_checks = [], {}, {}, 0
base = plan['baseline_source_variant']['context_features']
assert len(base) == 41
for year in plan['folds']:
    tr = W._canonical_rows(x[(x.draft_year >= plan['backbone']['window']) & (x.draft_year <= year - 2)])
    te = W._canonical_rows(x[(x.draft_year == year) & (x.was_drafted == 1)])
    used = labels[(labels.season_end <= year - 1) & labels.pid.isin(tr.pid)]
    assert len(used) and not set(tr.pid) & set(te.pid) and (used.season_end <= year - 1).all()
    features, selection = {}, {}
    coverage[str(year)] = {}
    for family in ['combine', 'consensus', 'bio']:
        features[family], selection[family] = W._eligible_columns(tr, plan['families'][family], plan['source_filter'])
        assert features[family] == plan['training_eligibility_registration'][str(year)][family]
        coverage[str(year)][family] = {}
        for role, frame in [('train', tr), ('validation', te)]:
            values = frame[features[family]].astype(float)
            invariants = W._vector_invariants(values, frame)
            changed_rows = []
            for seed in plan['permutation_seeds']:
                shuffled = W._vector_shuffle(values, frame, family, seed, role)
                reordered = frame.iloc[::-1]
                other = W._vector_shuffle(reordered[features[family]].astype(float), reordered, family, seed, role)
                pd.testing.assert_frame_equal(shuffled, other.reindex(frame.index))
                # The exact row-vector multiset check preserves derived algebra
                # and all within-family joint distributions, not just marginals.
                assert W._vector_invariants(shuffled, frame) == invariants
                changed_rows.append(int((values.notna() & shuffled.ne(values)).any(axis=1).sum()))
                order_checks += 1
            coverage[str(year)][family][role] = {
                'rows': len(frame), 'columns': len(features[family]),
                **{k: invariants[k] for k in ['observed_rows', 'swappable_observed_rows', 'immovable_observed_rows']},
                'strata': len(invariants['groups']),
                'changed_rows_by_permutation': dict(zip(map(str, plan['permutation_seeds']), changed_rows))}
    # CPU selector is deliberately not run here. All 41 columns are used in a
    # fixed fixture order; server preflight must verify actual selector order.
    audit = {'study_hash': 'fixture_only', 'ordered_base_columns': base, 'base_columns_hash': W._hash(base),
             'training_pid_hash': W._hash(tr.pid.tolist()), 'validation_pid_hash': W._hash(te.pid.tolist()),
             'training_labels_hash': 'fixture_only_no_label_function_called',
             'training_matrix_hash': W._matrix_hash(tr[base]), 'validation_matrix_hash': W._matrix_hash(te[base]),
             'source_selection': selection, 'source_selection_hash': W._hash(selection),
             'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
             'source_only_baseline': True, 'diagnostic_only': True, 'ordering_policy_hash': W._hash(plan['ordering_policy'])}
    fold = {'year': year, 'cutoff': year - 1, 'k': min(5, 2018 - year), 'tr': tr, 'te': te,
            'btr': tr[base].copy(), 'bte': te[base].copy(), 'source_columns': features, 'audit': audit}
    for variant in plan['variants']:
        atr, ate, families = W._design(fold, variant, plan)
        designs[(year, variant['id'])] = {**audit, 'families': families, 'input_columns': list(atr),
                                         'raw_feature_count': len(atr.columns),
                                         'training_nonconstant_columns': int((atr.nunique() > 1).sum())}
        raw = np.arange(len(ate), dtype=float) / len(ate)
        pred, ties = W._canonical_predictions(ate, raw, te.pid.tolist())
        designs[(year, variant['id'])]['canonical_prediction_ties'] = ties
        designs[(year, variant['id'])]['fixture_predictions'] = [{'pid': pid, 'score': float(v), 'raw_score': float(r)} for pid, v, r in zip(te.pid, pred, raw)]
        pd.testing.assert_frame_equal(W._canonical_rows(tr.iloc[::-1]), tr)
        pd.testing.assert_frame_equal(W._canonical_rows(te.iloc[::-1]), te)
    folds.append(fold)

# Small diagnostic-only values test duplicate equivalence and tie operations.
# No fixture is a model input or written to the research results directory.
duplicate_tests = []
tiny = pd.DataFrame({'one': [np.nan, np.nan, 1., 1. + 1e-15, 0., -0.],
                     'two': [np.nan, np.nan, 3., 3., 7., 7.]})
raw = np.asarray([.1, .3, .4, .6, .8, 1.])
pids = ['pid' + str(i) for i in range(len(tiny))]
fixed, tie = W._canonical_predictions(tiny, raw, pids)
assert fixed[0] == fixed[1] == .2 and fixed[4] == fixed[5] == .9
assert fixed[2] == raw[2] and fixed[3] == raw[3] and fixed[2] != fixed[3]
assert tie['distinct_input_vectors'] == 4 and not tie['distinct_vectors_quantized']
duplicate_tests.extend(['all_NaN_vectors_average', 'signed_zero_equivalent', 'distinct_near_vectors_never_quantized'])
perm = np.asarray([3, 5, 1, 0, 2, 4])
reordered, other = W._canonical_predictions(tiny.iloc[perm], raw[perm], [pids[i] for i in perm])
assert np.array_equal(fixed, reordered[np.argsort(perm)])
assert tie['duplicate_groups'] == other['duplicate_groups']
duplicate_tests.append('duplicate_mean_reorder_invariant')
index_only = tiny.copy(); index_only.index = ['unrelated_index_' + str(i) for i in range(len(tiny))]
assert np.array_equal(fixed, W._canonical_predictions(index_only, raw, pids)[0])
duplicate_tests.append('pandas_index_never_predictor')
for key, frame, values, ids in [('infinite_input', tiny.replace({1.: np.inf}), raw, pids),
                              ('infinite_prediction', tiny, raw * np.inf, pids),
                              ('duplicate_identity', tiny, raw, ['same'] * len(pids))]:
    try:
        W._canonical_predictions(frame, values, ids)
    except AssertionError:
        duplicate_tests.append('reject_' + key)
    else:
        raise AssertionError('Bad tie fixture accepted: ' + key)

constructor_tests = []
original_module, original_seed = sys.modules.get('tabicl'), os.environ.get('SEED_SHIFT')
os.environ['SEED_SHIFT'] = '0'
cfg = {'icl_n': 32, 'icl_kwargs': {k: (0 if k == 'random_state' else v) for k, v in plan['model_constructor'].items() if k not in ['device', 'n_estimators']}}
try:
    class FakeModel:
        def __init__(self, **kwargs): self.kwargs = kwargs
        def get_params(self): return dict(self.kwargs)
    sys.modules['tabicl'] = types.SimpleNamespace(TabICLRegressor=FakeModel)
    model, parameters = W.make_registered_model(cfg)
    assert parameters == {**plan['model_constructor'], 'random_state': 0}
    constructor_tests.append('registered_parameters_preserved')
    class RejectingModel:
        calls = 0
        def __init__(self, **kwargs):
            RejectingModel.calls += 1
            raise TypeError('unsupported registered constructor')
    sys.modules['tabicl'] = types.SimpleNamespace(TabICLRegressor=RejectingModel)
    try: W.make_registered_model(cfg)
    except TypeError: pass
    else: raise AssertionError('Constructor failure did not propagate')
    assert RejectingModel.calls == 1
    constructor_tests.append('TypeError_fails_closed_without_fallback')
    class MutatingModel(FakeModel):
        def get_params(self): return {**self.kwargs, 'n_estimators': 256}
    sys.modules['tabicl'] = types.SimpleNamespace(TabICLRegressor=MutatingModel)
    try: W.make_registered_model(cfg)
    except AssertionError: constructor_tests.append('changed_effective_parameters_rejected')
    else: raise AssertionError('Constructor silently changed effective parameters')
finally:
    if original_module is None: sys.modules.pop('tabicl', None)
    else: sys.modules['tabicl'] = original_module
    if original_seed is None: os.environ.pop('SEED_SHIFT', None)
    else: os.environ['SEED_SHIFT'] = original_seed

# Synthetic aggregation fixtures verify paired calculations only. No outcomes
# are scored and none of these synthetic entries enter results/ or a model.
fixtures = []
gains = dict(zip(plan['backgrounds'], [.02, .03, -.01, .01]))
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows = []
        for fold in folds:
            score = .30 + .01 * (fold['year'] - 2012) + seed / 100000
            if variant['bio_arm'] == 'real': score += gains[variant['background']]
            audit = copy.deepcopy(designs[(fold['year'], variant['id'])])
            predictions = audit.pop('fixture_predictions')
            audit['registered_model_parameters'] = {**plan['model_constructor'], 'random_state': seed}
            rows.append({'season': fold['year'], 'stack': score, 'n': len(fold['te']), 'ntrain': len(fold['tr']),
                         'cutoff': fold['cutoff'], 'max_label_season': fold['audit']['max_label_season'],
                         'audit': audit, 'predictions': predictions})
        fixtures.append({'task_id': f"{variant['id']}_seed{seed}", 'config': dict(variant), 'seed': seed,
                         'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True})
summary = W.summarize_matched(fixtures)
assert summary['completed_tasks'] == 60 and not summary['pending']
assert len(summary['statistics']) == 4 and not summary['earlier_raw_study_scores_pooled']
for stat in summary['statistics']:
    assert np.isclose(stat['paired_mean_gain'], gains[stat['id']])
    assert all(np.isclose(v, gains[stat['id']]) for v in stat['fold_gains'].values())
assert W.summarize_matched(fixtures[:-1])['pending'] == ['college_combine_consensus']
runner_mutated = copy.deepcopy(fixtures)
for row in runner_mutated: row['config']['id'] = row['task_id']
assert W.summarize_matched(runner_mutated) == summary

tamper_tests = []
def rejects(name, mutate):
    changed = copy.deepcopy(fixtures)
    target = next(r for r in changed if r['config']['id'] == 'college_combine_consensus_bio_shuffle9317')
    mutate(target)
    try:
        W.summarize_matched(changed)
    except AssertionError:
        tamper_tests.append(name)
    else:
        raise AssertionError('Tamper accepted: ' + name)

rejects('per_player_mask', lambda t: t['rows'][0]['audit']['families']['bio']['train']['invariants'].__setitem__('mask_hash', 'changed'))
rejects('family_row_multiset', lambda t: t['rows'][0]['audit']['families']['bio']['train']['invariants']['groups'][0].__setitem__('vector_multiset_hash', 'changed'))
rejects('background_values_changed', lambda t: t['rows'][0]['audit']['families']['combine']['train'].__setitem__('matrix_hash', 'changed'))
rejects('missing_family', lambda t: t['rows'][0]['audit']['families'].pop('bio'))
rejects('wrong_slot', lambda t: t['rows'][0]['audit']['input_columns'].__setitem__(-1, 'actual_pick'))
rejects('future_label_season', lambda t: t['rows'][0]['audit'].__setitem__('max_label_season', 2012))
rejects('unregistered_seed', lambda t: t.__setitem__('seed', 999))
rejects('config_change', lambda t: t['config']['arms'].__setitem__('combine', 'permuted'))
rejects('ordering_policy_change', lambda t: t['rows'][0]['audit'].__setitem__('ordering_policy_hash', 'changed'))
rejects('raw_prediction_change', lambda t: t['rows'][0]['predictions'][0].__setitem__('raw_score', -999.))
rejects('canonical_prediction_change', lambda t: t['rows'][0]['predictions'][0].__setitem__('score', -999.))
rejects('prediction_identity_order', lambda t: t['rows'][0]['predictions'].reverse())
rejects('quantization_enabled', lambda t: t['rows'][0]['audit']['canonical_prediction_ties'].__setitem__('distinct_vectors_quantized', True))
rejects('wrong_constructor_seed', lambda t: t['rows'][0]['audit']['registered_model_parameters'].__setitem__('random_state', 999))
rejects('wrong_ensemble_count', lambda t: t['rows'][0]['audit']['registered_model_parameters'].__setitem__('n_estimators', 256))
rejects('wrong_duplicate_vector_hashes', lambda t: t['rows'][0]['audit']['canonical_prediction_ties'].__setitem__('row_vector_hashes', ['0' * 64] * t['rows'][0]['n']))

report = {'status': 'passed_without_model_execution', 'tasks': 60, 'model_universe_rows': len(x),
          'source_columns_per_fold': {str(f['year']): {k: len(v) for k, v in f['source_columns'].items()} for f in folds},
          'family_vector_order_invariance_checks': order_checks, 'design_checks': len(designs),
          'canonical_order_roundtrip_checks': len(designs) * 2, 'duplicate_tie_tests': duplicate_tests,
          'constructor_tests': constructor_tests, 'typed_bio_archive_replay_rows': len(replay),
          'typed_bio_archive_replay_exact_csv_hash': True, 'pinned_bio_public_files': len(allowlist['files']),
          'original_consensus_not_extension_verified': True,
          'paired_summary_fixture_passed': True, 'incomplete_background_withheld': True,
          'runner_config_id_normalization_verified': True, 'tamper_rejections': tamper_tests,
          'cpu_selector_executed': False, 'gpu_model_executed': False, 'coverage': coverage,
          'required_server_preflight': 'Run _prepared() on CPU. Verify canonical SHA256(pid) ordering, unchanged player/value sets and calendar labels, fixed41 source base plus eligible15 combine/4 consensus/10 bio, and all design audit hashes. This policy intentionally defines a new baseline; do not require old raw-order prediction equality.'}
(ROOT / 'preflight.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k: v for k, v in report.items() if k != 'coverage'}, indent=2))
