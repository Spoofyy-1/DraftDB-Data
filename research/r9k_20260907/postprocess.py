"""Score saved development predictions separately from the isolated model process."""
from pathlib import Path
import hashlib
import json
import numpy as np
from scipy.stats import rankdata


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rho(pred, truth):
    a, b = rankdata(pred, method='average'), rankdata(truth, method='average')
    assert len(a) == len(b) and np.isfinite(a).all() and np.isfinite(b).all()
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def summarize(records, root):
    root = Path(root)
    plan = json.loads((root / 'plan.json').read_text())
    grouped, detail = {}, []
    for record in records:
        year = record['outer_year']
        truth_path = root / 'scoring' / f'{year}.npz'
        assert sha(truth_path) == plan['scoring'][str(year)]['sha256']
        with np.load(truth_path, allow_pickle=False) as t:
            assert record['query_pids'] == t['pid'].tolist()
            truth, mask = t['legacy_truth'], t['observed_truth_mask']
        assert mask.dtype == bool and mask.any()
        vectors, family_counts = {}, {}
        for result in record['seed_results']:
            seed = result['seed']
            assert seed in plan['seeds']
            for name, vector in result['architectures'].items():
                vectors.setdefault(name, {})[seed] = np.asarray(vector, dtype=float)
                count = int((np.asarray(result['meta']['weights']) > 1e-8).sum()) if name == 'learned_global_nonnegative_meta' else 3 if name == 'equal_three_direct' else 2
                family_counts[(name, seed)] = count
            for family, member in result['members'].items():
                vectors.setdefault('control_' + family, {})[seed] = np.asarray(member['canonical_predictions'], dtype=float)
                family_counts[('control_' + family, seed)] = 1
            vectors.setdefault('control_residual_xgb_tabicl', {})[seed] = np.asarray(result['residual']['corrected_query_prediction'], dtype=float)
            family_counts[('control_residual_xgb_tabicl', seed)] = 2
        for name, seeds in vectors.items():
            assert sorted(seeds) == plan['seeds']
            for vector in seeds.values():
                assert vector.shape == truth.shape and np.isfinite(vector).all()
            # Fixed averaging of each completed architecture's seed ranks. No fitting here.
            seeds['fixed_three_seed_rank_average'] = sum(
                np.rint(2 * rankdata(seeds[s], method='average')).astype(np.int64)
                for s in plan['seeds']) / (2 * len(truth) * len(plan['seeds']))
            key = (record['panel_id'], record['policy_id'], name)
            for seed, vector in seeds.items():
                row = {'panel_id': key[0], 'policy_id': key[1], 'architecture': name,
                       'seed': seed, 'year': year, 'n_full': len(truth), 'n_observed': int(mask.sum()),
                       'contributing_families_at_least': family_counts.get((name, seed)),
                       'full': rho(vector, truth), 'observed': rho(vector[mask], truth[mask]),
                       'query_pids': record['query_pids'], 'prediction': vector.tolist()}
                grouped.setdefault(key, []).append(row)
                detail.append(row)
    summaries = []
    for (panel, policy, name), rows in grouped.items():
        if {r['year'] for r in rows} != set(plan['outer_years']):
            continue
        repeated = [r for r in rows if isinstance(r['seed'], int)]
        fixed = [r for r in rows if isinstance(r['seed'], str)]
        assert len(repeated) == 9 and len(fixed) == 3
        item = {'panel_id': panel, 'policy_id': policy, 'architecture': name,
                'member_control': name.startswith('control_'), 'diagnostic_only': True,
                'no_automatic_promotion': True, 'primary_mode': 'mean_three_seed_full_pool_Spearman',
                'multi_family_every_fold_seed': all(r['contributing_families_at_least'] >= 2 for r in repeated),
                'folds': sorted(plan['outer_years'])}
        for metric in ['full', 'observed']:
            item[metric] = {'mean_score': float(np.mean([r[metric] for r in repeated])),
                'fold_scores': {str(y): float(np.mean([r[metric] for r in repeated if r['year'] == y])) for y in plan['outer_years']},
                'seed_scores': {str(s): float(np.mean([r[metric] for r in repeated if r['seed'] == s])) for s in plan['seeds']},
                'fixed_three_seed_rank_average': float(np.mean([r[metric] for r in fixed]))}
        summaries.append(item)
    summaries.sort(key=lambda x: (-x['full']['mean_score'], x['panel_id'], x['policy_id'], x['architecture']))
    stacks = [s for s in summaries if not s['member_control']]
    controls = [s for s in summaries if s['member_control']]
    ensembles = [s for s in stacks if s['multi_family_every_fold_seed']]
    # Paired differences use exactly the same outer folds and seeds.
    comparisons = []
    by_key = {(s['panel_id'], s['policy_id'], s['architecture']): s for s in summaries}
    for s in summaries:
        if s['panel_id'] != 'panel174':
            continue
        baseline = by_key.get(('panel44', s['policy_id'], s['architecture']))
        if baseline:
            comparisons.append({'policy_id': s['policy_id'], 'architecture': s['architecture'],
                'full_gain_174_minus_44': s['full']['mean_score'] - baseline['full']['mean_score'],
                'observed_gain_174_minus_44': s['observed']['mean_score'] - baseline['observed']['mean_score'],
                'full_fold_gains': {y: s['full']['fold_scores'][y] - baseline['full']['fold_scores'][y] for y in s['full']['fold_scores']}})
    return {'stack_summaries_oof': stacks, 'control_summaries_oof': controls,
            'best_oof_stack': stacks[0] if stacks else None,
            'best_actual_multifamily_stack': ensembles[0] if ensembles else None,
            'best_member_control': controls[0] if controls else None,
            'paired_panel_comparisons': comparisons,
            'scored_prediction_records': len(detail), 'prediction_details': detail,
            'full_pool_primary': True, 'subset_secondary': True,
            'selection_uses_2019_plus_outcomes': False}
