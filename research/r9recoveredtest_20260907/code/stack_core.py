"""Recovered fixed-weight mechanisms on the frozen N127 numeric panel.

No scorer or query outcomes are accepted. This is not an exact legacy replay:
legacy features, unverified shrinkage, age constraints and RNG3 splits are absent.
"""
import collections
import hashlib
import json
import math

import numpy as np
import pandas as pd
from scipy.special import ndtri
from scipy.stats import rankdata

SEEDS = (0, 101, 202)
MEMBERS = ("tabicl", "ridge", "hybrid")
ARCHITECTURES = ("recovered_gen11", "prior_baseline", "always_rich")
EXPECTED_FITS = {"selector": 4, "ridge": 1, "tabicl": 12, "residual_q25": 9}


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def array_hash(value):
    array = np.asarray(value, dtype=np.float64)
    array = np.where(array == 0, 0, array)
    missing = np.isnan(array)
    return hashlib.sha256(
        json.dumps(list(array.shape), separators=(",", ":")).encode()
        + missing.tobytes() + np.where(missing, 0., array).tobytes()
    ).hexdigest()


def rank_twice(value):
    array = np.asarray(value, dtype=float)
    assert array.ndim == 1 and len(array) and np.isfinite(array).all()
    return np.rint(2 * rankdata(array, method="average")).astype(np.int64)


def rank_percentile(value):
    return rank_twice(value) / (2 * len(value))


def gaussian_target(label_values, cohorts):
    values = np.asarray(label_values, dtype=float)
    cohorts = np.asarray(cohorts)
    assert values.shape == cohorts.shape and np.isfinite(values).all()
    clipped = np.clip(values, -40., 40.)
    target = np.empty(len(values), dtype=float)
    for year in np.unique(cohorts):
        keep = cohorts == year
        q = (rankdata(clipped[keep], method="average") - .5) / int(keep.sum())
        target[keep] = ndtri(np.clip(q, .01, .99))
    return target


def canonical_order(pids):
    assert len(set(pids)) == len(pids) and all(isinstance(p, str) for p in pids)
    return np.array(sorted(range(len(pids)), key=lambda i: (
        hashlib.sha256(pids[i].encode()).hexdigest(), pids[i])), dtype=int)


def assignments(pids):
    """Three deterministic PID-hash inner splits, independent of targets/order."""
    return np.array([int(hashlib.sha256(p.encode()).hexdigest(), 16) % 3 for p in pids])


def vector_keys(frame):
    array = np.asarray(frame, dtype=float)
    assert array.ndim == 2 and not np.isinf(array).any()
    return [tuple(None if np.isnan(v) else ("0x0.0p+0" if v == 0 else float(v).hex())
                  for v in row) for row in array]


def canonicalize(frame, prediction, pids):
    raw = np.asarray(prediction, dtype=float)
    assert raw.shape == (len(frame),) and np.isfinite(raw).all() and len(pids) == len(raw)
    groups = collections.defaultdict(list)
    for index, key in enumerate(vector_keys(frame)):
        groups[key].append(index)
    result = raw.copy()
    duplicate = []
    for indices in groups.values():
        if len(indices) > 1:
            value = math.fsum(sorted(float(raw[i]) for i in indices)) / len(indices)
            result[indices] = value
            duplicate.append({"pids": [pids[i] for i in indices], "assigned": value,
                              "raw": [float(raw[i]) for i in indices]})
    return result, {"duplicate_groups": duplicate, "raw_hash": array_hash(raw),
                    "canonical_hash": array_hash(result),
                    "input_vector_hashes": [digest(k) for k in vector_keys(frame)]}


def validate_equal_groups(frame, prediction):
    seen = {}
    for key, value in zip(vector_keys(frame), prediction):
        if key in seen:
            assert value == seen[key]
        else:
            seen[key] = value


def coverage_routing(training, query):
    """Original fit-prior normalization, applied to the declared raw127 inputs."""
    raw_training = np.isfinite(np.asarray(training, dtype=float)).mean(axis=1)
    raw_query = np.isfinite(np.asarray(query, dtype=float)).mean(axis=1)
    low, high = np.quantile(raw_training, [.05, .95])
    assert np.isfinite(low) and np.isfinite(high) and high > low, \
        "Training coverage q95 must exceed q05; do not silently change routing"
    normalized = np.clip((raw_query - low) / (high - low), 0., 1.)
    median = float(np.median(normalized))
    thin = normalized < median
    return thin, {"training_coverage_hash": array_hash(raw_training),
                  "raw_query_coverage": raw_query.tolist(), "training_q05": float(low),
                  "training_q95": float(high), "normalized_query_coverage": normalized.tolist(),
                  "query_median": median, "query_thin_mask": thin.tolist(),
                  "definition": "raw127 finite share; training q05/q95 normalization then clipping; query strict-below-median",
                  "query_labels_used": False}


def architecture_predictions(rank_numerators, denominator, thin):
    """Exact integer quarter weights protect mathematical ties from round-off.

Input ranks have a common denominator. A seed-averaged input is the sum of
three rank numerators / (3*2*n); it is not re-ranked before the fixed blend.
The original architecture re-ranks the final routed blend.
"""
    assert set(rank_numerators) == set(MEMBERS)
    t, r, h = [np.asarray(rank_numerators[name], dtype=np.int64) for name in MEMBERS]
    thin = np.asarray(thin, dtype=bool)
    assert t.ndim == 1 and t.shape == r.shape == h.shape == thin.shape and denominator > 0
    rich = t + 3*r
    counts = {
        "recovered_gen11": np.where(thin, 4*h, rich),
        "prior_baseline": np.where(thin, 2*h + 2*r, 3*t + r),
        "always_rich": rich,
    }
    blends = {name: value / (4*denominator) for name, value in counts.items()}
    predictions = {name: rank_percentile(value) for name, value in counts.items()}
    predictions.update({"individual_" + name: value / denominator
                        for name, value in rank_numerators.items()})
    return predictions, blends


def combine_seed_members(seed_members, thin):
    assert len(seed_members) == 3
    rank_matrices = {
        name: np.vstack([rank_twice(item[name]) for item in seed_members]) for name in MEMBERS
    }
    n = len(thin)
    per_seed = []
    blends = []
    for i in range(3):
        pred, raw = architecture_predictions({name: rank_matrices[name][i] for name in MEMBERS}, 2*n, thin)
        per_seed.append(pred)
        blends.append(raw)
    numerators = {name: np.sum(rank_matrices[name], axis=0) for name in MEMBERS}
    fixed, fixed_blends = architecture_predictions(numerators, 6*n, thin)
    audit = {"family_order": list(MEMBERS), "twice_rank_matrices": {
        name: value.tolist() for name, value in rank_matrices.items()},
        "fixed_denominator": 6*n, "fixed_averaged_family_ranks": {
        name: (value/(6*n)).tolist() for name, value in numerators.items()},
        "seed_raw_architecture_blends": [{k: v.tolist() for k, v in x.items()} for x in blends],
        "fixed_raw_architecture_blends": {k: v.tolist() for k, v in fixed_blends.items()},
        "weights_fitted": False}
    return per_seed, fixed, audit


def validate_training_contract(X, query, metadata, query_pids, values, target,
                               outer_year, label_audit):
    assert list(metadata) == ["pid", "draft_year"] and list(X) == list(query)
    assert len(X) == len(metadata) and len(X) >= 40 and len(query) == len(query_pids) > 0
    assert len(set(X.columns)) == len(X.columns)
    assert not set(X) & {"pid", "draft_year", "actual_pick", "was_drafted", "qid"}
    pids = metadata.pid.tolist()
    assert np.array_equal(canonical_order(pids), np.arange(len(pids)))
    assert np.array_equal(canonical_order(query_pids), np.arange(len(query_pids)))
    assert not set(pids) & set(query_pids) and metadata.draft_year.lt(outer_year).all()
    assert label_audit is not None and label_audit["outer_year"] == outer_year
    assert label_audit["max_actual_label_season"] <= outer_year - 1
    assert label_audit["all_labels_finite_observed"] and not label_audit["missing_training_labels_zero_filled"]
    assert label_audit["training_pid_hash"] == digest(pids)
    assert label_audit["label_value_hash"] == array_hash(values)
    assert label_audit["target_hash"] == array_hash(target)
    assert np.array_equal(gaussian_target(values, metadata.draft_year), target)
    assert not np.isinf(np.asarray(X)).any() and not np.isinf(np.asarray(query)).any()
    return pids


def run_outer(X, query, metadata, query_pids, label_values, target, outer_year,
              backend, seeds=SEEDS, label_audit=None):
    """26 fits: 4 selectors + 12 TabICL + 1 Ridge + 9 residual XGBoost.

The three inner-fold targets and selectors are fitted without held-row labels.
Only hashes of training targets and OOF outputs are retained in the result.
"""
    assert tuple(seeds) == SEEDS
    pids = validate_training_contract(X, query, metadata, query_pids, label_values,
                                     target, outer_year, label_audit)
    thin, coverage = coverage_routing(X, query)
    source = (array_hash(X), array_hash(query), array_hash(target), array_hash(label_values))
    fold = assignments(pids)
    assert set(fold) == {0, 1, 2}
    oof = {shift: np.full(len(X), np.nan) for shift in seeds}
    inner = []
    for f in range(3):
        train, held = np.flatnonzero(fold != f), np.flatnonzero(fold == f)
        assert len(train) >= 20 and len(held) > 0
        train_pids, held_pids = [pids[i] for i in train], [pids[i] for i in held]
        xi = X.iloc[train].reset_index(drop=True)
        xh = X.iloc[held].reset_index(drop=True)
        yi = gaussian_target(np.asarray(label_values)[train], metadata.draft_year.to_numpy()[train])
        stage = f"outer{outer_year}_inner{f}"
        selected, selector = backend.select(xi, yi, train_pids, stage)
        assert len(selected) == min(100, len(X.columns)) and len(set(selected)) == len(selected)
        assert set(selected) <= set(X)
        records = []
        for shift in seeds:
            model = backend.fit("tabicl", xi[selected], yi, 42+shift, train_pids, stage)
            raw, audit = backend.predict(model, xh[selected])
            pred, ties = canonicalize(xh[selected], raw, held_pids)
            assert np.isnan(oof[shift][held]).all()
            oof[shift][held] = pred
            # OOF vectors are private training intermediates; export hashes only.
            records.append({"seed_shift": shift, "tabicl_seed": 42+shift,
                            "raw_prediction_hash": array_hash(raw),
                            "canonical_prediction_hash": array_hash(pred),
                            "model_audit": audit, "duplicate_group_count": len(ties["duplicate_groups"])})
        inner.append({"fold": f, "train_pid_hash": digest(train_pids),
                      "held_pid_hash": digest(held_pids), "train_rows": len(train), "held_rows": len(held),
                      "training_matrix_hash": array_hash(xi), "held_matrix_hash": array_hash(xh),
                      "training_target_hash": array_hash(yi),
                      "training_label_value_hash": array_hash(np.asarray(label_values)[train]),
                      "selector": selector, "selected_TabICL_columns": selected, "records": records})
    assert all(np.isfinite(v).all() for v in oof.values())
    stage = f"outer{outer_year}_full"
    selected, selector = backend.select(X, target, pids, stage)
    assert len(selected) == min(100, len(X.columns)) and len(set(selected)) == len(selected)
    assert set(selected) <= set(X)
    ridge = backend.fit("ridge", X, target, 0, pids, stage)
    ridge_raw, ridge_audit = backend.predict(ridge, query)
    ridge_pred, ridge_ties = canonicalize(query, ridge_raw, query_pids)
    results, seed_members = [], []
    for shift in seeds:
        tab = backend.fit("tabicl", X[selected], target, 42+shift, pids, stage)
        tab_raw, tab_audit = backend.predict(tab, query[selected])
        tab_pred, tab_ties = canonicalize(query[selected], tab_raw, query_pids)
        residual_target = rank_percentile(target) - rank_percentile(oof[shift])
        bag_raw, bag_canonical, bag_records = [], [], []
        for seed in (11+shift, 12+shift, 13+shift):
            model = backend.fit("residual_q25", X, residual_target, seed, pids,
                                f"outer{outer_year}_residual_shift{shift}")
            raw, audit = backend.predict(model, query)
            pred, ties = canonicalize(query, raw, query_pids)
            bag_raw.append(np.asarray(raw))
            bag_canonical.append(pred)
            bag_records.append({"seed": seed, "raw_predictions": np.asarray(raw).tolist(),
                                "canonical_predictions": pred.tolist(), "model_audit": audit,
                                "tie_audit": ties})
        delta_raw = np.mean(bag_raw, axis=0)
        delta = np.mean(bag_canonical, axis=0)
        hybrid_raw = rank_percentile(tab_pred) + delta_raw
        hybrid = rank_percentile(tab_pred) + delta
        hybrid, hybrid_ties = canonicalize(query, hybrid, query_pids)
        members = {"tabicl": tab_pred, "ridge": ridge_pred, "hybrid": hybrid}
        for pred in members.values():
            validate_equal_groups(query, pred)
        seed_members.append(members)
        results.append({"seed_shift": shift, "tabicl_seed": 42+shift,
                        "members": {
                            "tabicl": {"raw_predictions": np.asarray(tab_raw).tolist(),
                                       "canonical_predictions": tab_pred.tolist(), "model_audit": tab_audit,
                                       "tie_audit": tab_ties},
                            "ridge": {"raw_predictions": np.asarray(ridge_raw).tolist(),
                                      "canonical_predictions": ridge_pred.tolist(), "model_audit": ridge_audit,
                                      "tie_audit": ridge_ties, "shared_across_seeds": True},
                            "hybrid": {"raw_predictions": hybrid_raw.tolist(),
                                       "canonical_predictions": hybrid.tolist(), "tie_audit": hybrid_ties,
                                       "mean_canonical_query_correction": delta.tolist(),
                                       "mean_raw_query_correction": delta_raw.tolist(), "bags": bag_records,
                                       "training_target_hash": array_hash(residual_target),
                                       "OOF_TabICL_hash": array_hash(oof[shift]),
                                       "full_training_rank_target_hash": array_hash(rank_percentile(target)),
                                       "formula": "pct_rank(full TabICL query)+mean(3 XGB q25 corrections)",
                                       "training_targets_exported": False}}})
    per_seed, fixed, combination_audit = combine_seed_members(seed_members, thin)
    sets = {}
    for i, shift in enumerate(seeds):
        results[i]["architectures"] = {name: per_seed[i][name].tolist() for name in ARCHITECTURES}
        sets[f"per_seed_{shift}"] = {name: value.tolist() for name, value in per_seed[i].items()}
    sets["family_seed_rank_average"] = {name: value.tolist() for name, value in fixed.items()}
    for predictions in sets.values():
        for value in predictions.values():
            validate_equal_groups(query, value)
    assert source == (array_hash(X), array_hash(query), array_hash(target), array_hash(label_values))
    assert dict(backend.counts) == EXPECTED_FITS
    return {"outer_year": outer_year, "columns": list(X), "query_pids": query_pids,
            "training_pid_hash": digest(pids), "training_rows": len(X),
            "inner_assignment_hash": digest(dict(zip(pids, fold.tolist()))),
            "label_audit": label_audit, "inner_stages": inner,
            "full_selector": selector, "full_TabICL_columns": selected,
            "full_training_target_hash": array_hash(target), "coverage": coverage,
            "seed_results": results, "prediction_sets": sets, "combination_audit": combination_audit,
            "query_outcomes_accessed": False, "training_targets_exported": False,
            "weights_fitted": False, "fit_counts": dict(backend.counts)}
