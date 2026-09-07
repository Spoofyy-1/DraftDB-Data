"""Verify existing fixed benchmark records and archive only an explicit allowlist.

Never calls a model fit, scorer or opens benchmark answer files. Existing saved
score summaries and the append-only ledger are inspected, never recomputed from
answers. Every raw worker result is archived byte-for-byte after boundary checks.
"""
import collections
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tarfile

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
ROOT = Path("/home/ubuntu/nba/handoff/r9recoveredtest")
sys.path.insert(0, str(ROOT))
import verify as V

RESULT_SHA = "14109ccac4ea4366b638e3dfd027d3fb0465aaab68b69ee633fe17d95557841e"
PREDICTION_FREEZE_SHA = "9f5beaf2c3209383cce4dc525910d8a97521a4b7cf5032788e3a50f1d97548eb"
FROZEN_SHA = "4ab620fa8a95c88e043ed1c37b2f53086b7ba9c732d3fea9aed803e0def56bf5"
LAUNCH_SNAPSHOT_SHA = "82b4bdafb1c629e0fbd294dc1cd4c4031c1f18d971c6e6c2a2055a625dde4586"
MODES = ["per_seed_0", "per_seed_101", "per_seed_202", "family_seed_rank_average"]
RECIPES = ["recovered_gen11", "prior_baseline", "always_rich", "individual_tabicl", "individual_ridge", "individual_hybrid"]
SCOPES = ["full_legacy", "complete_target_subset"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def save_new(path, value):
    path = Path(path)
    raw = (json.dumps(value,indent=2,allow_nan=False)+"\n").encode()
    path.parent.mkdir(exist_ok=True,parents=True)
    with path.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def same_mean(values, saved):
    if any(value is None for value in values):
        assert saved is None
        return 0.
    assert len(values) and np.isfinite(values).all() and all(-1 <= x <= 1 for x in values)
    expected = math.fsum(values)/len(values)
    error = abs(expected-saved)
    assert error <= 3e-16, (expected,saved,error)
    return error


def canonical_prediction(frame, values):
    values = np.asarray(values,dtype=float)
    groups = collections.defaultdict(list)
    for i,row in enumerate(np.asarray(frame,dtype=float)):
        key = tuple(None if np.isnan(x) else float(x) for x in row)
        groups[key].append(i)
    output = values.copy()
    for indices in groups.values():
        if len(indices) > 1:
            output[indices] = math.fsum(sorted(float(values[i]) for i in indices))/len(indices)
    return output


def verify_query_member_math(record, matrix, columns):
    verified = 0
    for seed in record["seed_results"]:
        for family in ["tabicl", "ridge"]:
            member = seed["members"][family]
            selected = member["model_audit"]["input_columns"]
            indices = [columns.index(c) for c in selected]
            actual = canonical_prediction(matrix[:,indices],member["raw_predictions"])
            assert np.array_equal(actual,member["canonical_predictions"])
            verified += 1
        hybrid = seed["members"]["hybrid"]
        for bag in hybrid["bags"]:
            actual = canonical_prediction(matrix,bag["raw_predictions"])
            assert np.array_equal(actual,bag["canonical_predictions"])
            verified += 1
        mean_raw = np.mean([b["raw_predictions"] for b in hybrid["bags"]],axis=0)
        mean_canonical = np.mean([b["canonical_predictions"] for b in hybrid["bags"]],axis=0)
        assert np.array_equal(mean_raw,hybrid["mean_raw_query_correction"])
        assert np.array_equal(mean_canonical,hybrid["mean_canonical_query_correction"])
        tab_rank = rankdata(seed["members"]["tabicl"]["canonical_predictions"],method="average")/len(matrix)
        assert np.array_equal(tab_rank+mean_raw,hybrid["raw_predictions"])
        assert np.array_equal(canonical_prediction(matrix,tab_rank+mean_canonical),hybrid["canonical_predictions"])
        verified += 3
    return verified


FORBIDDEN_KEYS = {"label_value", "label_values", "y", "truth", "query_labels", "test_labels",
                  "training_target", "training_targets", "residual_target", "OOF_predictions",
                  "training_pids", "train_pids", "held_pids", "actual_pick", "eligible_label_facts"}
SECRET = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9]{20,}|(?i:bearer)\s+[A-Za-z0-9._-]{20,}")


def public_boundary(value, anonymous_pids):
    if isinstance(value,dict):
        forbidden = set(value)&FORBIDDEN_KEYS
        # The frozen protocol declares this exact formula as text. It is not a
        # training-vector field; all arrays or other values under this key fail.
        if isinstance(value.get("residual_target"), str) and value["residual_target"] in {
            "pct_rank(outer target)-pct_rank(OOF TabICL)",
            "rank_pct(transformed y)-rank_pct(3fold TabICL OOF raw prediction)",
        }:
            forbidden.discard("residual_target")
        assert not forbidden, forbidden
        assert not any(re.fullmatch(r"y_s\d+_(war|minutes)",str(key)) for key in value)
        for key,item in value.items():
            if key in {"pids","query_pids","outer_query_pids"}:
                assert isinstance(item,list) and all(x in anonymous_pids for x in item)
            public_boundary(item,anonymous_pids)
    elif isinstance(value,list):
        for item in value:
            public_boundary(item,anonymous_pids)
    elif isinstance(value,float):
        assert np.isfinite(value)
    elif isinstance(value,str):
        assert not SECRET.search(value)


def main():
    assert sha(ROOT/"results/test_result.json") == RESULT_SHA
    assert sha(ROOT/"results/prediction_freeze.json") == PREDICTION_FREEZE_SHA
    assert sha(ROOT/"frozen.json") == FROZEN_SHA
    assert sha(HERE/"launch_snapshot.json") == LAUNCH_SNAPSHOT_SHA
    plan = V.pins(ROOT)
    frozen = read(ROOT/"frozen.json")
    assert len(frozen["files"]) == 61
    authorization = read(ROOT/"launch_authorization.json")
    assert authorization["jobs"] == 7 and authorization["fits"] == 182 and authorization["workers"] == 4
    assert not authorization["automatic_retry"] and not authorization["benchmark_model_selection_allowed"]
    assert authorization["all_predictions_required_before_answers"]
    snapshot = read(HERE/"launch_snapshot.json")
    assert snapshot["unit"] == "draftdb-r9recoveredtest-20260907"
    assert snapshot["state"]["status"] == "predicting" and snapshot["state"]["active_workers"] == 4
    assert snapshot["state"]["model_fits_registered"] == 182 and not snapshot["state"]["test_scores_read"]
    input_manifest = read(ROOT/"inputs_manifest.json")
    assert len(input_manifest["source_pins"]) == 104
    for name,expected in input_manifest["source_pins"].items():
        assert sha(name) == expected, name
    freeze = read(ROOT/"results/prediction_freeze.json")
    result = read(ROOT/"results/test_result.json")
    completion = read(ROOT/"results/completion.json")
    assert freeze["all_seven_predictions_complete_before_answers"]
    assert freeze["plan_sha256"] == sha(ROOT/"plan.json")
    assert freeze["scorer_sha256"] == sha(ROOT/"score_frozen.py")
    assert freeze["frozen_sha256"] == FROZEN_SHA
    assert result["prediction_freeze_sha256"] == PREDICTION_FREEZE_SHA
    assert snapshot["time"] < freeze["frozen_at"] < result["scored_at"]
    assert completion["model_fits"] == 182 and completion["jobs"] == 7 and completion["status"] == "completed"
    assert completion["prediction_freeze_sha256"] == PREDICTION_FREEZE_SHA
    assert completion["test_result_sha256"] == RESULT_SHA
    assert completion["elapsed_seconds"] == 196.73080370598473
    completed = [json.loads(line) for line in (ROOT/"results/completed.jsonl").read_text().splitlines()]
    assert len(completed) == 7 and len({item["task_id"] for item in completed}) == 7
    assert {t["id"] for t in plan["tasks"]} == set(freeze["tasks"]) == {item["task_id"] for item in completed}
    jobs = []
    anonymous_pids = set()
    records = {}
    for task in plan["tasks"]:
        entry = freeze["tasks"][task["id"]]
        assert entry["file"] == f"jobs/{task['id']}/result.json"
        path = ROOT/"results"/entry["file"]
        assert sha(path) == entry["sha256"]
        assert path.stat().st_mtime <= freeze["frozen_at"]
        record = read(path)
        check = V.validate(record,task,ROOT)
        assert check == entry["verification"]
        assert next(x for x in completed if x["task_id"] == task["id"]) == entry
        with np.load(ROOT/"inputs"/task["id"]/"inference.npz",allow_pickle=False) as f:
            pids = f["pid"].tolist()
            matrix = f["X"].copy()
        assert all(re.fullmatch(r"[A-Za-z0-9_:-]{1,32}",p) and any(c.isdigit() for c in p) for p in pids)
        anonymous_pids.update(pids)
        arithmetic_count = verify_query_member_math(record,matrix,record["columns"])
        assert arithmetic_count == 24
        records[task["year"]] = record
        jobs.append({**check,"task_id":task["id"],"result_sha256":sha(path),
                     "query_pid_hash":canonical_hash(pids),"query_member_arithmetic_checks":arithmetic_count,
                     "result_mtime":path.stat().st_mtime,"prediction_freeze_time":freeze["frozen_at"]})
    assert [r["season"] for r in result["rows"]] == list(range(2019,2026))
    previous = read(ROOT/"previous_test_result.json")
    previous_rows = {r["season"]:r for r in previous["rows"]}
    for row in result["rows"]:
        year = row["season"]
        record = records[year]
        assert row["n_full"] == len(record["query_pids"])
        assert row["training_rows"] == record["training_rows"]
        assert row["actual_label_max"] == record["label_audit"]["max_actual_label_season"] <= year-1
        assert row["k"] == plan["horizons"][str(year)]
        assert row["answer_sha256"] == plan["answer_hashes"][str(year)]
        assert 0 <= row["n_complete_target"] <= row["n_full"]
        for key in ["n_full","n_complete_target","k","answer_sha256"]:
            assert row[key] == previous_rows[year][key]
    errors = []
    for scope in SCOPES:
        for mode in MODES:
            for recipe in RECIPES:
                errors.append(same_mean([r["metrics"][scope]["predictions"][mode][recipe] for r in result["rows"]],
                                        result["aggregate"][scope]["predictions"][mode][recipe]))
        errors.append(same_mean([r["metrics"][scope]["draft"] for r in result["rows"]],
                               result["aggregate"][scope]["draft"]))
    assert result["primary_recipe"] == plan["primary_recipe"] == "recovered_gen11"
    assert result["primary_mode"] == plan["primary_mode"] == "family_seed_rank_average"
    primary_values = [r["metrics"]["full_legacy"]["predictions"][result["primary_mode"]][result["primary_recipe"]] for r in result["rows"]]
    errors.append(same_mean(primary_values,result["primary_score"]))
    errors.append(same_mean(primary_values[1:],result["matched_2020_2025_score"]))
    assert result["controls_diagnostic_not_selection"] and result["no_test_feedback_tuning"]
    assert not result["new_model_promotion"]
    ledger_path = ROOT.parent/"vault/r9_frozen_benchmark_ledger.jsonl"
    # Read ledger aggregates only. Never export ledger bytes or open answer files.
    ledger_before = sha(ledger_path)
    lines = ledger_path.read_text().splitlines(keepends=True)
    previous_hash = "GENESIS"
    matches = []
    for index,line in enumerate(lines):
        assert line.endswith("\n")
        item = json.loads(line)
        assert item["prev"] == previous_hash
        line_hash = hashlib.sha256(line.encode()).hexdigest()
        if item["prediction_freeze_sha256"] == PREDICTION_FREEZE_SHA:
            assert item["result"] == result
            matches.append({"zero_based_index":index,"line_sha256":line_hash,
                            "previous_line_sha256":previous_hash,
                            "matching_result_canonical_sha256":canonical_hash(item["result"])})
        previous_hash = line_hash
    assert len(matches) == 1 and sha(ledger_path) == ledger_before
    for record in records.values():
        public_boundary(record,anonymous_pids)
    proof = {"passed":True,"frozen_files_verified":61,"source_pins_verified":104,
             "jobs_verified":7,"model_fit_audits_verified":182,
             "blend_vectors_reconstructed":168,"query_member_arithmetic_checks":168,
             "saved_aggregate_mean_checks":len(errors),"maximum_mean_arithmetic_error":max(errors),
             "all_prediction_files_frozen_before_scoring":True,
             "all_query_counts_and_complete_subset_counts_match_previous_frozen_benchmark":True,
             "all_worker_records_pass_recursive_public_boundary":True,
             "jobs":jobs,"prediction_freeze_sha256":PREDICTION_FREEZE_SHA,"test_result_sha256":RESULT_SHA,
             "frozen_sha256":FROZEN_SHA,"launch_authorization_sha256":sha(ROOT/"launch_authorization.json"),
             "launch_snapshot_sha256":LAUNCH_SNAPSHOT_SHA,
             "completion_sha256":sha(ROOT/"results/completion.json"),
             "primary_score":result["primary_score"],"matched_2020_2025_score":result["matched_2020_2025_score"],
             "primary_per_year":[{"year":r["season"],"n_full":r["n_full"],"n_complete_target":r["n_complete_target"],
                                  "rho":primary_values[i]} for i,r in enumerate(result["rows"])],
             "ledger":{"entries":len(lines),"hash_chain_passed":True,"exactly_one_matching_entry":True,
                         "ledger_sha256":ledger_before,"matching_entry":matches[0],"raw_ledger_exported":False},
             "verification_script_sha256":sha(__file__),
             "new_model_fits":0,"new_scores_computed":0,"raw_answer_files_opened":False,
             "private_training_arrays_exported":False,"no_model_or_recipe_selection":True,
             "interpretation":"Verification of existing fixed diagnostic records and saved aggregate arithmetic; no fresh holdout or retrospective-vintage certification."}
    save_new(HERE/"independent_verification.json",proof)
    root_files = [
        "results/test_result.json","results/prediction_freeze.json","results/completion.json",
        "results/completed.jsonl","results/state.json","results/cpu_preflight.json",
        "plan.json","launch_authorization.json","frozen.json","inputs_manifest.json","archived_recipe.json",
        "verify.py","score_frozen.py","research.py","run_task_sandbox.sh","prepare_inputs.py","cpu_preflight.py",
        "cpu_fixture_proof.json","controller_fixture_proof.json","legacy_AUDIT.md","README.md","previous_test_result.json",
        "code/model_backend.py","code/stack_core.py","code/worker.py","code/test_o.py","code/protocol.json","code/runtime_support.json",
    ]
    for task in plan["tasks"]:
        root_files.extend([f"results/jobs/{task['id']}/{name}" for name in ["result.json","worker.log","preflight.json","preflight_log.json"]])
        root_files.append(f"inputs/{task['id']}/manifest.json")
    sources = {name:ROOT/name for name in root_files}
    sources.update({f"verification/{name}":HERE/name for name in ["independent_verification.json","verify_and_archive.py","launch_snapshot.json"]})
    assert len(sources) == len(root_files)+3
    member_info = {}
    for name,path in sorted(sources.items()):
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert path.is_file() and not path.is_symlink()
        assert path.suffix in {".json",".jsonl",".py",".sh",".md",".log"}
        assert path.suffix != ".npz" and "vault" not in Path(name).parts and "eligible_label_facts" not in name
        raw = path.read_bytes()
        text = raw.decode()
        assert not SECRET.search(text), name
        if path.suffix == ".json":
            public_boundary(json.loads(text),anonymous_pids)
        elif path.suffix == ".jsonl":
            for line in text.splitlines():
                public_boundary(json.loads(line),anonymous_pids)
        elif path.suffix == ".log":
            assert "Traceback (most recent call last)" not in text
            for line in text.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                public_boundary(item,anonymous_pids)
        member_info[name] = {"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
    allowlist = {"policy":"Explicit hash allowlist; all raw seven worker records preserved verbatim. No NPZ, training targets, OOF/residual training arrays, raw label facts, identity names, vault files or ledger bytes.",
                 "files":member_info,"raw_worker_records":7,"recursive_boundary_passed":True}
    save_new(HERE/"PUBLIC_ALLOWLIST.json",allowlist)
    sources["PUBLIC_ALLOWLIST.json"] = HERE/"PUBLIC_ALLOWLIST.json"
    member_info = {name:{"sha256":sha(path),"bytes":path.stat().st_size} for name,path in sources.items()}
    archive = HERE/"r9recoveredtest_public_results.tar.gz"
    with archive.open("xb") as outer:
        with gzip.GzipFile(filename="",mode="wb",fileobj=outer,mtime=0) as gz:
            with tarfile.open(mode="w",fileobj=gz,format=tarfile.PAX_FORMAT) as tf:
                for name,path in sorted(sources.items()):
                    raw = path.read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == member_info[name]["sha256"]
                    header = tarfile.TarInfo(name)
                    header.size = len(raw)
                    header.mode = 0o644
                    header.mtime = 0
                    header.uid = header.gid = 0
                    header.uname = header.gname = ""
                    tf.addfile(header,io.BytesIO(raw))
    with tarfile.open(archive,"r:gz") as tf:
        members = tf.getmembers()
        assert len(members) == len(member_info) and len({m.name for m in members}) == len(members)
        assert {m.name for m in members} == set(member_info)
        for member in members:
            assert member.isfile() and not member.issym() and not member.islnk()
            raw = tf.extractfile(member).read()
            assert len(raw) == member_info[member.name]["bytes"] == member.size
            assert hashlib.sha256(raw).hexdigest() == member_info[member.name]["sha256"]
            assert raw == sources[member.name].read_bytes()
    # Recheck all source/output pins at end; no source mutations were permitted.
    V.pins(ROOT)
    assert sha(ROOT/"results/test_result.json") == RESULT_SHA and sha(ROOT/"results/prediction_freeze.json") == PREDICTION_FREEZE_SHA
    assert sha(ledger_path) == ledger_before
    archive_proof = {"passed":True,"archive":archive.name,"archive_sha256":sha(archive),
                     "archive_bytes":archive.stat().st_size,"members":member_info,
                     "member_count":len(member_info),"uncompressed_bytes":sum(x["bytes"] for x in member_info.values()),
                     "lossless_roundtrip_all_members":True,"all7_raw_records_preserved":True,
                     "no_private_NPZ_or_fact_or_vault_files":True,"recursive_public_boundary_passed":True,
                     "allowlist_sha256":sha(HERE/"PUBLIC_ALLOWLIST.json"),
                     "verification_sha256":sha(HERE/"independent_verification.json"),
                     "no_commit_or_push":True}
    save_new(HERE/"archive_verification.json",archive_proof)
    print(json.dumps({"passed":True,"frozen_files":61,"jobs":7,"fit_audits":182,"blend_vectors":168,
                      "primary_score":proof["primary_score"],"matched_2020_2025_score":proof["matched_2020_2025_score"],
                      "verification_sha256":sha(HERE/"independent_verification.json"),
                      "archive_bytes":archive.stat().st_size,"archive_sha256":sha(archive),
                      "archive_members":len(member_info)}))


if __name__ == "__main__":
    main()
