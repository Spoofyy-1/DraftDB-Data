"""Pinned-runtime/source checks and bounded unscored GPU compatibility fixtures."""
from pathlib import Path
import json,hashlib,inspect,itertools,re,copy,tempfile
import numpy as np
import catboost,catboost._catboost as binary
from catboost import CatBoostRegressor
import worker as W
import queue_runtime as Q
from postprocess import rank_blend
R=Path(__file__).resolve().parent;O=R/'results'
def reject(fn):
 try:fn()
 except (AssertionError,TypeError,KeyError):return
 raise AssertionError('Invalid input accepted')
def prepare(gpu_fixture=False):
 p=W.load_plan();sources={}
 for path in [Path(inspect.getfile(CatBoostRegressor)),Path(binary.__file__)]:sources[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 assert catboost.__version__=='1.2.10';assert len(p['variants'])==145 and p['execution']['task_count']==435
 assert {(tuple(v[k]for k in p['grid']))for v in p['variants'][1:]}==set(itertools.product(*p['grid'].values()))
 assert all(re.fullmatch(r'[A-Za-z0-9_]+',f"{v['id']}_seed{s}")for v in p['variants']for s in p['seeds'])
 for v in p['variants'][1:]:
  for seed in p['seeds']:W.make_model(v,seed)
 _,_,_,folds=W.B._prepared();designs={}
 for fold in folds:
  atr,ate=W.design(fold);designs[str(fold['year'])]={'train_hash':W.B._matrix_hash(atr),'query_hash':W.B._matrix_hash(ate),'training_target_hash':W.D.h(np.asarray(fold['yy'])),'columns':list(atr),'train_rows':len(atr),'query_rows':len(ate)}
  for seed in p['seeds']:
   old=next(r for r in W.D.references()[seed]['rows']if r['season']==fold['year']);assert list(atr)==old['audit']['input_columns'];assert [W.B._hash(k)for k in W.B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
   anchor=next(r for r in W.anchors()[(p['reference_id'],seed)]['rows']if r['season']==fold['year']);assert anchor['predictions']==old['predictions']and anchor['stack']==old['stack']
 first=folds[0];atr,ate=W.design(first)
 class Spy:
  tree_count_=1200
  def fit(self,*args,**kwargs):assert len(args)==2 and not kwargs and W.B._matrix_hash(args[0])==W.B._matrix_hash(atr)and np.array_equal(args[1],first['yy']);self.fit_checked=True;return self
  def predict(self,data,ntree_end=None,thread_count=None):assert ntree_end in [200,600,1200]and thread_count==2 and W.B._matrix_hash(data)==W.B._matrix_hash(ate);return np.zeros(len(data))
 spy=Spy();W.fit_native(spy,atr,first['yy']);assert spy.fit_checked
 reject(lambda:W.fit_native(spy,atr,first['yy'],eval_set=(ate,None)))
 for bad in [0,199,201,1201]:reject(lambda bad=bad:W.predict_checkpoint(spy,ate,bad))
 for end in p['tree_checkpoints']:W.predict_checkpoint(spy,ate,end)
 with tempfile.TemporaryDirectory(dir=O)as tmp:
  reject(lambda:Q.save_immutable(Path(tmp),{'task_id':'bad.03'}));Q.save_immutable(Path(tmp),{'task_id':'good0p03'})
 # Original-vector duplicate ties, including NaN/signed-zero equivalence, and no rank-blend order dependence.
 import pandas as pd
 matrix=pd.DataFrame({'a':[np.nan,np.nan,2.],'b':[0.,-0.,1.]});pred,ties=W.B._canonical_predictions(matrix,np.array([1.,3.,9.]),['a','b','c']);assert np.array_equal(pred,[2.,2.,9.])
 a=np.array([1.,1.,3.,5.]);b=np.array([5.,5.,1.,3.]);order=np.array([3,1,0,2])
 for step in range(11):assert np.array_equal(rank_blend(a[order],b[order],step),rank_blend(a,b,step)[order])
 probes=[]
 if gpu_fixture:
  for loss,nan in itertools.product(p['grid']['loss_function'],p['grid']['nan_mode']):
   v=next(v for v in p['variants'][1:]if v['loss_function']==loss and v['nan_mode']==nan and v['depth']==7 and v['learning_rate']==.1 and v['l2_leaf_reg']==1 and v['bagging_temperature']==1)
   model,params=W.make_model(v,0,iterations=2);W.fit_native(model,atr,first['yy']);assert model.tree_count_==2 and model.feature_names_==list(atr)and set(model.get_evals_result())<= {'learn'}
   effective=model.get_all_params();assert effective['task_type']=='GPU'
   for end in [1,2]:W.predict_checkpoint(model,ate,end,allowed=[1,2])
   reject(lambda:W.predict_checkpoint(model,ate,3,allowed=[3]));probes.append({'loss':loss,'nan_mode':nan,'iterations':2,'tree_count':model.tree_count_,'actual_task_type':effective['task_type'],'constructor':params,'effective_constructor':effective,'scored':False})
  support={'version':catboost.__version__,'sources':sources,'source_designs':designs,'gpu_fixtures':probes,'GPU_fixture_models_fitted':4,'models_scored':0,'no_query_data_in_fit':True,'native_NaNs_verified':True};Q.atomic_json(O/'runtime_support.json',support)
 else:
  support=json.loads((O/'runtime_support.json').read_text());assert support['version']==catboost.__version__ and support['sources']==sources and support['source_designs']==designs and len(support['gpu_fixtures'])==4
 proof={'passed':True,'CPU_and_source_checks_passed':True,'fit_query_exclusion_fixture':True,'checkpoint_range_guards':True,'identical_input_ties':True,'safe_task_ids':True,'rank_blend_order_invariance':True,'exact_B_and_E_anchor_inputs':True,'registered_tasks':435,'GPU_compatibility_fixture_count':4,'GPU_fixture_scores_used':False}
 Q.atomic_json(O/'tests.json',proof);print(json.dumps(proof),flush=True)
if __name__=='__main__':
 import sys
 prepare(gpu_fixture='--gpu-fixture'in sys.argv)
