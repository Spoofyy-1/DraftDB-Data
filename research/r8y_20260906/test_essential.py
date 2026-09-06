"""Small contract tests only. No estimator fitting or synthetic model inputs."""
import copy,json,numpy as np
from pathlib import Path
import worker as Y
R=Path(__file__).resolve().parent;p=Y.plan();refs=Y.references();fixtures=[]
for v in p['variants']:
 for seed in p['seeds']:
  e=copy.deepcopy(refs[(v['context'],seed)]);e.update(config=v,task_id=f"{v['id']}_seed{seed}")
  for row in e['rows']:
   row['audit']['registered_model_parameters']['n_estimators']=v['n_estimators'];width=row['audit']['training_nonconstant_columns']
   row['capacity']={'requested':v['n_estimators'],'effective_estimators':min(v['n_estimators'],width),'effective_features':width,'effective_constructor':copy.deepcopy(row['audit']['registered_model_parameters'])}
  fixtures.append(e)
s=Y.summarize_matched(fixtures);assert s['reference_replays_passed']==6 and s['interpretation_allowed'] and len(s['size_results'])==len(p['sizes'])
assert not Y.summarize_matched([e for e in fixtures if e['task_id']!='baseline_n32_seed0'])['interpretation_allowed']
for result in s['size_results']:assert result['baseline_minus_n32']==result['pair_minus_n32']==0
rejected=[]
def reject(name,mutate):
 e=copy.deepcopy(next(e for e in fixtures if e['task_id']=='pair06_RR_n32_seed0'));mutate(e)
 try:Y.validate_entry(e)
 except (AssertionError,KeyError):rejected.append(name)
 else:raise AssertionError('Tamper accepted: '+name)
reject('raw_prediction',lambda e:e['rows'][0]['predictions'][0].__setitem__('raw_score',999.))
reject('reference_score',lambda e:e.__setitem__('score',999.))
reject('input_hash',lambda e:e['rows'][0]['audit'].__setitem__('training_matrix_hash','wrong'))
reject('unregistered_norm',lambda e:e['rows'][0]['audit']['registered_model_parameters'].__setitem__('norm_methods','power'))
reject('effective_count',lambda e:e['rows'][0]['capacity'].__setitem__('effective_estimators',999))
reject('missing_capacity',lambda e:e['rows'][0].pop('capacity'))
(R/'tests.json').write_text(json.dumps({'passed':True,'models_fitted':0,'fixtures_not_model_data':True,'tasks':len(fixtures),'six_reference_gate':True,'tamper_rejections':rejected},indent=2)+'\n');print('Essential reference/config/capacity fixtures passed.')
