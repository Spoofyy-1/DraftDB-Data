"""Registration/reference/tie/aggregation fixtures; never train a model."""
from pathlib import Path
import copy,hashlib,json,sys,types
import numpy as np
import worker as W
ROOT=Path(__file__).resolve().parent
plan,manifest,x,labels=W._load_inputs()
reference=json.loads((ROOT/'baseline_reference.json').read_text())
assert len(plan['tasks'])==48 and len(plan['models'])==10
assert sum(plan['models'][next(v['model_id'] for v in plan['variants'] if v['id']==t['variant'])]['family']=='ridge' for t in plan['tasks'])==6
for name,digest in reference['source_data_hashes'].items():assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==digest
assert hashlib.sha256((ROOT/'r8u_reference/worker.py').read_bytes()).hexdigest()==manifest['parent_r8u_worker_sha256']
assert hashlib.sha256((ROOT/'r8u_reference/plan.json').read_bytes()).hexdigest()==manifest['parent_r8u_plan_sha256']
fixtures=[]
for task in plan['tasks']:
    variant=next(v for v in plan['variants'] if v['id']==task['variant']);seed=task['seed'];spec=plan['models'][variant['model_id']]
    ref=next(r for r in reference['references'] if r['background']==variant['background'] and r['seed']==seed)
    rows=copy.deepcopy(ref['rows'])
    params={k:seed if v=='task_seed' else v for k,v in spec['parameters'].items()}
    for row in rows:
        # Invented fixture scores are not model results and are never persisted
        # in results/. Exact reference scores remain for the replay arms.
        if variant['model_id']!='tabicl32':row['stack']+=.01
        audit=row['audit'];audit['registered_model_parameters']=params
        audit['model']={'family':spec['family'],'registered_parameters':params,'input_features':len(audit['input_columns']),
            'training_rows':row['ntrain'],'validation_rows':row['n'],'training_only_preprocessing':True}
        width=len(audit['input_columns'])
        if spec['family']=='ridge':
            audit['model']['preprocessing']={'imputer_training_statistics':[0.]*width,'missing_indicator_input_indices':[],
                'scaler_training_mean':[0.]*width,'scaler_training_scale':[1.]*width,'scaler_training_samples_seen':row['ntrain'],
                'transformed_width':width,'training_transformed_hash':'0'*64}
        else:
            audit['model']['effective_constructor']=dict(params)
            if spec['family']=='tabicl':
                audit['model']['effective_constructor']['feat_shuffle_method']='latin'
                audit['model'].update(effective_estimator_count=min(params['n_estimators'],width),effective_feature_count=width)
            else:audit['model']['native_nan_processing']=True
    fixtures.append({'config':variant,'seed':seed,'task_id':f"{variant['id']}_seed{seed}",'rows':rows,
                     'score':float(np.mean([r['stack'] for r in rows])),'diagnostic_only':True})
summary=W.summarize_matched(fixtures)
assert summary['completed_tasks']==48 and len(summary['statistics'])==20 and summary['interpretation_allowed']
assert len(summary['baseline_replay_checks'])==6 and not summary['baseline_replay_pending']
missing=[e for e in fixtures if e['config']['id']!='college_consensus_tabicl32']
assert not W.summarize_matched(missing)['interpretation_allowed'] and not W.summarize_matched(missing)['statistics']
tests=[]
def rejects(name,mutate,ref=False,model_id=None):
    changed=copy.deepcopy(fixtures)
    target_id='college_consensus_'+model_id if model_id else ('college_consensus_tabicl32' if ref else 'college_consensus_xgb_depth3')
    target=next(e for e in changed if e['config']['id']==target_id and e['seed']==0)
    mutate(target)
    try:W.summarize_matched(changed)
    except AssertionError:tests.append(name)
    else:raise AssertionError('Accepted tamper '+name)
rejects('gpu_xgboost_disallowed',lambda e:e['rows'][0]['audit']['registered_model_parameters'].__setitem__('device','cuda'))
rejects('changed_seed',lambda e:e['rows'][0]['audit']['registered_model_parameters'].__setitem__('random_state',999))
rejects('changed_input_columns',lambda e:e['rows'][0]['audit']['input_columns'].__setitem__(0,'actual_pick'))
rejects('changed_training_label_hash',lambda e:e['rows'][0]['audit'].__setitem__('training_labels_hash','changed'))
rejects('future_training_season',lambda e:e['rows'][0]['audit'].__setitem__('max_label_season',2012))
rejects('validation_fitted_preprocessing',lambda e:e['rows'][0]['audit']['model'].__setitem__('training_only_preprocessing',False))
rejects('missing_effective_constructor',lambda e:e['rows'][0]['audit']['model'].pop('effective_constructor'))
rejects('wrong_effective_ensemble_count',lambda e:e['rows'][0]['audit']['model'].__setitem__('effective_estimator_count',999),True)
rejects('missing_ridge_preprocessing',lambda e:e['rows'][0]['audit']['model'].pop('preprocessing'),model_id='ridge30')
rejects('wrong_scaler_training_count',lambda e:e['rows'][0]['audit']['model']['preprocessing'].__setitem__('scaler_training_samples_seen',999),model_id='ridge30')
rejects('changed_raw_reference_prediction',lambda e:e['rows'][0]['predictions'][0].__setitem__('raw_score',999.),True)
rejects('changed_reference_score',lambda e:e.__setitem__('score',e['score']+.01),True)
original=sys.modules.get('tabicl')
try:
    class Rejecting:
        calls=0
        def __init__(self,**kwargs):Rejecting.calls+=1;raise TypeError('unsupported test signature')
    sys.modules['tabicl']=types.SimpleNamespace(TabICLRegressor=Rejecting)
    try:W.make_registered_model(plan['models']['tabicl16'],0)
    except TypeError:pass
    else:raise AssertionError('Constructor failure was hidden')
    assert Rejecting.calls==1
finally:
    if original is None:sys.modules.pop('tabicl',None)
    else:sys.modules['tabicl']=original
report={'passed':True,'tasks':48,'model_specs':10,'backgrounds':2,'deterministic_ridge_tasks':6,
    'source_files_checked':len(reference['source_data_hashes']),'summary_fixture_variants':20,
    'six_reference_replays_required_before_interpretation':True,'tamper_rejections':tests,
    'TypeError_constructor_fails_closed':True,'gpu_predictor_calls':0,'research_estimators_fitted':0,
    'server_tests_required':'Actual sklearn median/indicator/scaling train-only fixtures; native-NaN ExtraTrees tags; CPU XGB constructor; completed U exact input/hash replay for both backgrounds.'}
(ROOT/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
