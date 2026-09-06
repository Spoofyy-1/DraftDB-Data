"""Source, row-vector controls and factorial fixtures; no model preparation."""
from pathlib import Path
import copy
import hashlib
import json
import numpy as np
import pandas as pd
import worker as W

ROOT = Path(__file__).resolve().parent
plan, manifest, x, labels = W._load_inputs()
folds, designs, coverage, order_checks = [], {}, {}, 0
base = plan['baseline_source_variant']['context_features']
assert len(base) == 41
for year in plan['folds']:
    tr = x[(x.draft_year >= plan['backbone']['window']) & (x.draft_year <= year - 2)].copy().reset_index(drop=True)
    te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
    used = labels[(labels.season_end <= year - 1) & labels.pid.isin(tr.pid)]
    assert len(used) and not set(tr.pid) & set(te.pid) and (used.season_end <= year - 1).all()
    features, selection = {}, {}
    coverage[str(year)] = {}
    for family in ['combine', 'consensus']:
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
             'source_only_baseline': True, 'diagnostic_only': True}
    fold = {'year': year, 'cutoff': year - 1, 'k': min(5, 2018 - year), 'tr': tr, 'te': te,
            'btr': tr[base].copy(), 'bte': te[base].copy(), 'source_columns': features, 'audit': audit}
    for variant in plan['variants']:
        atr, ate, families = W._design(fold, variant, plan)
        designs[(year, variant['id'])] = {**audit, 'families': families, 'input_columns': list(atr),
                                         'raw_feature_count': len(atr.columns),
                                         'training_nonconstant_columns': int((atr.nunique() > 1).sum())}
    folds.append(fold)

# Synthetic fixture scores below test aggregation only. They are not trained
# model results, are never written to results/, and cannot be displayed as runs.
fixtures = []
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows = []
        for fold in folds:
            score = .30 + .01 * (fold['year'] - 2012) + seed / 100000
            if variant['scope'] in ['combine', 'consensus']:
                score += {'combine': .02, 'consensus': .03}[variant['scope']] if variant['permutation_seed'] is None else 0
            elif variant['scope'] == 'joint':
                code = ''.join('R' if variant['arms'][f] == 'real' else 'P' for f in ['combine', 'consensus'])
                score += {'RR': .10, 'RP': .05, 'PR': .04, 'PP': 0}[code]
            rows.append({'season': fold['year'], 'stack': score, 'n': len(fold['te']), 'ntrain': len(fold['tr']),
                         'cutoff': fold['cutoff'], 'max_label_season': fold['audit']['max_label_season'],
                         'audit': copy.deepcopy(designs[(fold['year'], variant['id'])])})
        fixtures.append({'task_id': f"{variant['id']}_seed{seed}", 'config': dict(variant), 'seed': seed,
                         'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True})
summary = W.summarize_matched(fixtures)
assert summary['completed_tasks'] == 57 and not summary['pending']
for stat in summary['statistics']:
    assert np.isclose(stat['paired_mean_gain'], {'combine': .02, 'consensus': .03}[stat['id']])
for measure, expected in [('consensus_given_combine', .05), ('combine_given_consensus', .06), ('interaction', .01)]:
    assert np.isclose(summary['factorial']['mean_contrasts'][measure], expected)
assert W.summarize_matched(fixtures[:-1])['pending'] == ['joint_factorial']
runner_mutated = copy.deepcopy(fixtures)
for row in runner_mutated:
    row['config']['id'] = row['task_id']
assert W.summarize_matched(runner_mutated) == summary

tamper_tests = []
def rejects(name, mutate):
    changed = copy.deepcopy(fixtures)
    target = next(r for r in changed if r['config']['id'] == 'joint_RP_shuffle9317')
    mutate(target)
    try:
        W.summarize_matched(changed)
    except AssertionError:
        tamper_tests.append(name)
    else:
        raise AssertionError('Tamper accepted: ' + name)

rejects('per_player_mask', lambda t: t['rows'][0]['audit']['families']['consensus']['train']['invariants'].__setitem__('mask_hash', 'changed'))
rejects('family_row_multiset', lambda t: t['rows'][0]['audit']['families']['consensus']['train']['invariants']['groups'][0].__setitem__('vector_multiset_hash', 'changed'))
rejects('stream_reuse', lambda t: t['rows'][0]['audit']['families']['combine']['train'].__setitem__('matrix_hash', 'changed'))
rejects('missing_family', lambda t: t['rows'][0]['audit']['families'].pop('consensus'))
rejects('wrong_slot', lambda t: t['rows'][0]['audit']['input_columns'].__setitem__(-1, 'wrong_slot'))
rejects('future_label_season', lambda t: t['rows'][0]['audit'].__setitem__('max_label_season', 2012))
rejects('unregistered_seed', lambda t: t.__setitem__('seed', 999))
rejects('config_change', lambda t: t['config']['arms'].__setitem__('combine', 'permuted'))

public_root = ROOT.parent / 'verified_consensus'
public = json.loads((public_root / 'public_manifest.json').read_text())
assert all(hashlib.sha256((public_root / name).read_bytes()).hexdigest() == record['sha256'] for name, record in public['files'].items())
report = {'status': 'passed_without_model_execution', 'tasks': 57, 'model_universe_rows': len(x),
          'source_columns_per_fold': {str(f['year']): {k: len(v) for k, v in f['source_columns'].items()} for f in folds},
          'family_vector_order_invariance_checks': order_checks, 'design_checks': len(designs),
          'factorial_summary_fixture_passed': True, 'incomplete_factorial_withheld': True,
          'runner_config_id_normalization_verified': True, 'tamper_rejections': tamper_tests,
          'source_public_manifest_files_unchanged': len(public['files']),
          'cpu_selector_executed': False, 'gpu_model_executed': False,
          'coverage': coverage,
          'required_server_preflight': 'Run _prepared() on CPU and compare source_college base column order, matrices, labels and membership with R8q source-only baseline before launching TabICL.'}
(ROOT / 'preflight.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != 'coverage'}, indent=2))
