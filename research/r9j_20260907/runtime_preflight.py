"""CPU integrity checks and synthetic software fixtures; no research fitting."""
from pathlib import Path
import copy,json,hashlib,unittest
import numpy as np
import pandas as pd
import worker as W
ROOT=Path(__file__).resolve().parent
def reject(fn):
 try:fn()
 except (AssertionError,ValueError):return
 raise AssertionError('Invalid audit/argument accepted')
def main():
 p=W.plan();checks=[]
 for payload in p['payloads']:
  for year in p['folds']:
   atr,ate,tr,te,a,q=W.H.payload(payload['id'],year)
   assert list(atr)==list(ate)==p['columns']and len(atr.columns)==44 and not set(atr)&{'pid','actual_pick','was_drafted','draft_year'}
   assert a['max_label_season']<=year-1 and np.isfinite(tr['y']).all()and not set(tr['pid'])&set(te['pid'])
   assert (a['matrix_hash'],a['target_hash'])==next((f['matrix_hash'],f['target_hash'])for f in payload['folds']if f['year']==year)
   checks.append({'payload':payload['id'],'year':year,'matrix_hash':a['matrix_hash'],'target_hash':a['target_hash'],'source_fact_hash':a['source_fact_hash'],'query_hash':q['matrix_hash'],'query_PID_hash':q['pid_hash'],'observed_mask_hash':q['observed_mask_hash']})
 # Small synthetic Ridge fixture proves train-only medians/indicators/scaling, including all-missing field.
 v=next(v for v in p['variants']if v.get('setting_id')=='ridge_a30');m,kw=W.make_model(v,0)
 x=pd.DataFrame({'a':[0.,2.,np.nan,4.],'b':[np.nan]*4});q=pd.DataFrame({'a':[1000000.,np.nan],'b':[1.,np.nan]});y=np.array([-1.,0.,1.,2.])
 W.fit_native(m,x,y);prep=W.preprocessing(m,x,q);W.validate_preprocessing(prep,x,q);assert prep['median']==[2.,0.]
 corrupt=copy.deepcopy(prep);corrupt['median'][0]=1000000.;reject(lambda:W.validate_preprocessing(corrupt,x,q))
 def forbidden(*args,**kwargs):raise AssertionError('No research model fit in CPU preflight')
 from tabicl import TabICLRegressor
 from catboost import CatBoostRegressor
 from xgboost import XGBRegressor
 from sklearn.pipeline import Pipeline
 for cls in [TabICLRegressor,CatBoostRegressor,XGBRegressor,Pipeline]:cls.fit=forbidden
 entries=[];constructors=0
 for task in p['tasks']:
  v=next(v for v in p['variants']if v['id']==task['variant']);seed=task['seed']
  if v['kind']=='stack_member_candidate':W.make_model(v,seed);constructors+=1
  else:
   old=copy.deepcopy(W.refs()[(v['H_variant_id'],seed)]);e={**old,'config':v,'task_id':f"{v['id']}_seed{seed}",'original_H_config':old['config'],'original_H_task_id':old['task_id']};W.validate_entry(e);entries.append(e)
   bad=copy.deepcopy(e);bad['rows'][0]['audit']['training_labels_hash']='tampered';reject(lambda:W.validate_entry(bad))
 assert W.summarize(entries)['reference_replays_passed']==12
 class FitSpy:
  def fit(self,*args,**kwargs):assert len(args)==2 and not kwargs;self.args=args
 spy=FitSpy();W.fit_native(spy,x,y);assert spy.args[1]is not y and np.array_equal(spy.args[1],y)
 class PredictSpy:
  tree_count_=600
  def predict(self,X,**kw):assert kw=={'ntree_end':200,'thread_count':2};return np.ones(len(X))
 cb=next(s for s in p['settings']if s['family']=='catboost');W.predict_at(PredictSpy(),q,cb,200)
 for invalid in [0,201,601,200.5]:reject(lambda:W.predict_at(PredictSpy(),q,cb,invalid))
 suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_stack_math.py');result=unittest.TextTestRunner().run(suite);assert result.wasSuccessful()
 proof={'passed':True,'research_model_fits':0,'synthetic_CPU_Ridge_fixture_fits':1,'constructors_checked':constructors,'exact_saved_reference_wrappers':12,'payloads':checks,'training_only_Ridge_missingness_and_query_exclusion':True,'reference_target_tamper_rejected':True,'checkpoint_limits_checked':True,'fixed_weight_fixture_tests':result.testsRun,'frozen_sha256':W.sha(ROOT/'frozen.json'),'registered_plan_sha256':W.sha(ROOT/'plan.json')}
 (ROOT/'results/runtime_preflight.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items()if k!='payloads'}))
if __name__=='__main__':main()
