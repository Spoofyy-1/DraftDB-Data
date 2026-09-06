"""Freeze individual biography screen and completed R8t baseline references."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import shutil
import pandas as pd

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8t'
DATA=ROOT/'data'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    original=json.loads((SOURCE/'plan.json').read_text())
    manifest=json.loads((SOURCE/'data/manifest.json').read_text())
    state=json.loads((SOURCE/'results/state.json').read_text())
    assert state['status']=='completed' and state['completed']==state['total']==60
    assert all('error' not in e for e in state['candidates'])
    for name,digest in manifest['files'].items():
        assert Path(name).name==name and sha(SOURCE/'data'/name)==digest
        shutil.copyfile(SOURCE/'data'/name,DATA/name)
    shutil.copyfile(SOURCE/'legacy_kernel.py',ROOT/'legacy_kernel.py')
    plan=copy.deepcopy(original)
    plan.update(study='R8u individual dated biography screen',baseline='baseline',
                purpose='Identify useful or harmful individual biography fields on the fixed canonical source-college plus real-consensus background.',
                backgrounds={'college_consensus':['consensus']},single_features=original['families']['bio'],
                common_bio_slot='slot_041',
                variants=[{'id':'baseline','background':'college_consensus','bio_arm':'absent','feature':None,'arms':{'consensus':'real'},'permutation_seed':None}])
    for feature in plan['single_features']:
        plan['variants'].append({'id':feature+'_real','background':'college_consensus','bio_arm':'real','feature':feature,'arms':{'consensus':'real','bio':'real'},'permutation_seed':None})
        for seed in plan['permutation_seeds']:
            plan['variants'].append({'id':f'{feature}_shuffle{seed}','background':'college_consensus','bio_arm':'permuted','feature':feature,'arms':{'consensus':'real','bio':'permuted'},'permutation_seed':seed})
    assert len(plan['variants'])*len(plan['seeds'])==123
    plan['controls'].update(shuffle='Permute one selected biography field within draft cohort AND its exact observed/missing mask, preserving each player mask and observed-value multiset.',
                            seed_stream='SHA256(bio:feature_name, permutation seed, train-or-validation role, cohort, mask pattern). Same fixed source and consensus for all fields, arms and fit seeds.',
                            limitations='The test preserves cohort and missingness distributions. Constant/singleton strata cannot move; report effective changed rows. Individual screening after the family-level study is exploratory and requires later independent confirmation.')
    plan['summary']={'primary':'Pair each actual biography field with the mean of three matched shuffles within fold and model seed; same single added slot across all ten fields.',
                     'baseline':'Baseline has45 features, single/control arms46. Empty-column gain is not evidence; judge only matched real-minus-shuffled contrasts.',
                     'automatic_promotion':False,'combinations':'No combinations or further model selection in this registration.'}
    plan['registration_basis']='R8t completed family screen hurt all backgrounds. This registered follow-up includes every one of the ten fields, without outcome-based exclusion. No held-out data or confirmation used.'
    plan['execution'].update(task_count=123,workers=4,gpu_launch_performed=False,max_runtime_seconds=7200,memory_max='140G',cpu_quota='2200%')
    (ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    manifest.update(parent_r8t_plan_sha256=sha(SOURCE/'plan.json'),parent_r8t_worker_sha256=sha(SOURCE/'worker.py'))
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

    # Reference hashes come from actual completed R8t baseline audits. Build
    # its full45-column matrices independently without fitting any model.
    reference_root=ROOT/'r8t_reference'
    reference_root.mkdir(exist_ok=True)
    for name in ['worker.py','plan.json','legacy_kernel.py']:
        shutil.copyfile(SOURCE/name,reference_root/name)
    if not (reference_root/'data').exists(): (reference_root/'data').symlink_to('../data',target_is_directory=True)
    reference=[]
    baseline_entries=[e for e in state['candidates'] if e['config']['id']=='college_consensus_baseline']
    assert {e['seed'] for e in baseline_entries}==set(plan['seeds'])
    fields=['ordered_base_columns','base_columns_hash','training_pid_hash','validation_pid_hash','training_labels_hash',
            'training_matrix_hash','validation_matrix_hash','source_selection_hash','ordering_policy_hash','input_columns','raw_feature_count','training_nonconstant_columns']
    for year in plan['folds']:
        rows=[next(row for row in entry['rows'] if row['season']==year) for entry in baseline_entries]
        audit=rows[0]['audit']
        for row in rows:
            assert all(row['audit'][field]==audit[field] for field in fields)
            assert row['audit']['families']['consensus']==audit['families']['consensus']
        expected={'year':year,'audit':{field:audit[field] for field in fields},'consensus':audit['families']['consensus'],
                  'query_vector_hashes':audit['canonical_prediction_ties']['row_vector_hashes']}
        reference.append(expected)
    (ROOT/'baseline_reference.json').write_text(json.dumps({'source':'Completed R8t college_consensus_baseline, all3 fit seeds agree on fixed input hashes',
        'r8t_state_sha256':sha(SOURCE/'results/state.json'),'source_data_hashes':manifest['files'],'folds':reference},indent=2)+'\n')
    print(json.dumps({'tasks':123,'source_fields':41,'fixed_consensus':4,'individual_fields':10,'baseline_reference_checks':'exact_completed_R8t_hashes','gpu_models_run':0}))

if __name__=='__main__':main()
