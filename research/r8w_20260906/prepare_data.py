"""Freeze all50 F50 singles with a fixed dated-consensus background."""
from pathlib import Path
import copy,hashlib,json,shutil
import pandas as pd
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8u'
FIFTY=ROOT.parent/'r8r'
DATA=ROOT/'data'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    original=json.loads((SOURCE/'plan.json').read_text());um=json.loads((SOURCE/'data/manifest.json').read_text())
    fm=json.loads((FIFTY/'data/manifest.json').read_text());fp=json.loads((FIFTY/'plan.json').read_text())
    for name,digest in um['files'].items():
        assert sha(SOURCE/'data'/name)==digest
        shutil.copyfile(SOURCE/'data'/name,DATA/name)
    for name,digest in fm['files'].items():assert sha(FIFTY/'data'/name)==digest
    for name in ['features.csv','labels.csv','incumbent.json']:assert fm['files'][name]==um['files'][name]
    for suffix in ['features.csv','dictionary.json','metadata.json','provenance.json']:
        shutil.copyfile(FIFTY/'data'/('source_'+suffix),DATA/('fifty_'+suffix))
    shutil.copyfile(SOURCE/'legacy_kernel.py',ROOT/'legacy_kernel.py')
    x=pd.read_csv(DATA/'features.csv',usecols=['pid','draft_year'])
    fifty=pd.read_csv(DATA/'fifty_features.csv')
    assert fifty[['pid','draft_year']].equals(x) and (x.draft_year<=2018).all()
    features=fm['source_features'];assert list(fifty)==['pid','draft_year']+features and len(features)==50
    lineage=json.loads((ROOT.parent/'fifty_audit/source_row_lineage.json').read_text())
    lineage=[r for r in lineage if r['draft_year']<=2018 and r['pid'] in set(x.pid)]
    for row in lineage:
        assert not row['team_has_duplicate_tpid'] and row['focal']['season']<=row['draft_year']
        assert all(r['season']<=row['draft_year'] for r in row['history']+row['team'])
    (DATA/'fifty_lineage.json').write_text(json.dumps(lineage,indent=2)+'\n')
    lineage_audit=json.loads((ROOT.parent/'fifty_audit/lineage_audit.json').read_text())
    assert not lineage_audit['features_changed'] and lineage_audit['all_existing_focal_and_history_selections_reproduced']
    assert lineage_audit['same_team_player_duplicate_rows']==0 and lineage_audit['source_player_ids_with_multiple_model_pids']==0
    (DATA/'fifty_lineage_audit.json').write_text(json.dumps(lineage_audit,indent=2)+'\n')
    plan=copy.deepcopy(original)
    plan.update(study='R8w F50 individual controls with dated consensus',purpose='Rescreen every F50 statistic on fixed source-college41 plus real dated-consensus4, allowing new information conditional on consensus.',
                single_features=features,common_extra_slot='slot_041',families={**original['families'],'fifty':features},variants=[])
    plan.pop('common_bio_slot',None)
    for year in plan['folds']:
        tr=fifty[fifty.draft_year.between(plan['backbone']['window'],year-2)]
        eligible=[c for c in features if tr[c].notna().sum()>=5 and tr[c].nunique()>=2]
        assert eligible==features
        plan['training_eligibility_registration'][str(year)]['fifty']=eligible
    plan['variants']=[{'id':'baseline','background':'college_consensus','extra_arm':'absent','feature':None,'arms':{'consensus':'real'},'permutation_seed':None}]
    for feature in features:
        plan['variants'].append({'id':feature+'_real','background':'college_consensus','extra_arm':'real','feature':feature,'arms':{'consensus':'real','fifty':'real'},'permutation_seed':None})
        for seed in plan['permutation_seeds']:
            plan['variants'].append({'id':f'{feature}_shuffle{seed}','background':'college_consensus','extra_arm':'permuted','feature':feature,'arms':{'consensus':'real','fifty':'permuted'},'permutation_seed':seed})
    assert len(plan['variants'])*len(plan['seeds'])==603
    plan['controls'].update(shuffle='Permute one F50 field only among observed values within cohort and role; preserve exact per-player missingness and observed-value multisets.',
        seed_stream='SHA256(fifty:feature_name, permutation seed, train-or-validation role, cohort, missingness pattern). Same fixed45 baseline columns and one common extra slot for all50 singles.',
        preserved='Every player/column NaN mask and within-cohort observed-value multiset for the single field. Cross-feature associations are not preserved.',
        limitations='Constant/singleton strata cannot move; report effective changed values. Fifty hypotheses after prior development studies are exploratory, not significance tests or independent confirmation.')
    plan['summary'].update(primary='Pair each real F50 field with the mean of three same-mask/cohort shuffles per fold/model seed.',
        baseline_replay='All3 baseline seeds must exactly reproduce completed R8u raw/canonical predictions and scores before interpretation.',
        baseline='No-extra baseline45 columns differs from single/control46. Report real-minus-baseline separately as descriptive; positive matched gain alone is not baseline improvement.',
        multiplicity='All50 exploratory hypotheses after prior development studies; no significance or automatic promotion.')
    plan['registration_basis']='All50 F50 fields included; no ranking-based subset. R8r lacked consensus, so this tests incremental signal conditional on fixed dated consensus. No confirmation or2019+ inputs/outcomes.'
    plan['execution'].update(task_count=603,predictor='GPU TabICL32 only; no weight reuse',gpu_launch_performed=False)
    (ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    manifest=copy.deepcopy(um)
    manifest.update(source_families=plan['families'],parent_r8u_plan_sha256=sha(SOURCE/'plan.json'),parent_r8u_worker_sha256=sha(SOURCE/'worker.py'),
        fifty_source_manifest_sha256=sha(FIFTY/'data/manifest.json'),fifty_origin_hashes=fm['files'],
        fifty_lineage_origin_sha256=sha(ROOT.parent/'fifty_audit/source_row_lineage.json'))
    manifest['files']={p.name:sha(p) for p in sorted(DATA.iterdir()) if p.is_file() and p.name!='manifest.json'}
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    ref=ROOT/'r8u_reference';ref.mkdir(exist_ok=True);(ref/'data').mkdir(exist_ok=True)
    for name in ['worker.py','plan.json','legacy_kernel.py']:shutil.copyfile(SOURCE/name,ref/name)
    shutil.copyfile(SOURCE/'data/manifest.json',ref/'data/manifest.json')
    for name in um['files']:
        if not (ref/'data'/name).exists():(ref/'data'/name).symlink_to('../../data/'+name)
    state=json.loads((SOURCE/'results/state.json').read_text());assert state['status']=='completed' and state['completed']==123
    entries=[e for e in state['candidates'] if e['config']['id']=='baseline'];assert {e['seed'] for e in entries}==set(plan['seeds'])
    (ROOT/'baseline_reference.json').write_text(json.dumps({'source':'Completed R8u baseline (also exactly replayed by R8v TabICL32)',
        'source_data_hashes':um['files'],'state_sha256':sha(SOURCE/'results/state.json'),
        'references':[{'seed':e['seed'],'score':e['score'],'rows':e['rows']} for e in entries]},indent=2)+'\n')
    print(json.dumps({'tasks':603,'features':50,'eligible_all_folds':True,'pre2019_lineages':len(lineage),'base_source_files_unchanged':True}))

if __name__=='__main__':main()
