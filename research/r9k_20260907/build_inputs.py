"""Join frozen source panels and cutoff label exports; no fitting or score reading."""
from pathlib import Path
import hashlib
import json
import os
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
H = ROOT.parent / 'r9h'
LABELS = ROOT.parent / 'r9k_label_exports'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def values_hash(a):
    a = np.asarray(a, dtype=np.float64)
    a = np.where(a == 0., 0., a)
    mask = np.isnan(a)
    return hashlib.sha256(json.dumps(list(a.shape), separators=(',', ':')).encode() + mask.tobytes() + np.where(mask, 0., a).tobytes()).hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def main():
    os.umask(0o077)
    assert not (ROOT / 'inputs').exists() and not (ROOT / 'plan.json').exists()
    hm = read(H / 'source_manifest.json')
    hp = read(H / 'plan.json')
    hf = read(H / 'frozen.json')
    assert sha(H / 'frozen.json') == '22e68b8bee7902d65ed0f1c7a2d04bde3fc6521f5f872339faead15416c24d0e'
    assert sha(H / 'plan.json') == hf['files']['plan.json']
    pm = read(ROOT / 'panels/panel_manifest.json')
    assert pm['H44_shared_exact'] and pm['rows'] == 1428 and len(pm['H_input_only_matrix_replays']) == 66
    panels = {}
    for width, filename in [(44, 'pairedpanel44.csv'), (174, 'panel174.csv')]:
        path = ROOT / 'panels' / filename
        assert sha(path) == pm['outputs'][filename]['sha256']
        frame = pd.read_csv(path, float_precision='round_trip')
        columns = pm['columns' + str(width)]
        assert frame.pid.is_unique and len(frame) == 1428 and frame.draft_year.between(2000, 2018).all()
        assert list(frame) == ['pid', 'draft_year', 'was_drafted'] + columns
        assert values_hash(frame[columns]) == pm['outputs'][filename]['matrix_hash']
        panels['panel' + str(width)] = (frame.set_index('pid'), columns)
    assert panels['panel174'][0][pm['columns44']].equals(panels['panel44'][0][pm['columns44']])
    lm = read(LABELS / 'manifest.json')
    assert lm['all_H_controls_exact_and_broker_reverified'] and len(lm['exports']) == 6
    protocol_hash = sha(ROOT / 'code/protocol.json')
    (ROOT / 'inputs').mkdir()
    (ROOT / 'scoring').mkdir()
    scoring = {}
    queries = {}
    for year in [2012, 2013, 2014]:
        rel = f'data/query_{year}.npz'
        assert sha(H / rel) == hm['data_files'][rel]['sha256'] == hf['files'][rel]
        with np.load(H / rel, allow_pickle=False) as q:
            queries[year] = q['pid'].copy()
            assert q['pid'].tolist() == hp['queries'][str(year)]['query_pids']
            assert np.array_equal(panels['panel44'][0].loc[q['pid'], pm['columns44']].to_numpy(float), q['X'], equal_nan=True)
            path = ROOT / 'scoring' / f'{year}.npz'
            np.savez_compressed(path, pid=q['pid'], legacy_truth=q['legacy_truth'], observed_truth_mask=q['observed_truth_mask'])
        scoring[str(year)] = {'sha256': sha(path), 'source_sha256': sha(H / rel),
                             'not_mounted_in_model_worker': True}
    tasks = []
    for export in lm['exports']:
        year, policy = export['year'], export['policy']
        source = LABELS / policy / str(year)
        assert sha(source / 'manifest.json') == export['manifest_sha256']
        m = read(source / 'manifest.json')
        assert sha(source / 'training.npz') == export['training_npz_sha256'] == m['training_npz_sha256']
        assert m['all_labels_finite_observed'] and not m['missing_training_labels_zero_filled']
        assert m['max_actual_label_season'] <= year - 1
        with np.load(source / 'training.npz', allow_pickle=False) as a:
            labels = {k: a[k].copy() for k in a.files}
        assert set(labels) == {'pid', 'draft_year', 'label_value', 'y', 'prefix_length'}
        assert values_hash(labels['label_value']) == m['label_value_hash'] and values_hash(labels['y']) == m['y_hash']
        for panel, (frame, columns) in panels.items():
            tid = f'{panel}_{policy}_y{year}'
            directory = ROOT / 'inputs' / tid
            directory.mkdir()
            admitted = frame.loc[labels['pid']]
            query = frame.loc[queries[year]]
            assert np.array_equal(admitted.draft_year, labels['draft_year']) and admitted.draft_year.lt(year).all()
            assert query.draft_year.eq(year).all() and query.was_drafted.eq(1).all()
            assert not set(admitted.index) & set(query.index)
            np.savez_compressed(directory / 'training.npz', **labels, X=admitted[columns].to_numpy(float))
            np.savez_compressed(directory / 'inference.npz', pid=queries[year], X=query[columns].to_numpy(float))
            audit = {'outer_year': year, 'max_actual_label_season': m['max_actual_label_season'],
                     'all_labels_finite_observed': True, 'missing_training_labels_zero_filled': False,
                     'training_pid_hash': m['pid_hash'], 'label_value_hash': m['label_value_hash'],
                     'target_hash': m['y_hash'], 'source_fact_hash': m['source_fact_hash'],
                     'source_fact_rows': m['source_fact_rows'], 'prefix_length_counts': m['prefix_length_counts'],
                     'cohort_counts': m['cohort_counts'], 'label_value_definition': m['label_value_definition'],
                     'cutoff_broker_verified': True}
            manifest = {'task_id': tid, 'panel_id': panel, 'policy_id': policy, 'outer_year': year,
                        'columns': columns, 'protocol_sha256': protocol_hash,
                        'files': {name: {'sha256': sha(directory / name)} for name in ['training.npz', 'inference.npz']},
                        'label_audit': audit, 'source_panel_manifest_sha256': sha(ROOT / 'panels/panel_manifest.json'),
                        'source_label_manifest_sha256': sha(source / 'manifest.json')}
            write(directory / 'manifest.json', manifest)
            tasks.append({'id': tid, 'panel_id': panel, 'policy_id': policy, 'outer_year': year,
                          'input_manifest_sha256': sha(directory / 'manifest.json'),
                          'training_rows': len(admitted), 'query_rows': len(query)})
    plan = {'study': 'R9k cutoff-safe OOF stacking and paired source panels', 'target_percent': 55,
            'status': 'CPU registration; launch requires preflight and frozen authorization',
            'outer_years': [2012, 2013, 2014], 'seeds': [0, 101, 202],
            'tasks': tasks, 'task_count': 12, 'model_fits': 420, 'workers': 4,
            'protocol_sha256': protocol_hash, 'scoring': scoring,
            'source_panel_manifest_sha256': sha(ROOT / 'panels/panel_manifest.json'),
            'source_label_export_manifest_sha256': sha(LABELS / 'manifest.json'),
            'selection_metric': 'Full-query Spearman, mean all three seeds and all three development folds',
            'secondary_metrics': ['Fixed complete-target subset', 'Fixed three-seed architecture-rank average'],
            'interpretation': 'Compare actual multi-family stacks against individual controls; broad inputs versus identical44control. Pre2019 reused development only; no automatic promotion.',
            'limitations': ['No55percent result promised or inferred from feature count.',
                'Not an exact original50.6 reproduction: calendar labels, missing outcomes, data coverage and model details differ.',
                'Prefix target mixes observed career lengths; missing future seasons are never invented as zeros.',
                'Original candidate pool and source vintage remain incomplete; complete-target subset can favor survivors.',
                'OOF is cross-fitting of data known by each outer cutoff, not a simulated earlier historical inner-year prediction.',
                'No2019+inputs/outcomes mounted; no test feedback selects weights or candidates.']}
    assert len(tasks) == len({t['id'] for t in tasks}) == 12
    write(ROOT / 'plan.json', plan)
    print(json.dumps({'tasks': len(tasks), 'model_fits': 420, 'plan_sha256': sha(ROOT / 'plan.json'),
                      'training_rows': sorted({t['training_rows'] for t in tasks})}))


if __name__ == '__main__':
    main()
