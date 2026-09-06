import copy,json,itertools,hashlib
from pathlib import Path
import numpy as np
import worker as W
p=W.load_plan();cap=W.capacity();grid=p['requested_grid'];assert len(grid)==432
assert {(s['norm_methods'],s['outlier_threshold'],s['n_estimators'],s['target_transform'])for s in grid}==set(itertools.product(p['normalizations'],p['outlier_thresholds'],p['requested_estimator_counts'],p['target_transforms']))
assert len(p['variants'])*3==p['execution']['task_count'] and set(p['requested_to_evaluated'])=={s['id']for s in grid}
for requested,evaluated in p['requested_to_evaluated'].items():
 if evaluated is None:assert requested in cap['invalid_configurations'] and requested in p['excluded_before_fitting']
 else:assert cap['equality_signatures'][requested]==cap['equality_signatures'][evaluated]
assert all(p['requested_to_evaluated'][v]==v for v in p['reference_ids'])
def rejects(fn):
 try:fn()
 except (AssertionError,KeyError):return
 raise AssertionError('Tamper accepted')
y=np.array([-4.,-2.,-1.,0.,0.,1.,2.,4.]);before=y.copy()
for name in p['target_transforms']:
 z,a=W.transform_target(y,name);assert np.array_equal(y,before) and a['original_hash']==W.array_hash(y) and a['nondecreasing'] and a['original_equal_ties_preserved'] and np.all(np.diff(z)>=0) and z[3]==z[4]
 if name=='identity':assert np.array_equal(z,y) and a['transformed_hash']==a['original_hash']
 if name=='ndtr':assert z[3]==.5 and (z>0).all() and (z<1).all()
 if name=='signed_log1p':assert z[5]==np.log(2.) and z[0]==-np.log(5.)
 if name=='clip1_5':assert z[0]==z[1]==-1.5 and z[-1]==z[-2]==1.5 and a['additional_tied_adjacent_pairs']==2
rejects(lambda:W.transform_target(np.array([1.,float('nan')]),'identity'));rejects(lambda:W.transform_target(y,'unregistered'))
records=[]
for (vid,seed),old in W.d_references().items():
 e=copy.deepcopy(old);e['config']=next(v for v in p['variants']if v['id']==vid)
 for row in e['rows']:
  target=cap['designs'][vid][f"{row['season']}:{seed}"]['training_target_transform'];row['audit']['training_target_transform']=target;row['model_design']['training_target_transform']=target
 W.validate_entry(e,p);records.append(e)
assert W.summarize_matched(records)['reference_replays_passed']==18 and not W.summarize_matched(records[:-1])['interpretation_allowed']
for mutation in ['raw','future','target','width']:
 e=copy.deepcopy(records[0]);row=e['rows'][0]
 if mutation=='raw':row['predictions'][0]['raw_score']+=1
 if mutation=='future':row['audit']['max_label_season']=2020
 if mutation=='target':row['audit']['training_target_transform']['transformed_hash']='tampered'
 if mutation=='width':row['model_design']['generator']['effective_features']+=1
 rejects(lambda:W.validate_entry(e,p))
rows=[{'predictions':[{'pid':'a','score':a},{'pid':'b','score':b}]}for a,b in [(1.,9.),(4.,6.),(7.,3.)]];pids,mean=W.mean_saved_predictions(rows);assert pids==['a','b'] and np.array_equal(mean,[4.,6.]);rejects(lambda:W.mean_saved_predictions(rows[:2]));bad=copy.deepcopy(rows);bad[1]['predictions'].reverse();rejects(lambda:W.mean_saved_predictions(bad))
json.dumps(cap,allow_nan=False);json.dumps(p,allow_nan=False)
out={'passed':True,'models_fitted':0,'requested_configurations':432,'distinct_configurations':len(p['variants']),'tasks':p['execution']['task_count'],'all_dedupes_identical_across9fold_seed_designs':True,'18_exact_D_reference_contracts':True,'training_only_target_invariants_and_no_mutation':True,'fixed_all_three_seed_mean_fixture':True,'tamper_rejections':['raw_reference_prediction','future_label','training_target_hash','effective_width','missing_reference','nonfinite_target','unregistered_transform','missing_seed','misaligned_prediction_pids']}
(Path(__file__).parent/'results/tests.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
