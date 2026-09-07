"""Independent, one-time scorer. Freeze ALL predictions before opening answers."""
from pathlib import Path
import argparse
import datetime
import fcntl
import hashlib
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

ROOT = Path('/home/ubuntu/nba/handoff/r9test')
OUT = ROOT / 'results'
VAULT = ROOT.parent / 'vault'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_new(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def policy():
    p = json.loads((ROOT / 'scoring_policy.json').read_text())
    assert p['years'] == list(range(2019, 2026)) and p['seeds'] == [0, 101, 202]
    return p


def freeze():
    assert not (OUT / 'prediction_freeze.json').exists()
    p = policy()
    approval = json.loads((ROOT / 'code/approval.json').read_text())
    assert approval['approved'] and approval['reference_gate_passed']
    assert sha(ROOT / 'code/frozen.json') == approval['frozen_code_sha256']
    assert sha(ROOT / 'code/recipe.json') == approval['recipe_sha256']
    assert approval['scoring_policy_sha256'] == sha(ROOT / 'scoring_policy.json')
    proofs = {}
    for year in p['years']:
        folder = OUT / str(year)
        done = json.loads((folder / 'completion.json').read_text())
        assert done['year'] == year and done['seeds'] == p['seeds']
        assert not done['scoring_performed']
        assert sha(folder / 'predictions.csv') == done['predictions_csv_sha256']
        assert sha(folder / 'predictions.json') == done['predictions_sha256']
        predictions = pd.read_csv(folder / 'predictions.csv', float_precision='round_trip')
        assert list(predictions) == ['pid', 'season', 'seed_0', 'seed_101', 'seed_202', 'score']
        assert predictions.pid.is_unique and predictions.season.eq(year).all()
        assert len(predictions) == done['rows']
        columns = [f'seed_{s}' for s in p['seeds']]
        assert np.isfinite(predictions[columns + ['score']].to_numpy()).all()
        ranks = [np.rint(2 * rankdata(predictions[c], method='average')).astype(np.int64) for c in columns]
        expected = np.sum(ranks, axis=0, dtype=np.int64) / (6 * len(predictions))
        assert np.array_equal(expected, predictions.score.to_numpy())
        audit = json.loads((folder / 'predictions.json').read_text())
        assert not audit['test_outcomes_accessed'] and not audit['evaluation_scores_computed']
        assert audit['recipe_sha256'] == approval['recipe_sha256']
        assert audit['frozen_code_sha256'] == approval['frozen_code_sha256']
        assert audit['input_manifest_sha256'] == approval['year_manifest_sha256'][str(year)]
        assert audit['audit']['actual_admitted_label_max'] <= year - 1
        assert audit['audit']['training_max_cohort'] < year
        proofs[str(year)] = {
            'predictions_csv_sha256': done['predictions_csv_sha256'],
            'predictions_json_sha256': done['predictions_sha256'],
            'completion_sha256': sha(folder / 'completion.json'),
            'rows': len(predictions),
            'training_rows': audit['audit']['training_rows'],
            'actual_admitted_label_max': audit['audit']['actual_admitted_label_max'],
            'source_export_label_max': audit['audit']['source_export_label_max'],
            'input_manifest_sha256': audit['input_manifest_sha256'],
        }
    record = {
        'frozen_at_utc': now(), 'all_seven_predictions_complete_before_answers': True,
        'scoring_policy_sha256': sha(ROOT / 'scoring_policy.json'),
        'scorer_sha256': sha(Path(__file__)),
        'approval_sha256': sha(ROOT / 'code/approval.json'),
        'frozen_code_sha256': approval['frozen_code_sha256'],
        'recipe_sha256': approval['recipe_sha256'], 'years': proofs,
    }
    write_new(OUT / 'prediction_freeze.json', record)
    print(json.dumps({'predictions_frozen': True, 'years': list(proofs),
                      'prediction_freeze_sha256': sha(OUT / 'prediction_freeze.json'),
                      'test_answers_opened': False}))


def correlation(a, b, minimum):
    if len(a) < minimum or len(np.unique(a)) < 2 or len(np.unique(b)) < 2:
        return None
    value = float(spearmanr(a, b).statistic)
    return value if np.isfinite(value) else None


def score():
    p = policy()
    f = json.loads((OUT / 'prediction_freeze.json').read_text())
    freeze_sha = sha(OUT / 'prediction_freeze.json')
    assert f['all_seven_predictions_complete_before_answers']
    assert f['scoring_policy_sha256'] == sha(ROOT / 'scoring_policy.json')
    assert f['scorer_sha256'] == sha(Path(__file__))
    assert f['approval_sha256'] == sha(ROOT / 'code/approval.json')
    assert set(f['years']) == {str(y) for y in p['years']}
    for y, proof in f['years'].items():
        assert sha(OUT / y / 'predictions.csv') == proof['predictions_csv_sha256']
        assert sha(OUT / y / 'predictions.json') == proof['predictions_json_sha256']
    ledger = VAULT / 'r9_frozen_benchmark_ledger.jsonl'
    with Path(str(ledger) + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lines = ledger.read_text().splitlines(keepends=True) if ledger.exists() else []
        previous = 'GENESIS'
        for line in lines:
            saved = json.loads(line)
            assert saved['prev'] == previous, 'Ledger chain changed'
            previous = hashlib.sha256(line.encode()).hexdigest()
            if saved['prediction_freeze_sha256'] == freeze_sha:
                if not (OUT / 'test_result.json').exists():
                    write_new(OUT / 'test_result.json', saved['result'])
                print(json.dumps(saved['result']))
                return
        assert not (OUT / 'test_result.json').exists(), 'Never overwrite a scored result'
        # No answers are opened before the complete prediction/hash checks above.
        pairs = []
        for year in p['years']:
            path = VAULT / f'answers_{year}.csv'
            k = p['horizons'][str(year)]
            truth_columns = [f'y_s{i}_war' for i in range(1, k + 1)]
            answers = pd.read_csv(path, usecols=['pid', 'actual_pick'] + truth_columns,
                                  float_precision='round_trip').dropna(subset=['actual_pick'])
            predictions = pd.read_csv(OUT / str(year) / 'predictions.csv', float_precision='round_trip')
            assert answers.pid.is_unique and predictions.pid.is_unique
            assert set(answers.pid) == set(predictions.pid), f'Full benchmark PID mismatch for{year}'
            joined = predictions.merge(answers, on='pid', validate='one_to_one', sort=False)
            assert joined.pid.tolist() == predictions.pid.tolist()
            values = joined[truth_columns].apply(pd.to_numeric, errors='raise').to_numpy(dtype=float)
            assert not np.isinf(values).any()
            pairs.append((year, k, joined, values, sha(path)))
        rows = []
        for year, k, joined, values, answer_sha in pairs:
            truth = np.nan_to_num(values, nan=0).sum(axis=1)
            observed = np.isfinite(values).all(axis=1)
            row = {'season': year, 'k': k, 'n_full': len(joined), 'n_complete_target': int(observed.sum()),
                   'partial_or_unknown_target_rows': int((~observed).sum()),
                   'answer_sha256': answer_sha, 'training': f['years'][str(year)]}
            for name, mask in [('full_legacy', np.ones(len(joined), dtype=bool)), ('complete_target_subset', observed)]:
                metrics = {col: correlation(joined[col].to_numpy()[mask], truth[mask], p['minimum_n_for_correlation'])
                           for col in ['score', 'seed_0', 'seed_101', 'seed_202']}
                metrics['draft'] = correlation(-joined.actual_pick.to_numpy()[mask], truth[mask], p['minimum_n_for_correlation'])
                seed_scores = [metrics[f'seed_{s}'] for s in p['seeds']]
                metrics['mean_seed_score'] = float(np.mean(seed_scores)) if all(x is not None for x in seed_scores) else None
                row[name] = metrics
            rows.append(row)
        aggregates = {}
        for name in ['full_legacy', 'complete_target_subset']:
            aggregates[name] = {}
            for metric in ['score', 'seed_0', 'seed_101', 'seed_202', 'draft', 'mean_seed_score']:
                values = [r[name][metric] for r in rows]
                aggregates[name][metric] = float(np.mean(values)) if all(x is not None for x in values) else None
            aggregates[name]['cohorts_with_defined_ensemble_correlation'] = sum(r[name]['score'] is not None for r in rows)
        result = {'protocol': p['protocol'], 'scored_at_utc': now(), 'prediction_freeze_sha256': freeze_sha,
                  'aggregation': 'Unweighted mean across all seven cohorts; no undefined cohort silently omitted',
                  'score_units': 'Spearman rho; multiply by100 for dashboard percent', 'rows': rows,
                  'aggregate': aggregates, 'limitations': p['limitations'],
                  'no_test_feedback_tuning': True, 'new_model_promotion': False}
        record = {'prev': previous, 'prediction_freeze_sha256': freeze_sha, 'result': result}
        line = json.dumps(record, allow_nan=False) + '\n'
        with ledger.open('a') as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        write_new(OUT / 'test_result.json', result)
        print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['freeze', 'score'])
    args = parser.parse_args()
    freeze() if args.action == 'freeze' else score()
