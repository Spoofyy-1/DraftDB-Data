"""Launch the frozen K study once J finishes cleanly. Never select from J scores."""
from pathlib import Path
import fcntl
import hashlib
import json
import subprocess
import time

ROOT = Path('/home/ubuntu/nba/handoff/r9k')
J = ROOT.parent / 'r9j'
OUT = ROOT / 'results'
UNIT = 'draftdb-r9k-20260907'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def unit_state(unit):
    result = subprocess.run(['systemctl', 'show', unit, '-p', 'ActiveState', '-p',
                             'Result', '-p', 'MainPID', '-p', 'ControlGroup'],
                            check=True, capture_output=True, text=True)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def verify_inputs(auth):
    assert sha(ROOT / 'plan.json') == auth['plan_sha256']
    assert sha(ROOT / 'frozen.json') == auth['frozen_sha256']
    for name, digest in read(ROOT / 'frozen.json')['files'].items():
        assert sha(ROOT / name) == digest, name
    assert sha(J / 'frozen.json') == auth['J_frozen_sha256']
    for name, digest in read(J / 'frozen.json')['files'].items():
        assert sha(J / name) == digest, name
    assert sha(OUT / 'cpu_preflight.json') == auth['cpu_preflight_sha256']
    assert read(OUT / 'cpu_preflight.json')['passed']


def verify_j():
    complete = read(J / 'results/completion.json')
    assert complete['status'] == 'completed' and complete['tasks'] == 48
    assert complete['reference_gate'] and complete['saved_stacks_complete']
    gate = read(J / 'results/reference_gate.json')
    assert gate['passed'] and gate['exact_references'] == 12
    plan = read(J / 'plan.json')
    expected = {f"{t['variant']}_seed{t['seed']}" for t in plan['tasks']}
    seen = set()
    for line in (J / 'results/completed.jsonl').read_text().splitlines():
        item = json.loads(line)
        assert item['task_id'] in expected and item['task_id'] not in seen
        assert item['file'] == item['task_id'] + '.json'
        assert sha(J / 'results/tasks' / item['file']) == item['sha256']
        seen.add(item['task_id'])
    assert seen == expected
    manifest = read(J / 'results/stack_manifest.json')
    assert manifest['recipes'] == 2244 and manifest['all_roundtrips_exact']
    for item in manifest['chunks']:
        assert sha(J / 'results' / item['file']) == item['sha256']
    return {name: sha(J / 'results' / name) for name in
            ['completion.json', 'reference_gate.json', 'completed.jsonl', 'stack_manifest.json']}


def main():
    OUT.mkdir(exist_ok=True)
    lock = (OUT / 'sequential.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    auth = read(ROOT / 'launch_authorization.json')
    assert auth['model_fits_authorized'] and auth['queue_enabled']
    verify_inputs(auth)
    launched = OUT / 'sequential_launch.json'
    if launched.exists():
        assert read(launched)['unit'] == UNIT
        return
    start = time.time()
    while time.time() - start < 28800:
        j = unit_state('draftdb-r9j-20260907')
        waiting = unit_state('draftdb-r9j-queue-20260907')
        if j['ActiveState'] in ['active', 'activating', 'deactivating'] or waiting['ActiveState'] in ['active', 'activating']:
            write(OUT / 'queue_progress.json', {'status': 'waiting', 'waiting_for': 'R9j clean completion',
                  'updated': time.time(), 'K_models_started': False})
            time.sleep(30)
            continue
        assert j['ActiveState'] == 'inactive' and j['Result'] == 'success' and j['MainPID'] == '0', j
        if j.get('ControlGroup'):
            cg = Path('/sys/fs/cgroup') / j['ControlGroup'].lstrip('/')
            assert not cg.exists() or not any(p.read_text().strip() for p in cg.rglob('cgroup.procs'))
        proof = verify_j()
        verify_inputs(auth)
        assert not (OUT / 'state.json').exists()
        assert unit_state(UNIT)['ActiveState'] == 'inactive'
        subprocess.run(['sudo', '-n', 'systemd-run', '--unit', UNIT,
                        '--property=RuntimeMaxSec=10800', '--property=MemoryMax=140G',
                        '--property=CPUQuota=2200%', '--property=KillMode=control-group',
                        '--property=WorkingDirectory=' + str(ROOT), '--uid=ubuntu', '--gid=ubuntu',
                        '/home/ubuntu/nba/.venv/bin/python', '-u', str(ROOT / 'research.py')], check=True)
        write(launched, {'unit': UNIT, 'started_at': time.time(), 'J_verified': proof,
                        'authorization_sha256': sha(ROOT / 'launch_authorization.json'),
                        'no_J_scores_used_for_selection': True})
        write(OUT / 'queue_progress.json', {'status': 'launched', 'unit': UNIT, 'updated': time.time()})
        return
    raise TimeoutError('K waiting controller exceeded eight hours; no retry or duplicate launch')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        write(OUT / 'queue_progress.json', {'status': 'failed', 'error': repr(error), 'updated': time.time()})
        raise
