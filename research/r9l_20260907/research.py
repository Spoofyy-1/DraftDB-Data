"""Four isolated GPU jobs at a time; only this coordinator can read dev truth."""
import os
os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
from pathlib import Path
import concurrent.futures as cf
import fcntl
import hashlib
import json
import subprocess
import time
import postprocess
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def verify_pins():
    auth = read(ROOT / 'launch_authorization.json')
    assert auth['model_fits_authorized']
    assert sha(ROOT / 'plan.json') == auth['plan_sha256']
    assert sha(ROOT / 'frozen.json') == auth['frozen_sha256']
    for name, digest in read(ROOT / 'frozen.json')['files'].items():
        assert sha(ROOT / name) == digest, name
    return auth


def validate(record, task):
    assert record['task_id'] == task['id'] and record['outer_year'] == task['outer_year']
    assert record['panel_id'] == task['panel_id'] and record['policy_id'] == task['policy_id']
    assert record['input_manifest_sha256'] == task['input_manifest_sha256']
    assert record['protocol_sha256'] == sha(ROOT / 'code/protocol.json')
    assert record['fit_counts'] == {'ridge_a30': 1, 'ridge_a300': 1, 'ridge_a3000': 1, 'tabicl': 3, 'catboost': 3}
    assert not record['query_outcome_labels_accessed'] and not record['learned_weights']
    assert sorted(r['seed'] for r in record['seed_results']) == [0, 101, 202]
    for result in record['seed_results']:
        assert set(result['architectures']) == {r['id'] for r in read(ROOT / 'plan.json')['architectures']}
        assert set(result['members']) == {'tabicl', 'ridge_a30', 'ridge_a300', 'ridge_a3000', 'catboost'}



def run(task):
    folder = OUT / 'jobs' / task['id']
    folder.mkdir(exist_ok=True, parents=True)
    with (folder / 'worker.log').open('ab') as log:
        subprocess.run(['/usr/bin/bash', str(ROOT / 'run_task_sandbox.sh'), task['id']],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
    path = folder / 'result.json'
    record = read(path)
    validate(record, task)
    return record, {'task_id': task['id'], 'file': str(path.relative_to(OUT)), 'sha256': sha(path)}


def main():
    OUT.mkdir(exist_ok=True)
    lock = (OUT / 'model_queue.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    auth = verify_pins()
    assert sha(OUT / 'cpu_preflight.json') == auth['cpu_preflight_sha256'] and read(OUT / 'cpu_preflight.json')['passed']
    plan = read(ROOT / 'plan.json')
    for name, study, status in [('research_queue.json', 'r9k', 'completed'), ('research_queue_next.json', 'r9l', 'running')]:
        path = ROOT.parent / name
        if path.exists():
            value = read(path)
            if value.get('study') == study:
                write(path, {**value, 'status': status, 'updated': time.time()})
    by_id = {t['id']: t for t in plan['tasks']}
    assert len(by_id) == 24
    log_path = OUT / 'completed.jsonl'
    completed, entries = {}, {}
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            entry = json.loads(line)
            tid = entry['task_id']
            assert tid in by_id and tid not in entries
            assert entry['file'] == f'jobs/{tid}/result.json'
            path = OUT / entry['file']
            assert sha(path) == entry['sha256']
            record = read(path)
            validate(record, by_id[tid])
            completed[tid], entries[tid] = record, entry
    def append(entry):
        with log_path.open('a') as f:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')
            f.flush()
            os.fsync(f.fileno())
    # Durable worker output may precede the log append if the coordinator was interrupted.
    for tid, task in by_id.items():
        path = OUT / 'jobs' / tid / 'result.json'
        if path.exists() and tid not in completed:
            record = read(path)
            validate(record, task)
            entry = {'task_id': tid, 'file': str(path.relative_to(OUT)), 'sha256': sha(path), 'recovered_after_publish': True}
            append(entry)
            completed[tid], entries[tid] = record, entry
    start = time.monotonic()
    pending = {}
    summary = postprocess.summarize(list(completed.values()), ROOT)
    def snapshot(status='running'):
        compact = {k: v for k, v in summary.items() if k != 'prediction_details'}
        best = compact['best_actual_multifamily_stack']
        state = {**compact, 'status': status, 'updated': time.time(), 'completed': len(completed), 'total': 24,
                 'phase': 'R9L feature families · TabICL, Ridge and CatBoost stacks',
                 'current': ' | '.join(t['id'] for t in pending.values()),
                 'workers': 4, 'active_workers': len(pending), 'candidates': [],
                 'message': 'Exact 44-column controls run first. Each job compares 38 fixed blends; the scorer is outside model workers.',
                 'model_fits_completed': 9 * len(completed), 'model_fits_registered': 216,
                 'elapsed_seconds': time.monotonic() - start, 'no_model_promotion': True,
                 'test_result': None, 'confirmation': None}
        if best:
            state['best_configuration'] = {'id': best['architecture'], 'score': best['full']['mean_score'], 'seeds': 3, 'kind': 'fixed_family_stack'}
        write(OUT / 'state.json', state)
    tasks = [t for t in plan['tasks'] if t['id'] not in completed]
    base_tasks = [t for t in tasks if t['panel_id'] == 'base44']
    tasks = [t for t in tasks if t['panel_id'] != 'base44']
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        if base_tasks:
            pending.update({pool.submit(run, task): task for task in base_tasks})
            snapshot()
            for future in cf.as_completed(list(pending)):
                task = pending.pop(future)
                record, entry = future.result()
                append(entry)
                completed[task['id']], entries[task['id']] = record, entry
                summary = postprocess.summarize(list(completed.values()), ROOT)
                snapshot()
        gate = postprocess.reference_gate(list(completed.values()), ROOT)
        assert gate['passed'] and gate['exact_member_fold_seed_vectors'] == 36
        write(OUT / 'reference_gate.json', gate)
        def refill():
            while tasks and len(pending) < 4:
                task = tasks.pop(0)
                pending[pool.submit(run, task)] = task
        refill()
        snapshot()
        while pending:
            ready, _ = cf.wait(pending, timeout=5, return_when=cf.FIRST_COMPLETED)
            for future in ready:
                task = pending.pop(future)
                record, entry = future.result()
                append(entry)
                completed[task['id']], entries[task['id']] = record, entry
                print(json.dumps({'completed': task['id'], 'count': len(completed)}), flush=True)
            refill()
            if ready:
                summary = postprocess.summarize(list(completed.values()), ROOT)
            snapshot()
    assert len(completed) == 24 and summary['scored_prediction_records'] == 4128
    verify_pins()
    write(OUT / 'stack_diagnostics.json', summary)
    write(OUT / 'result_manifest.json', {'tasks': entries, 'diagnostics_sha256': sha(OUT / 'stack_diagnostics.json'),
          'model_fits': 216, 'scoring_records': 4128, 'no_2019_plus_scoring': True})
    snapshot('completed')
    write(OUT / 'completion.json', {'status': 'completed', 'tasks': 24, 'model_fits': 216,
          'all_inputs_unchanged': True, 'no_model_promotion': True, 'result_manifest_sha256': sha(OUT / 'result_manifest.json')})


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        path = OUT / 'state.json'
        old = read(path) if path.exists() else {}
        write(path, {**old, 'status': 'failed', 'error': repr(error), 'active_workers': 0, 'updated': time.time()})
        raise
