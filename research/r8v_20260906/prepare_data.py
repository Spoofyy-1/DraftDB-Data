"""Register a fixed 48-task comparison; no model fitting or held-out access."""
from pathlib import Path
import copy,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'r8u'
DATA=ROOT/'data'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source_plan=json.loads((SOURCE/'plan.json').read_text());manifest=json.loads((SOURCE/'data/manifest.json').read_text())
    state=json.loads((SOURCE/'results/state.json').read_text())
    assert state['status']=='completed' and state['completed']==123 and not any('error' in e for e in state['candidates'])
    for name,digest in manifest['files'].items():
        assert sha(SOURCE/'data'/name)==digest
        shutil.copyfile(SOURCE/'data'/name,DATA/name)
    shutil.copyfile(SOURCE/'legacy_kernel.py',ROOT/'legacy_kernel.py')
    models={}
    for n in [16,32,45]:models[f'tabicl{n}']={'family':'tabicl','seeds':[0,101,202],'resource':'gpu',
        'parameters':{**source_plan['model_constructor'],'n_estimators':n}}
    for alpha in [30,300,3000]:models[f'ridge{alpha}']={'family':'ridge','seeds':[0],'resource':'cpu',
        'parameters':{'alpha':alpha,'solver':'svd'},'preprocessing':{'imputer':{'strategy':'median','add_indicator':True,'keep_empty_features':True},
        'scaler':{'with_mean':True,'with_std':True},'fit_scope':'training only; all-missing training columns retained as0; missing indicators created from training missingness only'}}
    for leaf in [5,15]:models[f'extratrees_leaf{leaf}']={'family':'extratrees','seeds':[0,101,202],'resource':'cpu',
        'parameters':{'n_estimators':500,'min_samples_leaf':leaf,'max_features':.7,'n_jobs':2,'random_state':'task_seed'}}
    for depth in [3,5]:models[f'xgb_depth{depth}']={'family':'xgb','seeds':[0,101,202],'resource':'cpu',
        'parameters':{'max_depth':depth,'n_estimators':300,'learning_rate':.05,'min_child_weight':5,'reg_lambda':5,
        'subsample':.8,'colsample_bytree':.8,'n_jobs':2,'device':'cpu','tree_method':'hist','objective':'reg:squarederror','random_state':'task_seed'}}
    plan=copy.deepcopy(source_plan)
    plan.update(study='R8v fixed model-family comparison',purpose='Compare model families on identical canonical source-college+consensus data, with a fixed optional shooting-guard indicator.',
                models=models,backgrounds={'college_consensus':False,'college_consensus_sg':True},variants=[],tasks=[],
                single_features=['vmb_position_sg'],baseline='college_consensus_tabicl32')
    for background,sg in plan['backgrounds'].items():
        for model_id,model in models.items():
            plan['variants'].append({'id':background+'_'+model_id,'background':background,'model_id':model_id,
                'bio_arm':'real' if sg else 'absent','feature':'vmb_position_sg' if sg else None,
                'arms':{'consensus':'real',**({'bio':'real'} if sg else {})},'permutation_seed':None})
    order=['tabicl16','ridge30','extratrees_leaf5','xgb_depth3','tabicl32','ridge300','extratrees_leaf15','xgb_depth5','tabicl45','ridge3000']
    for seed in plan['seeds']:
        for model_id in order:
            if seed not in models[model_id]['seeds']:continue
            for background in plan['backgrounds']:plan['tasks'].append({'variant':background+'_'+model_id,'seed':seed})
    assert len(plan['tasks'])==48 and len({(t['variant'],t['seed']) for t in plan['tasks']})==48
    plan.pop('controls',None)
    plan['execution'].update(task_count=48,gpu_launch_performed=False,predictor='Interleaved GPU TabICL and CPU Ridge/ExtraTrees/XGBoost',queue_order=order)
    plan['summary']={'primary':'Report every registered model/background mean and fold scores; model seeds are repeated diagnostics, not independent datasets.',
        'baseline_replay':'Before interpreting, all six TabICL32 baseline/SG tasks must reproduce completed R8u scores and raw/canonical prediction vectors exactly.',
        'automatic_promotion':False,'blends':'No blends, combinations, hyperparameter extension or promotion.'}
    plan['registration_basis']='Fixed model grid requested after completed pre2019 R8u study. SG is the sole optional background selected from that development study; no2019+ test or confirmation data used.'
    (ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    manifest.update(parent_r8u_plan_sha256=sha(SOURCE/'plan.json'),parent_r8u_worker_sha256=sha(SOURCE/'worker.py'))
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    refroot=ROOT/'r8u_reference';refroot.mkdir(exist_ok=True)
    for name in ['worker.py','plan.json','legacy_kernel.py']:shutil.copyfile(SOURCE/name,refroot/name)
    if not (refroot/'data').exists():(refroot/'data').symlink_to('../data',target_is_directory=True)
    references=[]
    for bg,sg in plan['backgrounds'].items():
        source_id='vmb_position_sg_real' if sg else 'baseline'
        for seed in plan['seeds']:
            entry=next(e for e in state['candidates'] if e['config']['id']==source_id and e['seed']==seed)
            references.append({'background':bg,'seed':seed,'score':entry['score'],'rows':entry['rows']})
    (ROOT/'baseline_reference.json').write_text(json.dumps({'source':'Completed R8u baseline and SG real','state_sha256':sha(SOURCE/'results/state.json'),
        'source_data_hashes':manifest['files'],'references':references},indent=2)+'\n')
    print(json.dumps({'tasks':48,'models':10,'backgrounds':2,'ridge_tasks':6,'gpu_launch':False}))

if __name__=='__main__':main()
