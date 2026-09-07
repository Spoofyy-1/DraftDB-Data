"""Finite software fixtures, no historical outcome scores or model-library fits."""
import collections
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

import stack_core as C
from model_backend import ridge_statistics, ridge_transform
import worker


class FakeBackend:
    def __init__(self):
        self.counts = collections.Counter()
        self.calls = []
        self.predictions = []

    def select(self, X, y, pids, stage):
        self.counts["selector"] += 1
        importance = np.abs(np.nan_to_num(np.asarray(X)).T @ y)
        selected = [c for _, c in sorted(zip(importance, X), reverse=True)[:100]]
        return selected, {"training_pid_hash": C.digest(pids), "training_target_hash": C.array_hash(y),
                          "training_matrix_hash": C.array_hash(X), "selected_columns": selected}

    def fit(self, family, X, y, seed, pids, stage):
        self.counts[family] += 1
        record = {"family": family, "seed": seed, "fields": list(X), "stage": stage,
                  "training_pid_hash": C.digest(pids), "training_target_hash": C.array_hash(y),
                  "coef": np.nan_to_num(np.asarray(X)).T @ y / len(y), "mean": float(np.mean(y))}
        self.calls.append({**record, "private_y": np.asarray(y).copy(), "pids": list(pids)})
        return record

    def predict(self, model, X):
        assert list(X) == model["fields"]
        array = np.nan_to_num(np.asarray(X))
        factor = {"ridge": .8, "tabicl": 1.2, "residual_q25": .3}[model["family"]]
        raw = array @ model["coef"] * factor + model["mean"] + model["seed"]*.00001*array[:, 0]
        self.predictions.append({"model": model, "X": X.copy(), "raw": raw.copy()})
        return raw, {k: v for k, v in model.items() if k != "coef"}


def fixture():
    rng = np.random.default_rng(72896)
    pids = [f"P_fixture_{i}" for i in range(90)]
    order = C.canonical_order(pids)
    pids = [pids[i] for i in order]
    cohorts = np.tile([2007, 2008, 2009], 30)[order]
    x = rng.normal(size=(90, 127))[order]
    x[rng.uniform(size=x.shape) < np.linspace(.01, .5, len(x))[:, None]] = np.nan
    values = 2*np.nan_to_num(x[:, 0]) + rng.normal(size=90)
    target = C.gaussian_target(values, cohorts)
    columns = json.loads((worker.CODE / "protocol.json").read_text())["columns"]
    queries = [f"Q_fixture_{i}" for i in range(8)]
    qo = C.canonical_order(queries)
    queries = [queries[i] for i in qo]
    q = np.vstack([np.ones(127)]*3 + [np.zeros(127), np.full(127, np.nan)]
                  + [rng.normal(size=127) for _ in range(3)])
    q[5, :45] = np.nan
    q[6, :25] = np.nan
    q = q[qo]
    X = pd.DataFrame(x, columns=columns)
    Q = pd.DataFrame(q, columns=columns)
    metadata = pd.DataFrame({"pid": pids, "draft_year": cohorts})
    audit = {"outer_year": 2012, "max_actual_label_season": 2011,
             "all_labels_finite_observed": True, "missing_training_labels_zero_filled": False,
             "training_pid_hash": C.digest(pids), "label_value_hash": C.array_hash(values),
             "target_hash": C.array_hash(target), "source_fact_hash": "synthetic-fixture-only"}
    return X, Q, metadata, queries, values, target, audit


def run(backend=None):
    X, Q, metadata, pids, values, target, audit = fixture()
    backend = backend or FakeBackend()
    return C.run_outer(X, Q, metadata, pids, values, target, 2012, backend,
                       label_audit=audit), backend


class RecoveredAdapterSafety(unittest.TestCase):
    def test_counts_seeds_residual_math_and_no_private_outputs(self):
        result, backend = run()
        self.assertEqual(dict(backend.counts), C.EXPECTED_FITS)
        self.assertEqual(sum(backend.counts.values()), 26)
        self.assertEqual(sorted(c["seed"] for c in backend.calls if c["family"] == "tabicl"),
                         sorted([42,143,244]*4))
        self.assertEqual(sorted(c["seed"] for c in backend.calls if c["family"] == "residual_q25"),
                         [11,12,13,112,113,114,213,214,215])
        X, Q, metadata, query_pids, values, target, audit = fixture()
        assignment = C.assignments(metadata.pid.tolist())
        for shift in C.SEEDS:
            oof = np.full(len(X), np.nan)
            for f in range(3):
                held = np.flatnonzero(assignment == f)
                record = next(r for r in backend.predictions if r["model"]["family"] == "tabicl"
                              and r["model"]["seed"] == 42+shift
                              and r["model"]["stage"] == f"outer2012_inner{f}")
                pids = metadata.pid.iloc[held].tolist()
                oof[held] = C.canonicalize(record["X"], record["raw"], pids)[0]
            expected = C.rank_percentile(target)-C.rank_percentile(oof)
            fitted = [r for r in backend.calls if r["family"] == "residual_q25"
                      and r["stage"] == f"outer2012_residual_shift{shift}"]
            self.assertEqual(len(fitted), 3)
            for record in fitted:
                np.testing.assert_array_equal(record["private_y"], expected)
            output = next(r for r in result["seed_results"] if r["seed_shift"] == shift)
            bags = output["members"]["hybrid"]["bags"]
            correction = np.mean([b["canonical_predictions"] for b in bags], axis=0)
            hybrid = C.rank_percentile(output["members"]["tabicl"]["canonical_predictions"]) + correction
            hybrid = C.canonicalize(Q, hybrid, query_pids)[0]
            np.testing.assert_array_equal(hybrid, output["members"]["hybrid"]["canonical_predictions"])
        self.assertEqual(len(result["prediction_sets"]), 4)
        for predictions in result["prediction_sets"].values():
            self.assertEqual(len(predictions), 6)
            for prediction in predictions.values():
                C.validate_equal_groups(Q, prediction)
                self.assertTrue(np.isfinite(prediction).all())
        worker.assert_public_boundary(result)
        json.dumps(result, allow_nan=False)

    def test_held_labels_cannot_change_inner_selector_or_fit(self):
        X, Q, m, p, v, y, a = fixture()
        original = C.run_outer(X, Q, m, p, v, y, 2012, FakeBackend(), label_audit=a)
        held = C.assignments(m.pid.tolist()) == 0
        changed_values = v.copy()
        changed_values[held] = np.linspace(-80, 80, int(held.sum()))
        changed_target = C.gaussian_target(changed_values, m.draft_year)
        changed_audit = {**a, "label_value_hash": C.array_hash(changed_values),
                         "target_hash": C.array_hash(changed_target)}
        changed = C.run_outer(X, Q, m, p, changed_values, changed_target, 2012,
                             FakeBackend(), label_audit=changed_audit)
        self.assertEqual(original["inner_stages"][0], changed["inner_stages"][0])

    def test_query_changes_cannot_change_training_fits_or_selector(self):
        X, Q, m, p, v, y, a = fixture()
        first_backend, changed_backend = FakeBackend(), FakeBackend()
        first = C.run_outer(X, Q, m, p, v, y, 2012, first_backend, label_audit=a)
        changed_query = Q * 1000000.
        changed = C.run_outer(X, changed_query, m, p, v, y, 2012, changed_backend, label_audit=a)
        self.assertEqual(first["inner_stages"], changed["inner_stages"])
        self.assertEqual(first["full_selector"], changed["full_selector"])
        for original_call, changed_call in zip(first_backend.calls, changed_backend.calls):
            for key in ["training_pid_hash", "training_target_hash", "seed", "family", "fields"]:
                self.assertEqual(original_call[key], changed_call[key])
            np.testing.assert_array_equal(original_call["coef"], changed_call["coef"])

    def test_fixed_weights_rank_blends_and_seed_averaging(self):
        members = {"tabicl": np.array([2,4,6,8]), "ridge": np.array([8,6,4,2]),
                   "hybrid": np.array([4,2,8,6])}
        thin = np.array([True, False, True, False])
        output, blends = C.architecture_predictions(members, 8, thin)
        np.testing.assert_array_equal(blends["recovered_gen11"], np.array([16,22,32,14])/32)
        np.testing.assert_array_equal(blends["prior_baseline"], np.array([24,18,24,26])/32)
        np.testing.assert_array_equal(blends["always_rich"], np.array([26,22,18,14])/32)
        self.assertEqual(output["prior_baseline"][0], output["prior_baseline"][2])
        seeds = [members, {name: np.roll(value,1) for name,value in members.items()},
                 {name: np.roll(value,2) for name,value in members.items()}]
        per_seed, fixed, audit = C.combine_seed_members(seeds, thin)
        means = {name: np.mean([C.rank_percentile(s[name]) for s in seeds], axis=0) for name in C.MEMBERS}
        expected = np.where(thin, means["hybrid"], .25*means["tabicl"]+.75*means["ridge"])
        np.testing.assert_allclose(audit["fixed_raw_architecture_blends"]["recovered_gen11"], expected)
        np.testing.assert_array_equal(fixed["recovered_gen11"], C.rank_percentile(expected))

    def test_training_coverage_normalization_and_degenerate_failure(self):
        train = np.vstack([np.r_[np.ones(k), np.full(10-k,np.nan)] for k in [4]*10+[8]*10])
        query = np.vstack([np.r_[np.ones(k), np.full(10-k,np.nan)] for k in [0,1,2,3]])
        thin, audit = C.coverage_routing(train, query)
        self.assertEqual(audit["training_q05"], .4)
        self.assertEqual(audit["training_q95"], .8)
        self.assertEqual(audit["normalized_query_coverage"], [0.,0.,0.,0.])
        self.assertFalse(thin.any())
        with self.assertRaises(AssertionError):
            C.coverage_routing(np.ones((50,10)), query)

    def test_ridge_training_mean_sample_std_and_missing(self):
        X = pd.DataFrame({"a":[0.,2.,np.nan,4.],"b":[np.nan]*4,"c":[7.]*4})
        mean, std = ridge_statistics(X)
        query = pd.DataFrame({"a":[1000000.,np.nan],"b":[4.,np.nan],"c":[9.,7.]})
        z = ridge_transform(query, mean, std)
        self.assertEqual(mean.a, 2.)
        self.assertEqual(std.a, 2.)
        np.testing.assert_array_equal(z.to_numpy(), [[499999.,0.,2.],[0.,0.,0.]])

    def test_cutoff_unknown_targets_overlap_and_private_fields_rejected(self):
        X, Q, m, p, v, y, a = fixture()
        for update in [{"max_actual_label_season":2012}, {"all_labels_finite_observed":False},
                       {"missing_training_labels_zero_filled":True}]:
            with self.assertRaises(AssertionError):
                C.run_outer(X,Q,m,p,v,y,2012,FakeBackend(),label_audit={**a,**update})
        bad = v.copy()
        bad[0] = np.nan
        with self.assertRaises(AssertionError):
            C.gaussian_target(bad,m.draft_year)
        p[0] = m.pid.iloc[0]
        with self.assertRaises(AssertionError):
            C.run_outer(X,Q,m,p,v,y,2012,FakeBackend(),label_audit=a)
        self.assertNotIn("query_labels",inspect.signature(C.run_outer).parameters)
        for name in ["training_target", "OOF_predictions", "actual_pick"]:
            with self.assertRaises(AssertionError):
                worker.assert_public_boundary({"nested":[{name:[1.,2.]}]})

    def test_canonicalization_and_zero_negative_targets(self):
        frame = pd.DataFrame({"a":[1.,1.,1.,2.]})
        canonical, audit = C.canonicalize(frame,[.1,.2,.3,.9],["a","b","c","d"])
        self.assertEqual(canonical[0],canonical[1])
        self.assertEqual(canonical[1],canonical[2])
        self.assertEqual(len(audit["duplicate_groups"]),1)
        C.validate_equal_groups(frame,canonical)
        values = np.array([-3.,0.,0.,7.])
        target = C.gaussian_target(values,np.ones(4))
        self.assertTrue(target[0] < target[1] == target[2] < target[3])
        self.assertEqual(C.array_hash(np.array([0.,np.nan])),C.array_hash(np.array([-0.,np.nan])))

    def test_worker_input_schema_and_season_hash_enforcement(self):
        X,Q,m,p,v,y,a = fixture()
        prefix = np.ones(len(X),dtype=np.int64)
        season = np.minimum(m.draft_year.to_numpy()+2,2011).astype(np.int64)
        a = {**a,"outer_year":2019,"max_actual_label_season":int(season.max()),
             "season_end_max_hash":C.array_hash(season),"prefix_length_hash":C.array_hash(prefix)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            def write(query_labels=False, bad_season=False):
                local_season = season.copy()
                if bad_season:
                    local_season[0] = 2019
                np.savez(path/"training.npz", X=X.to_numpy(),pid=np.array(m.pid.tolist()),
                         draft_year=m.draft_year.to_numpy(),label_value=v,y=y,prefix_length=prefix,
                         season_end_max=local_season)
                query = {"X":Q.to_numpy(),"pid":np.array(p)}
                if query_labels:
                    query["y"] = np.zeros(len(Q))
                np.savez(path/"inference.npz",**query)
                manifest = {"outer_year":2019,"target_mode":"prefix5","task_id":"prefix5_y2019",
                            "columns":list(X),"protocol_sha256":worker.sha(worker.CODE/"protocol.json"),
                            "label_audit":a,"files":{name:{"sha256":worker.sha(path/name)}
                            for name in ["training.npz","inference.npz"]}}
                (path/"manifest.json").write_text(json.dumps(manifest))
            write()
            worker.load(path)
            for options in [{"query_labels":True},{"bad_season":True}]:
                write(**options)
                with self.assertRaises(AssertionError):
                    worker.load(path)
            write()
            (path/"scoring.npz").write_bytes(b"forbidden")
            with self.assertRaises(AssertionError):
                worker.load(path)


if __name__ == "__main__":
    unittest.main()
