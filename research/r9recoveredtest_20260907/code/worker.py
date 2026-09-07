"""Fixed recovered-gen11 benchmark worker; no scoring/outcomes namespace."""
import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

import numpy as np
import pandas as pd

import stack_core as C
from model_backend import Backend, ridge_statistics, ridge_transform

CODE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(directory):
    directory = Path(directory)
    assert {p.name for p in directory.iterdir()} == {"training.npz", "inference.npz", "manifest.json"}
    manifest = json.loads((directory / "manifest.json").read_text())
    protocol = json.loads((CODE / "protocol.json").read_text())
    year, mode, columns = manifest["outer_year"], manifest["target_mode"], manifest["columns"]
    assert year in protocol["outer_years"] and mode in protocol["target_modes"]
    assert manifest["task_id"] == f"{mode}_y{year}"
    assert protocol["seeds"] == [0, 101, 202] and protocol["fit_counts"] == C.EXPECTED_FITS
    assert len(columns) == 127 and columns == protocol["columns"] and len(set(columns)) == 127
    assert manifest["protocol_sha256"] == sha(CODE / "protocol.json")
    assert set(manifest["files"]) == {"training.npz", "inference.npz"}
    for name, info in manifest["files"].items():
        assert sha(directory / name) == info["sha256"]
    with np.load(directory / "training.npz", allow_pickle=False) as f:
        assert set(f.files) == {"X", "pid", "draft_year", "label_value", "y", "prefix_length", "season_end_max"}
        train = {k: f[k].copy() for k in f.files}
    with np.load(directory / "inference.npz", allow_pickle=False) as f:
        assert set(f.files) == {"X", "pid"}, "Query labels or metadata may not enter worker"
        query = {k: f[k].copy() for k in f.files}
    n, nq = len(train["pid"]), len(query["pid"])
    assert train["X"].shape == (n, 127) and query["X"].shape == (nq, 127)
    assert train["pid"].ndim == query["pid"].ndim == 1
    assert train["pid"].dtype.kind == query["pid"].dtype.kind == "U"
    assert all(train[k].shape == (n,) for k in ["draft_year", "label_value", "y", "prefix_length", "season_end_max"])
    assert n >= 40 and nq > 0
    for name in ["draft_year", "prefix_length", "season_end_max"]:
        assert train[name].dtype.kind in "iu"
    assert train["draft_year"].min() >= protocol["training_start_year"]
    assert mode == "prefix5"
    cap = 5
    assert 1 <= cap <= 5 and np.isin(train["prefix_length"], np.arange(1, cap+1)).all()
    assert np.all(train["season_end_max"] <= year-1)
    assert np.all(train["season_end_max"] >= train["draft_year"] + train["prefix_length"])
    audit = manifest["label_audit"]
    assert audit["max_actual_label_season"] == int(train["season_end_max"].max())
    assert audit["season_end_max_hash"] == C.array_hash(train["season_end_max"])
    assert audit["prefix_length_hash"] == C.array_hash(train["prefix_length"])
    assert audit["source_fact_hash"]
    X = pd.DataFrame(train["X"], columns=columns)
    Q = pd.DataFrame(query["X"], columns=columns)
    metadata = pd.DataFrame({"pid": train["pid"], "draft_year": train["draft_year"]})
    pids = C.validate_training_contract(X, Q, metadata, query["pid"].tolist(),
                                      train["label_value"], train["y"], year, audit)
    assignment = C.assignments(pids)
    assert set(assignment) == {0, 1, 2}
    for f in range(3):
        assert np.sum(assignment != f) >= 20 and np.sum(assignment == f) > 0
    C.coverage_routing(X, Q)
    return protocol, manifest, train, query


def runtime():
    path = CODE / "runtime_support.json"
    assert path.exists(), "Pinned runtime manifest required before any fitting"
    support = json.loads(path.read_text())
    assert support.get("sources") and support.get("checkpoint_files")
    for key in ["sources", "checkpoint_files"]:
        for name, info in support[key].items():
            assert sha(name) == (info["sha256"] if isinstance(info, dict) else info)
    return {"support_sha256": sha(path), "versions": support.get("versions", {})}


def save_new(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    path = Path(path)
    path.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(prefix="."+path.name+".", suffix=".tmp", dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            assert path.read_bytes() == raw, "Conflicting immutable worker output"
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def assert_public_boundary(value):
    """No training targets/OOF arrays may accidentally escape through audits."""
    forbidden = {"label_value", "label_values", "y", "training_target", "training_targets",
                 "OOF_predictions", "residual_target", "query_labels", "actual_pick"}
    if isinstance(value, dict):
        assert not set(value) & forbidden
        for item in value.values():
            assert_public_boundary(item)
    elif isinstance(value, list):
        for item in value:
            assert_public_boundary(item)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    assert Path(args.input_dir).resolve() == Path("/input")
    assert Path(args.output).resolve().parent == Path("/output")
    protocol, manifest, train, query = load(args.input_dir)
    inaccessible = ["/scoring", "/reference", "/source_records", "/h_reference", "/home", "/root", "/vault"]
    assert all(not Path(p).exists() for p in inaccessible), "Unexpected scoring or source access"
    namespace = {"input_files": sorted(p.name for p in Path(args.input_dir).iterdir()),
                 "inaccessible_paths": inaccessible, "passed": True}
    support = runtime()
    backend = Backend(protocol)
    X = pd.DataFrame(train["X"], columns=manifest["columns"])
    Q = pd.DataFrame(query["X"], columns=manifest["columns"])
    metadata = pd.DataFrame({"pid": train["pid"], "draft_year": train["draft_year"]})
    if args.preflight_only:
        constructors = []
        for family, seeds in [("selector", [11]), ("ridge", [0]),
                              ("tabicl", [42+s for s in protocol["seeds"]]),
                              ("residual_q25", [b+s for s in protocol["seeds"] for b in [11,12,13]])]:
            for seed in seeds:
                model, parameters = backend.constructor(family, seed)
                constructors.append({"family": family, "seed": seed, "parameters": parameters})
        mean, std = ridge_statistics(X)
        Z, Zq = ridge_transform(X, mean, std), ridge_transform(Q, mean, std)
        assert np.isfinite(np.asarray(Z)).all() and np.isfinite(np.asarray(Zq)).all()
        thin, coverage = C.coverage_routing(X, Q)
        proof = {"passed": True, "model_fits": 0, "preflight_only": True,
                 "task_id": manifest["task_id"], "outer_year": manifest["outer_year"],
                 "target_mode": manifest["target_mode"], "training_rows": len(X), "query_rows": len(Q),
                 "input_manifest_sha256": sha(Path(args.input_dir)/"manifest.json"),
                 "protocol_sha256": sha(CODE/"protocol.json"), "runtime": support,
                 "training_matrix_hash": C.array_hash(X), "query_matrix_hash": C.array_hash(Q),
                 "label_audit": manifest["label_audit"], "namespace_proof": namespace,
                 "constructor_checks": constructors, "coverage": coverage,
                 "inner_counts": [int(np.sum(C.assignments(train["pid"].tolist()) == f)) for f in range(3)],
                 "Ridge_standardized_training_hash": C.array_hash(Z),
                 "Ridge_standardized_query_hash": C.array_hash(Zq)}
        assert_public_boundary(proof)
        save_new(args.output, proof)
        print(json.dumps({"task_id": proof["task_id"], "passed": True, "model_fits": 0}))
        return
    started = time.time()
    result = C.run_outer(X, Q, metadata, query["pid"].tolist(), train["label_value"], train["y"],
                         manifest["outer_year"], backend, seeds=protocol["seeds"], label_audit=manifest["label_audit"])
    result.update(task_id=manifest["task_id"], target_mode=manifest["target_mode"],
                  input_manifest_sha256=sha(Path(args.input_dir)/"manifest.json"),
                  protocol_sha256=sha(CODE/"protocol.json"), runtime=support,
                  namespace_proof=namespace, seconds=time.time()-started,
                  query_outcome_labels_accessed=False)
    assert_public_boundary(result)
    save_new(args.output, result)
    print(json.dumps({"task_id": result["task_id"], "fit_counts": result["fit_counts"],
                      "seconds": result["seconds"], "output_sha256": sha(args.output)}))


if __name__ == "__main__":
    main()
