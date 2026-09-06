import copy,json,itertools
from pathlib import Path
import numpy as np
import worker as W
p=W.load_plan();cap=W.capacity();grid=p['requested_grid'];assert len(grid)==60
assert {(s['norm_methods'],s['outlier_threshold'],s['n_estimators']) for s in grid}==set(itertools.product(p['normalizations'],p['outlier_thresholds'],p['requested_estimator_counts']))
assert len(p['variants'])*3==p['execution']['task_count'] and set(p['requested_to_evaluated'])=={s['id'] for s in grid}
for requested,evaluated in p['requested_to_evaluated'].items():assert cap['equality_signatures'][requested]==cap['equality_signatures'][evaluated]
assert p['requested_to_evaluated'][p['reference_id']]==p['reference_id']
records=copy.deepcopy(list(W.references().values()))
for record in records:
 for row in record['rows']:row['model_design']=cap['designs'][p['reference_id']][f"{row['season']}:{record['seed']}"]
 W.validate_entry(record,p)
assert W.summarize_matched(records)['reference_replays_passed']==3 and not W.summarize_matched(records[:-1])['interpretation_allowed']
def rejects(fn):
 try:fn()
 except (AssertionError,KeyError):return
 raise AssertionError('Tamper accepted')
r=copy.deepcopy(records[0]);r['rows'][0]['model_design']['generator']['effective_estimators']+=1;rejects(lambda:W.validate_entry(r,p))
r=copy.deepcopy(records[0]);r['rows'][0]['predictions'][0]['raw_score']+=1;rejects(lambda:W.validate_entry(r,p))
r=copy.deepcopy(records[0]);r['rows'][0]['audit']['max_label_season']=2020;rejects(lambda:W.validate_entry(r,p))
rows=[{'predictions':[{'pid':'a','score':a},{'pid':'b','score':b}]} for a,b in [(1.,9.),(4.,6.),(7.,3.)]]
pids,mean=W.mean_saved_predictions(rows);assert pids==['a','b'] and np.array_equal(mean,[4.,6.]);rejects(lambda:W.mean_saved_predictions(rows[:2]))
bad=copy.deepcopy(rows);bad[1]['predictions'].reverse();rejects(lambda:W.mean_saved_predictions(bad))
assert W.normalize({'outlier_threshold':float('inf')})=={'outlier_threshold':'disabled'}
json.dumps(cap,allow_nan=False);json.dumps(p,allow_nan=False)
out={'passed':True,'models_fitted':0,'requested_factorial_configurations':60,'distinct_configurations':len(p['variants']),'tasks':p['execution']['task_count'],'all_dedupes_identical_across9fold_seed_designs':True,'three_exact_B_reference_contracts':True,'safe_disabled_serialization':True,'fixed_all_three_seed_mean_fixture':True,'tamper_rejections':['effective_ensemble_count','raw_reference_prediction','future_label','missing_seed','misaligned_prediction_pids']}
(Path(__file__).parent/'tests.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
