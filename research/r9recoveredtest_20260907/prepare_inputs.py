"""Join separately verified labels to frozen127 predictors; no fitting/scoring.

Run on server. Private training arrays stay on server. Existing query inputs are
reconstructed exactly, but no old model outputs or benchmark truth are read.
"""
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
HANDOFF = Path("/home/ubuntu/nba/handoff")
FEATURES = HANDOFF / "r9stacktest_features/package"
LABELS = HANDOFF / "r9recoveredtest_labelprep/exports"
PREVIOUS = HANDOFF / "r9stacktest/bundles"
sys.path.insert(0, str(ROOT / "code"))
import stack_core as C
import worker

FEATURE_MANIFEST_SHA = "9ba8624cfe079fb1a91f80e0c10a662a0694f29ddafcf4f0e9bcfd3995c58225"
LABEL_MANIFEST_SHA = "331f9bc49028abe273a9e5dd805ea39ac03dd96cb9d3ba35810c1ca26234dc09"
LABEL_VERIFICATION_SHA = "7c440c6ca8c9d6709f84cdfcb64afa9709ed09283309452f2cfb09b272f00a6b"
SOURCES = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, expected):
    path = Path(path)
    expected = expected["sha256"] if isinstance(expected, dict) else expected
    actual = sha(path)
    assert actual == expected, f"Source changed: {path}"
    if str(path) in SOURCES:
        assert SOURCES[str(path)] == actual
    SOURCES[str(path)] = actual
    return path


def read_json_pinned(path, expected):
    return json.loads(pin(path, expected).read_text())


def save_bytes_new(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(raw)
    except FileExistsError:
        assert path.read_bytes() == raw, f"Immutable output conflict: {path}"


def save_npz_new(path, values):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **values)
    save_bytes_new(path, buffer.getvalue())


def main():
    protocol = json.loads((ROOT / "code/protocol.json").read_text())
    assert protocol["outer_years"] == list(range(2019, 2026))
    assert protocol["target_modes"] == ["prefix5"]
    assert protocol["primary_architecture"] == "recovered_gen11"
    assert protocol["primary_prediction_set"] == "family_seed_rank_average"
    assert protocol["distinct_jobs"] == 7 and protocol["new_fits"] == 182
    columns = protocol["columns"]
    package = read_json_pinned(FEATURES / "manifest.json", FEATURE_MANIFEST_SHA)
    exports = read_json_pinned(LABELS / "manifest.json", LABEL_MANIFEST_SHA)
    verification = read_json_pinned(LABELS / "verification.json", LABEL_VERIFICATION_SHA)
    assert verification["passed"] and verification["exports_verified"] == 7
    assert verification["query_metadata_files_verified"] == 7 and verification["source_hashes_unchanged"]
    assert verification["models_run"] == verification["predictions_scored"] == 0
    assert len(columns) == 127 and columns == package["columns127"]
    assert exports["query_outcomes_or_vault_or_scoring_opened"] is False
    assert exports["model_runs"] == exports["predictions_scored"] == 0
    assert len(exports["exports"]) == 7
    # All package output and upstream feature-source pins are verified without
    # interpreting any additional source columns or outcomes.
    for name, info in package["outputs"].items():
        assert Path(name).name == name
        pin(FEATURES / name, info)
    for name, info in package["source_files"].items():
        relative = Path(name)
        assert not relative.is_absolute() and ".." not in relative.parts
        source = HANDOFF / relative if relative.parts[0] == "r9k" else FEATURES.parent / relative
        pin(source, info)
    feature_frames = {}
    for tag in ["pre2019"] + [str(y) for y in protocol["outer_years"]]:
        name = f"features_{tag}.csv"
        info = package["outputs"][name]
        frame = pd.read_csv(FEATURES / name, dtype={"pid": str}, float_precision="round_trip")
        assert list(frame) == ["pid", "draft_year"] + columns == info["columns"]
        assert len(frame) == info["rows"] and frame.pid.is_unique
        assert C.array_hash(frame[columns]) == info["matrix_hash"]
        assert not np.isinf(frame[columns].to_numpy()).any()
        if tag == "pre2019":
            assert frame.draft_year.max() <= 2018
        else:
            assert frame.draft_year.eq(int(tag)).all()
        feature_frames[tag] = frame
    tasks = []
    for exported in exports["exports"]:
        year, mode = exported["year"], exported["mode"]
        assert year in protocol["outer_years"] and mode == "prefix5"
        task_id = f"prefix5_y{year}"
        source_dir = LABELS / exported["relative_path"]
        label_manifest = read_json_pinned(source_dir / "manifest.json", exported["manifest_sha256"])
        assert label_manifest["mode"] == mode and label_manifest["prediction_year"] == year
        assert label_manifest["cap"] == 5 and label_manifest["start_cohort"] == 2007
        assert label_manifest["all_labels_finite_observed"] and not label_manifest["missing_training_labels_zero_filled"]
        assert label_manifest["contiguous_observed_prefix"] and not label_manifest["query_truth_exported"]
        label_path = pin(source_dir / "training.npz", exported["training_npz_sha256"])
        assert sha(label_path) == label_manifest["training_npz_sha256"]
        with np.load(label_path, allow_pickle=False) as f:
            assert set(f.files) == {"pid", "draft_year", "label_value", "y", "prefix_length", "season_end_max"}
            labels = {k: f[k].copy() for k in f.files}
        original_labels = {k: value.copy() for k, value in labels.items()}
        assert len(labels["pid"]) == exported["rows"] == label_manifest["training_rows"]
        assert C.digest(labels["pid"].tolist()) == label_manifest["pid_hash"] == exported["pid_hash"]
        for key, expected in label_manifest["array_hashes"].items():
            assert C.array_hash(labels[key]) == expected
        prior_tags = ["pre2019"] + [str(y) for y in range(2019, year)]
        available = pd.concat([feature_frames[tag] for tag in prior_tags], ignore_index=True)
        assert available.pid.is_unique and available.draft_year.lt(year).all()
        indexed = available.set_index("pid", verify_integrity=True)
        assert set(labels["pid"]).issubset(indexed.index)
        selected = indexed.loc[labels["pid"].tolist()]
        assert selected.index.tolist() == labels["pid"].tolist()
        assert np.array_equal(selected.draft_year.to_numpy(), labels["draft_year"])
        training = {"X": selected[columns].to_numpy(dtype=np.float64), **labels}
        assert np.all(training["season_end_max"] <= year-1)
        assert np.all(training["draft_year"] < year)
        query_meta = exports["query_metadata"][str(year)]
        query_path = pin(LABELS / f"queries/{year}.npz", query_meta["query_npz_sha256"])
        with np.load(query_path, allow_pickle=False) as f:
            assert set(f.files) == {"pid", "draft_year"}
            query_pid = f["pid"].copy()
            assert np.all(f["draft_year"] == year)
        assert C.digest(query_pid.tolist()) == query_meta["pid_hash"] == label_manifest["query_pid_hash"]
        query_frame = feature_frames[str(year)].set_index("pid", verify_integrity=True).loc[query_pid.tolist()]
        assert query_frame.draft_year.eq(year).all() and len(query_frame) == query_meta["rows"]
        inference = {"X": query_frame[columns].to_numpy(dtype=np.float64), "pid": query_pid}
        previous_dir = PREVIOUS / str(year)
        previous_manifest = read_json_pinned(previous_dir / "manifest.json", exports["source_hashes"][str(previous_dir / "manifest.json")])
        assert previous_manifest["columns"] == columns and previous_manifest["year"] == year
        previous_path = pin(previous_dir / "inference.npz", exports["source_hashes"][str(previous_dir / "inference.npz")])
        assert sha(previous_path) == previous_manifest["files"]["inference.npz"]
        with np.load(previous_path, allow_pickle=False) as f:
            assert set(f.files) == {"X", "pid"}
            assert np.array_equal(f["pid"], inference["pid"])
            assert np.array_equal(f["X"], inference["X"], equal_nan=True)
        for key, original in original_labels.items():
            assert np.array_equal(training[key], original), f"Training label export changed: {key}"
        assert not set(training["pid"]) & set(inference["pid"])
        for key in ["pid"]:
            assert np.array_equal(C.canonical_order(training[key].tolist()), np.arange(len(training[key])))
            assert np.array_equal(C.canonical_order(inference[key].tolist()), np.arange(len(inference[key])))
        label_audit = {
            "outer_year": year, "max_actual_label_season": label_manifest["max_actual_label_season"],
            "all_labels_finite_observed": True, "missing_training_labels_zero_filled": False,
            "training_pid_hash": label_manifest["pid_hash"], "label_value_hash": label_manifest["array_hashes"]["label_value"],
            "target_hash": label_manifest["array_hashes"]["y"], "source_fact_hash": label_manifest["source_fact_hash"],
            "season_end_max_hash": label_manifest["array_hashes"]["season_end_max"],
            "prefix_length_hash": label_manifest["array_hashes"]["prefix_length"],
            "training_max_cohort": int(training["draft_year"].max()),
            "training_cohort_counts": label_manifest["cohort_counts"],
            "prefix_length_counts": label_manifest["prefix_length_counts"],
            "label_export_manifest_sha256": exported["manifest_sha256"],
            "calendar_audit": label_manifest["calendar_audit"],
        }
        out = ROOT / "inputs" / task_id
        save_npz_new(out / "training.npz", training)
        save_npz_new(out / "inference.npz", inference)
        manifest = {
            "task_id": task_id, "outer_year": year, "target_mode": mode, "columns": columns,
            "protocol_sha256": sha(ROOT / "code/protocol.json"),
            "files": {name: {"sha256": sha(out/name), "bytes": (out/name).stat().st_size}
                      for name in ["training.npz", "inference.npz"]},
            "label_audit": label_audit,
            "training_feature_matrix_hash": C.array_hash(training["X"]),
            "query_feature_matrix_hash": C.array_hash(inference["X"]),
            "query_pid_hash": C.digest(query_pid.tolist()),
            "source_label_arrays_exact": True, "source_query_arrays_exact": True,
            "feature_package_sha256": FEATURE_MANIFEST_SHA,
            "label_exports_sha256": LABEL_MANIFEST_SHA,
            "label_exports_verification_sha256": LABEL_VERIFICATION_SHA,
            "prior_training_feature_files": {str(FEATURES/f"features_{tag}.csv"): SOURCES[str(FEATURES/f"features_{tag}.csv")] for tag in prior_tags},
            "query_feature_file_sha256": SOURCES[str(FEATURES/f"features_{year}.csv")],
            "previous_query_file_sha256": sha(previous_path),
            "source_global_model_eligible": package["model_eligible"],
            "scoped_retrospective_diagnostic": True,
            "query_truth_accessed": False,
        }
        worker.assert_public_boundary(manifest)
        worker.save_new(out / "manifest.json", manifest)
        # Production loader checks target arithmetic and all model-side cutoffs,
        # but runtime checks and actual constructors wait for isolated preflight.
        worker.load(out)
        tasks.append({"id": task_id, "year": year, "target_mode": mode,
                      "input_manifest_sha256": sha(out/"manifest.json"),
                      "training_rows": len(training["pid"]), "query_rows": len(inference["pid"]),
                      "training_matrix_hash": C.array_hash(training["X"]),
                      "query_matrix_hash": C.array_hash(inference["X"]),
                      "query_pid_hash": C.digest(query_pid.tolist()),
                      "expected_model_fits": 26, "prior_query_exact": True,
                      "all_six_training_label_arrays_exact": True})
    assert [task["year"] for task in tasks] == list(range(2019,2026))
    assert all(sha(Path(path)) == expected for path, expected in SOURCES.items())
    result = {"status": "prepared_no_models_no_scores", "tasks": tasks,
              "source_pins": SOURCES, "source_pin_count": len(SOURCES),
              "protocol_sha256": sha(ROOT/"code/protocol.json"),
              "builder_sha256": sha(__file__),
              "code_files": {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/"code").iterdir()) if p.is_file()},
              "all7_query_arrays_exact_to_prior_stacktest": True,
              "all42_training_label_arrays_exact_to_verified_export": True,
              "all8_feature_matrices_exact_to_package": True,
              "all_source_pins_unchanged": True,
              "primary_architecture": "recovered_gen11", "primary_prediction_set": "family_seed_rank_average",
              "no_benchmark_selection": True, "actual_model_fits": 0, "benchmark_scores_computed": 0,
              "benchmark_outcomes_or_vault_opened": False,
              "private_training_data_server_only": True,
              "limitations": protocol["limitations"]}
    worker.save_new(ROOT/"inputs_manifest.json", result)
    print(json.dumps({"tasks": len(tasks), "training_rows": [t["training_rows"] for t in tasks],
                      "source_pins": len(SOURCES), "query_arrays_exact": True,
                      "inputs_manifest_sha256": sha(ROOT/"inputs_manifest.json")}))


if __name__ == "__main__":
    main()
