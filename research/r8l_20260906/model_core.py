"""Frozen TabICL predictor; receives only an eligible single-cutoff bundle."""
import os
import hashlib
import json

import numpy as np
import pandas as pd
import xgboost as xgb
import legacy_kernel as E


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def predict(training, inference, labels, legacy_features, incumbent, policy, year, horizon):
    cutoff = year - 1
    assert training.pid.is_unique and inference.pid.is_unique
    assert training.draft_year.lt(year).all() and inference.draft_year.eq(year).all()
    assert labels.season_end.le(cutoff).all()
    assert not labels.duplicated(['pid', 'ordinal']).any()
    assert not set(training.pid).intersection(inference.pid)
    assert 1 <= horizon <= 5
    cfg = policy['backbone']
    g = {**incumbent, 'noscout': 1, 'win': cfg['window'], 'hw': cfg['hw'],
         'M': cfg['M'], 'icl_n': cfg['icl_n']}
    assert not any(g.get(k) for k in ['beatpick', 'consres', 'gltb', 'midw', 'el', 'wk', 'pss', 'star', 'hurdle'])
    assert g['labelmix'] == 'single' and g['meta'] == 'rankavg'
    features = [c for c in legacy_features if not any(c.startswith(p) for p in cfg['drop'])]
    assert not any(c.startswith(('f50_', 'slot_')) for c in features)
    assert not any(c.startswith('y_') for c in inference.columns)
    extras = policy['features']
    assert len(extras) <= 2 and len(set(extras)) == len(extras)
    assert all(c.startswith('f50_') and 'control' not in c for c in extras)
    tr = training[training.draft_year.between(int(cfg['window']), cutoff - 1)].copy().reset_index(drop=True)
    te = inference.copy().reset_index(drop=True)
    assert len(tr) >= 80 and len(te)
    for frame in [tr, te]:
        frame.drop(columns=['actual_pick', 'actual_round', 'was_drafted', 'player_name', 'nba_id'], errors='ignore', inplace=True)
        for col in legacy_features:
            if col not in frame or any(col.startswith(p) for p in cfg['drop']):
                frame[col] = np.nan
    used = labels[labels.pid.isin(tr.pid)]
    for i in range(1, 6):
        tr[f'y_s{i}_war'] = tr.pid.map(used[used.ordinal.eq(i)].set_index('pid').war)
    E.setup(features)
    options = E.opts_of(g)
    base = E.H.cols_for(options)
    columns = E.cols_of(g, base)
    E.H.audit_features(columns)
    prior, quantiles = E.H.fit_prior(tr)
    atr = E.H.build(tr, prior, quantiles, options)
    ate = E.H.build(te, prior, quantiles, options)
    rates = [c for c in base if c.startswith(('col_', 'intl_')) and not c.startswith('col_gl_')]
    atr, ate = E.feat_tx(atr, ate, g['fx'], tr, te, rates)
    stats = E.stats_of(atr)
    atr, ate = E.add_feats(atr, g['fx'], stats), E.add_feats(ate, g['fx'], stats)
    target = E.label(tr, E.specs(g)[0], horizon)
    selector = xgb.XGBRegressor(max_depth=3, n_estimators=300, learning_rate=.05,
                               subsample=.8, colsample_bytree=.6, n_jobs=2,
                               device='cpu', tree_method='hist', random_state=11)
    selector.fit(atr[columns], target)
    selected = [c for _, c in sorted(zip(selector.feature_importances_, columns), reverse=True)[:cfg['topk']]]
    assert len(selected) == cfg['topk'] and len(set(selected)) == len(selected)
    atr, ate = atr[selected].copy(), ate[selected].copy()
    for index, feature in enumerate(extras):
        atr[f'slot_{index}'] = pd.to_numeric(tr[feature], errors='raise')
        ate[f'slot_{index}'] = pd.to_numeric(te[feature], errors='raise')
    E.H.audit_features(list(atr))
    assert list(atr) == list(ate)
    predictions = []
    for seed in policy['seeds']:
        os.environ['SEED_SHIFT'] = str(seed)
        values = E.H.predict('tabicl', atr, target, ate, E.cfg_of('tabicl', g, list(atr)))
        assert np.isfinite(values).all()
        predictions.append(np.asarray(values))
    # Fixed rank average across seeds, with no fitted stacking weights.
    ensemble = np.mean([pd.Series(p).rank(pct=True).to_numpy() for p in predictions], axis=0)
    return pd.DataFrame({'pid': te.pid, 'season': year, 'k': horizon, 'score': ensemble}), {
        'training_players': len(tr), 'inference_players': len(te),
        'permitted_label_season': cutoff, 'actual_label_max': int(used.season_end.max()),
        'training_pid_hash': digest(tr.pid.tolist()),
        'training_labels_hash': hashlib.sha256(np.asarray(target, dtype=np.float64).tobytes()).hexdigest(),
        'base_columns': selected, 'input_columns': list(atr),
        'base_columns_hash': digest(selected),
        'seed_prediction_hashes': [hashlib.sha256(p.tobytes()).hexdigest() for p in predictions],
        'seed_predictions': [p.tolist() for p in predictions],
    }
