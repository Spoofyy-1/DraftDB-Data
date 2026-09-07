"""CPU-only fixtures and seven isolated production-input preflights; never fits."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/"code"))
import worker


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs = json.loads((ROOT/"inputs_manifest.json").read_text())
    assert len(inputs["tasks"]) == 7
    source_before = {name: sha(Path(name)) for name in inputs["source_pins"]}
    assert source_before == inputs["source_pins"]
    code_before = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/"code").iterdir()) if p.is_file()}
    assert code_before == inputs["code_files"]
    assert sha(ROOT/"code/protocol.json") == inputs["protocol_sha256"]
    started = time.time()
    fixture = subprocess.run([sys.executable, str(ROOT/"code/test_o.py")], capture_output=True, text=True)
    assert fixture.returncode == 0, fixture.stderr
    assert "Ran 9 tests" in fixture.stderr and fixture.stderr.strip().endswith("OK")
    fixture_proof = {"passed": True, "tests": 9, "actual_model_fits": 0,
                     "benchmark_scores_computed": 0, "python": platform.python_version(),
                     "stdout": fixture.stdout, "stderr": fixture.stderr,
                     "code_files": code_before, "protocol_sha256": inputs["protocol_sha256"]}
    worker.save_new(ROOT/"cpu_fixture_proof.json", fixture_proof)

    def preflight(task):
        task_id = task["id"]
        assert sha(ROOT/"inputs"/task_id/"manifest.json") == task["input_manifest_sha256"]
        process = subprocess.run(["bash", str(ROOT/"run_task_sandbox.sh"), task_id, "preflight"],
                                 capture_output=True, text=True, timeout=600)
        out = ROOT/"results/jobs"/task_id
        worker.save_new(out/"preflight_log.json", {"returncode":process.returncode,
                                                 "stdout":process.stdout,"stderr":process.stderr})
        assert process.returncode == 0, f"{task_id}: {process.stderr}"
        path = out/"preflight.json"
        proof = json.loads(path.read_text())
        assert proof["passed"] and proof["preflight_only"] and proof["model_fits"] == 0
        assert proof["input_manifest_sha256"] == task["input_manifest_sha256"]
        assert proof["protocol_sha256"] == inputs["protocol_sha256"]
        assert proof["training_matrix_hash"] == task["training_matrix_hash"]
        assert proof["query_matrix_hash"] == task["query_matrix_hash"]
        assert proof["training_rows"] == task["training_rows"] and proof["query_rows"] == task["query_rows"]
        assert proof["runtime"]["support_sha256"] == sha(ROOT/"code/runtime_support.json")
        assert proof["namespace_proof"]["passed"]
        assert set(proof["namespace_proof"]["input_files"]) == {"training.npz", "inference.npz", "manifest.json"}
        assert proof["label_audit"]["max_actual_label_season"] <= task["year"]-1
        assert len(proof["constructor_checks"]) == 14
        return {"id":task_id,"year":task["year"],"passed":True,"model_fits":0,
                "preflight_sha256":sha(path),"preflight_log_sha256":sha(out/"preflight_log.json"),
                "input_manifest_sha256":task["input_manifest_sha256"],
                "training_rows":proof["training_rows"],"query_rows":proof["query_rows"],
                "inner_counts":proof["inner_counts"],"actual_label_max":proof["label_audit"]["max_actual_label_season"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        proofs = list(executor.map(preflight, inputs["tasks"]))
    assert all(sha(Path(name)) == expected for name, expected in source_before.items())
    assert {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/"code").iterdir()) if p.is_file()} == code_before
    result = {"passed":True,"tasks":proofs,"fixture_tests":9,"actual_model_fits":0,
              "benchmark_scores_computed":0,"concurrent_preflights":4,
              "all_source_pins_unchanged":True,"all_code_pins_unchanged":True,
              "all_model_namespaces_have_no_scoring_or_source_paths":True,
              "inputs_manifest_sha256":sha(ROOT/"inputs_manifest.json"),
              "protocol_sha256":inputs["protocol_sha256"],
              "runtime_support_sha256":sha(ROOT/"code/runtime_support.json"),
              "fixture_proof_sha256":sha(ROOT/"cpu_fixture_proof.json"),
              "preflight_script_sha256":sha(__file__),"sandbox_sha256":sha(ROOT/"run_task_sandbox.sh"),
              "seconds":time.time()-started}
    worker.save_new(ROOT/"results/cpu_preflight.json", result)
    print(json.dumps({"passed":True,"tasks":len(proofs),"fixture_tests":9,"actual_model_fits":0,
                      "seconds":result["seconds"],"proof_sha256":sha(ROOT/"results/cpu_preflight.json")}))


if __name__ == "__main__":
    main()
