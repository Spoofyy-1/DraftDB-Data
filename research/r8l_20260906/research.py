"""Single frozen cohort confirmation; no 2019+ files in this namespace."""
from pathlib import Path
import hashlib
import json
import time
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from model_core import predict

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(state):
    state['updated'] = time.time()
    tmp = OUT / 'state.tmp'
    tmp.write_text(json.dumps(state, indent=2, allow_nan=False))
    tmp.replace(OUT / 'state.json')


def main():
    policy = json.loads((ROOT / 'frozen_policy.json').read_text())
    assert not (OUT / 'prediction_freeze.json').exists(), 'Confirmation already frozen; do not rerun'
    for name, expected in {**policy['files'], **policy['code_files']}.items():
        assert sha(ROOT / name) == expected
    assert not Path('/home/ubuntu/nba/handoff/vault').exists()
    x = pd.read_csv(ROOT / 'data/features.csv')
    labels = pd.read_csv(ROOT / 'data/labels.csv')
    assert x.draft_year.max() <= 2018 and labels.season_end.max() <= 2018
    manifest = json.loads((ROOT / 'data/manifest.json').read_text())
    incumbent = json.loads((ROOT / 'data/incumbent.json').read_text())['champ']
    state = {'started': time.time(), 'status': 'running', 'phase': 'R8l · frozen cohort confirmation',
             'completed': 0, 'total': 6, 'workers': 1, 'candidates': [],
             'best_configuration': {'id': 'frozen_pair01', 'score': policy['selected_development_mean'], 'seeds': 3},
             'message': 'One fixed candidate and its fixed backbone reference. All predictions freeze before confirmation scoring.',
             'confirmation': None, 'test_result': None}
    write(state)
    outputs, audits = [], []
    for model in ['selected', 'reference']:
        current = {**policy, 'features': policy['features'] if model == 'selected' else []}
        for year in policy['folds']:
            state['current'] = f'{model} · class {year}'
            write(state)
            tr = x[x.draft_year < year].copy()
            te = x[(x.draft_year == year) & x.was_drafted.eq(1)].copy()
            used = labels[labels.season_end <= year - 1].copy()
            pred, audit = predict(tr, te, used, manifest['legacy_features'], incumbent,
                                  current, year, int(policy['horizons'][str(year)]))
            pred['model'] = model
            outputs.append(pred)
            audits.append({'model': model, 'year': year, **audit})
            state['completed'] += 1
            write(state)
    predictions = pd.concat(outputs, ignore_index=True)
    predictions.to_csv(OUT / 'predictions.csv', index=False)
    (OUT / 'prediction_audit.json').write_text(json.dumps(audits, indent=2))
    freeze = {'time': time.time(), 'prediction_sha256': sha(OUT / 'predictions.csv'),
              'policy_sha256': sha(ROOT / 'frozen_policy.json')}
    (OUT / 'prediction_freeze.json').write_text(json.dumps(freeze, indent=2))
    result = {}
    for model in ['selected', 'reference']:
        rows = []
        for year in policy['folds']:
            pred = predictions[predictions.model.eq(model) & predictions.season.eq(year)]
            k = int(policy['horizons'][str(year)])
            truth = labels[labels.season_end.le(2018) & labels.ordinal.le(k)].groupby('pid').war.sum()
            values = pred.pid.map(truth).fillna(0)
            picks = pred.pid.map(x.set_index('pid').actual_pick)
            audit = next(a for a in audits if a['model'] == model and a['year'] == year)
            rows.append({'season': year, 'k': k, 'n': len(pred), 'ntrain': audit['training_players'],
                         'cutoff': year - 1, 'stack': float(spearmanr(pred.score, values).statistic),
                         'draft': float(spearmanr(-picks, values).statistic)})
        result[model] = {'score': float(np.mean([r['stack'] for r in rows])), 'rows': rows}
    result['protocol'] = policy['protocol']
    result['freeze'] = freeze
    result['interpretation'] = 'Retrospective cohort-disjoint confirmation; selection used development outcomes through2018. Not an as-of2015 deployment or goal test.'
    (OUT / 'confirmation_result.json').write_text(json.dumps(result, indent=2))
    state.update(status='completed', current='Frozen confirmation complete', confirmation=result['selected'],
                 reference_confirmation=result['reference'], message=result['interpretation'])
    write(state)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
