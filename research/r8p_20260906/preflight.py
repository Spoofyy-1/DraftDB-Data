"""Check real source joins and controls without importing a model or using GPU."""
from pathlib import Path
import copy
import json
import numpy as np
import worker as W

ROOT = Path(__file__).resolve().parent
plan, manifest, x, labels = W._load_inputs()
folds = []
slot_checks = 0
for year in plan['folds']:
    tr = x[(x.draft_year >= plan['backbone']['window']) & (x.draft_year <= year - 2)].copy().reset_index(drop=True)
    te = x[(x.draft_year == year) & (x.was_drafted == 1)].copy().reset_index(drop=True)
    used = labels[(labels.season_end <= year - 1) & labels.pid.isin(tr.pid)]
    assert not set(tr.pid) & set(te.pid) and (used.season_end <= year - 1).all()
    features, selection, coverage = {}, {}, {}
    for family in ['numeric', 'text']:
        features[family], selection[family] = W._eligible_columns(tr, plan['families'][family], plan['source_filter'])
        cols = features[family]
        coverage[family] = {'columns': len(cols), 'training_covered': int(tr[cols].notna().any(axis=1).sum()),
                            'validation_covered': int(te[cols].notna().any(axis=1).sum())}
    features['joint'] = features['numeric'] + features['text']
    features['baseline'] = []
    audits = {}
    for variant in plan['variants']:
        pair = []
        for role, frame in [('train', tr), ('validation', te)]:
            values, audit = W._slots(frame, features[variant['family']], variant, plan, role)
            assert list(values) == [plan['slot_mapping'][c] for c in features[variant['family']]]
            if variant['arm'] == 'permuted':
                for col in features[variant['family']]:
                    # Permutation is invariant to physical row order because it
                    # sorts exact PIDs within a cohort before randomization.
                    permuted = W._permuted(frame[col], frame, col, variant['permutation_seed'], role)
                    reordered = frame.iloc[::-1]
                    other = W._permuted(reordered[col], reordered, col, variant['permutation_seed'], role)
                    assert permuted.equals(other.reindex(frame.index))
                    slot_checks += 1
            pair.append(audit)
        audits[variant['id']] = pair
    for family in ['numeric', 'text', 'joint']:
        for seed in plan['permutation_seeds']:
            assert audits[family + '_real'] == audits[f'{family}_shuffle{seed}']
    folds.append({'season': year, 'training_rows': len(tr), 'validation_rows': len(te),
                  'training_max_draft_year': int(tr.draft_year.max()), 'max_label_season': int(used.season_end.max()),
                  'coverage': coverage, 'features': features, 'selection': selection, 'slot_audits': audits})

# Small artificial scores test paired aggregation and tamper rejection. These
# are fixture scores only, not experiment results, and are never saved as runs.
fixture = []
for variant in plan['variants']:
    for seed in plan['seeds']:
        rows = []
        for fold in folds:
            family, arm = variant['family'], variant['arm']
            score = .30 + .01 * (fold['season'] - 2012) + seed / 100000
            if family != 'baseline':
                score += .02 if arm == 'real' else plan['permutation_seeds'].index(variant['permutation_seed']) * .001
            source_columns = fold['features'][family]
            audit = {key: 'fixture_only' for key in ['study_hash', 'base_columns_hash', 'training_pid_hash', 'validation_pid_hash', 'training_labels_hash', 'training_matrix_hash']}
            audit.update({'source_selection_hash': W._hash(fold['selection']), 'max_label_season': fold['max_label_season'],
                          'training_max_draft_year': fold['training_max_draft_year'], 'source_columns': source_columns,
                          'input_columns': ['fixture_base'] + [plan['slot_mapping'][c] for c in source_columns],
                          'raw_feature_count': 1 + len(source_columns), 'training_nonconstant_columns': 1 + len(source_columns),
                          'train_slots': fold['slot_audits'][variant['id']][0], 'validation_slots': fold['slot_audits'][variant['id']][1]})
            rows.append({'season': fold['season'], 'stack': score, 'n': fold['validation_rows'], 'ntrain': fold['training_rows'],
                         'cutoff': fold['season'] - 1, 'max_label_season': fold['max_label_season'], 'audit': audit})
        fixture.append({'task_id': f"{variant['id']}_seed{seed}", 'config': dict(variant), 'seed': seed,
                        'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows, 'diagnostic_only': True})
summary = W.summarize_matched(fixture)
assert len(summary['statistics']) == 3 and summary['completed_tasks'] == 39
assert all(np.isclose(s['paired_mean_gain'], .019) for s in summary['statistics'])
assert W.summarize_matched(fixture[:-1])['pending_families'] == ['joint']
tampered = copy.deepcopy(fixture)
next(r for r in tampered if r['config']['id'] == 'numeric_shuffle9317')['rows'][0]['audit']['train_slots'][0]['mask_hash'] = 'changed'
try:
    W.summarize_matched(tampered)
except AssertionError:
    mask_tamper_rejected = True
else:
    raise AssertionError('Unmatched missingness was not rejected')
report = {'status': 'passed_without_model_execution', 'tasks': 39, 'model_universe_rows': len(x),
          'source_observations': int(x[manifest['source_features']].notna().sum().sum()),
          'unmatched_source_identities_excluded': manifest['unmatched_source_identities_excluded'],
          'cohort_permutation_reorder_checks': slot_checks, 'paired_summary_fixture_passed': True,
          'incomplete_family_withheld': True, 'mask_tamper_rejected': mask_tamper_rejected,
          'cpu_top60_selector_executed': False, 'gpu_model_executed': False,
          'folds': [{k: v for k, v in f.items() if k not in ['slot_audits', 'selection']} for f in folds]}
(ROOT / 'preflight.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k not in ['folds', 'unmatched_source_identities_excluded']}, indent=2))
