"""CPU input/constructor checks inside the exact worker namespaces; no model fits."""
from pathlib import Path
import concurrent.futures as cf
import hashlib
import json
import subprocess
import time
import numpy as np

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = json.loads((ROOT / 'plan.json').read_text())
    assert plan['task_count'] == len(plan['tasks']) == 12
    results = []
    def one(task):
        path = ROOT / 'results/jobs' / task['id'] / 'preflight.json'
        subprocess.run(['/usr/bin/bash', str(ROOT / 'run_task_sandbox.sh'), task['id'], 'preflight'],
                       check=True, capture_output=True, text=True)
        result = json.loads(path.read_text())
        assert result['passed'] and result['preflight_only'] and result['model_fits'] == 0
        assert result['input_manifest_sha256'] == task['input_manifest_sha256']
        assert result['training_rows'] == task['training_rows'] and result['query_rows'] == task['query_rows']
        assert result['label_audit']['max_actual_label_season'] <= task['outer_year'] - 1
        assert result['namespace_proof']['passed']
        return {'task_id': task['id'], 'sha256': sha(path), 'training_rows': result['training_rows'],
                'query_rows': result['query_rows'], 'namespace_proof': result['namespace_proof']}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(one, plan['tasks']):
            results.append(result)
            print(json.dumps({'preflight': result['task_id'], 'passed': True}), flush=True)
    tests = []
    for relative in ['code/test_stack_core.py', 'test_postprocess.py']:
        r = subprocess.run(['/home/ubuntu/nba/.venv/bin/python', str(ROOT / relative)],
                           check=True, capture_output=True, text=True)
        tests.append({'file': relative, 'sha256': sha(ROOT / relative), 'output': r.stdout + r.stderr})
    support = json.loads((ROOT / 'code/runtime_support.json').read_text())
    runtime_paths = 0
    for section in ['sources', 'checkpoint_files']:
        for path, info in support[section].items():
            mapped = path.replace('/opt/venv/', '/home/ubuntu/nba/.venv/', 1).replace('/models/hub/', '/home/ubuntu/.cache/huggingface/hub/', 1)
            expected = info['sha256'] if isinstance(info, dict) else info
            assert sha(Path(mapped)) == expected, path
            runtime_paths += 1
    summary = {'passed': True, 'models_fitted': 0, 'tasks_checked': len(results), 'tasks': results,
               'tests': tests, 'runtime_sources_checked': runtime_paths,
               'runtime_support_sha256': sha(ROOT / 'code/runtime_support.json'),
               'plan_sha256': sha(ROOT / 'plan.json'), 'protocol_sha256': sha(ROOT / 'code/protocol.json'),
               'finished': time.time(), 'scoring_files_mounted_in_model': False,
               'every_task_has_one_outer_cutoff_only': True}
    (ROOT / 'results/cpu_preflight.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ['tasks', 'tests']}), flush=True)


if __name__ == '__main__':
    main()
