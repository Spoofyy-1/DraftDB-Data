"""Freeze at most three matched pairs after BOTH R8i and R8j finish.

Usage: python planner.py --summaries path/i_summary.json path/j_summary.json
Each summary must sit beside its completed state.json; ../plan.json and
../worker.py are the corresponding registered source study. No model is fitted.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import itertools
import json
import time


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_source(summary_path):
    summary_path = Path(summary_path).resolve()
    state_path = summary_path.parent / 'state.json'
    plan_path = summary_path.parent.parent / 'plan.json'
    worker_path = summary_path.parent.parent / 'worker.py'
    state = json.loads(state_path.read_text())
    plan = json.loads(plan_path.read_text())
    summary = json.loads(summary_path.read_text())
    name = plan['study'].split()[0]
    if name not in ['R8i', 'R8j']:
        raise ValueError('Only completed R8i and R8j summaries are permitted')
    expected = {f"{v['id']}_seed{seed}" for v in plan['variants'] for seed in plan['seeds']}
    actual = [r.get('task_id') for r in state['candidates']]
    if state.get('status') != 'completed' or state.get('completed') != state.get('total'):
        raise ValueError(f'{name} is not completed; pair registration prohibited')
    if len(actual) != len(expected) or set(actual) != expected or len(set(actual)) != len(actual):
        raise ValueError(f'{name} is missing or duplicating registered tasks')
    if any('error' in r or 'score' not in r for r in state['candidates']):
        raise ValueError(f'{name} has invalid tasks; resolve explicitly before pair registration')
    # Re-run the source's complete matched-shape audits without fitting any model.
    spec = importlib.util.spec_from_file_location(f'pair_source_{name}', worker_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checked = module.summarize_matched(state['candidates'])
    expected_features = {v['features'][0] for v in plan['variants'] if v['arms'] == ['real']}
    supplied = {row['id']: row for row in summary['statistics']}
    recalculated = {row['id']: row for row in checked['statistics']}
    if set(supplied) != expected_features or set(recalculated) != expected_features:
        raise ValueError(f'{name} lacks one or more complete matched feature summaries')
    for feature, row in recalculated.items():
        for field in ['passes', 'fold_gains', 'gain', 'real_score', 'matched_control_score']:
            if supplied[feature][field] != row[field]:
                raise ValueError(f'Stale or inconsistent {name} summary: {feature}/{field}')
    metadata = {'study': name, 'summary_path': str(summary_path), 'state_sha256': _hash(state_path),
                'summary_sha256': _hash(summary_path), 'plan_sha256': _hash(plan_path),
                'worker_sha256': _hash(worker_path),
                'fold_signatures': {str(r['season']): {k:r['audit'][k] for k in ['base_columns_hash','training_pid_hash','training_labels_hash','training_matrix_hash']} for r in state['candidates'][0]['rows']}}
    return plan, checked, metadata


def build_plan(summary_paths):
    if len(summary_paths) != 2:
        raise ValueError('Exactly two summary files are required: completed R8i and R8j')
    sources = [_load_source(path) for path in summary_paths]
    if {source[2]['study'] for source in sources} != {'R8i', 'R8j'}:
        raise ValueError('Both R8i and R8j are required, without duplicates')
    sources.sort(key=lambda source: source[2]['study'])
    first = sources[0][0]
    for other, _, _ in sources[1:]:
        for field in ['backbone', 'folds', 'seeds', 'permutation_seeds']:
            if first[field] != other[field]:
                raise ValueError(f'Incompatible source study protocols: {field}')
    gates = [{k:v for k,v in p['provisional_gate'].items() if k != 'global_selection_note'} for p,_,_ in sources]
    if gates[0] != gates[1]:raise ValueError('Incompatible quantitative feature gates')
    if sources[0][2]['fold_signatures'] != sources[1][2]['fold_signatures']:raise ValueError('Unmatched base or training data across source studies')
    all_statistics = [row for _, summary, _ in sources for row in summary['statistics']]
    if len(all_statistics) != 50 or len({row['id'] for row in all_statistics}) != 50:
        raise ValueError('Exactly 50 distinct completed matched feature comparisons are required')
    qualified = sorted((row for row in all_statistics if row['passes']), key=lambda row: (-row['gain'], row['id']))[:3]
    pairs = list(itertools.combinations([row['id'] for row in qualified], 2))[:3]
    variants = []
    pair_ids = []
    pair_records = []
    for index, pair in enumerate(pairs):
        pair_id = f'pair{index:02d}'
        pair_ids.append(pair_id)
        pair_records.append({'id': pair_id, 'features': list(pair)})
        variants.append({'id': pair_id + '__RR', 'pair_id': pair_id, 'features': list(pair),
                         'arms': ['real', 'real'], 'permutation_seed': None})
        for seed in first['permutation_seeds']:
            for label, arms in [('RP', ['real', 'permuted']), ('PR', ['permuted', 'real']), ('PP', ['permuted', 'permuted'])]:
                variants.append({'id': f'{pair_id}__{label}_perm{seed}', 'pair_id': pair_id,
                                 'features': list(pair), 'arms': arms, 'permutation_seed': seed})
    plan = {**first, 'study': 'R8k matched two-slot complementary pairs',
            'purpose': 'Bounded pre-2019 complementarity study selected from completed matched R8i and R8j summaries; no test-based selection.',
            'variants': variants, 'selected_pair_ids': pair_ids, 'pairs': pair_records,
            'source_studies': [source[2] for source in sources], 'registered_at': time.time(),
            'selected_singles': qualified,
            'pair_phase': {**first['pair_phase'], 'enabled': True, 'maximum_pairs': 3,
                           'arms_per_pair': 10, 'paired_model_seeds': first['seeds'],
                           'rr_reuse': 'One RR task per model seed; shared across all three permutation replicates.',
                           'shuffle': 'Independent feature streams retaining each exact per-player mask and cohort distribution; PP intentionally breaks the interfeature relationship for this factorial diagnostic.',
                           'interpretation': 'Representation complementarity in the fitted backbone, not a significance test.'},
            'pair_gate': {'min_joint_minus_each_single': 0.005, 'min_improved_folds_each': 2,
                          'max_fold_regression_each': 0.01,
                          'require_positive_interaction': False,
                          'interpretation': 'Exploratory paired improvement; interaction reported separately and never hidden.'},
            'execution': {**first['execution'], 'task_count': len(variants) * len(first['seeds'])}}
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summaries', nargs=2, required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('plan.json'))
    args = parser.parse_args()
    plan = build_plan(args.summaries)
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        a, b = dict(previous), dict(plan)
        a.pop('registered_at', None); b.pop('registered_at', None)
        if a != b:
            raise ValueError('An existing pair registration differs; refusing to overwrite')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'pairs': plan['pairs'], 'tasks': plan['execution']['task_count'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
