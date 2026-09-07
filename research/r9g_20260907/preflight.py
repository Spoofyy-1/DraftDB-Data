"""CPU source/order fixtures before freeze; GPU objective fixtures run only after F completes."""
from pathlib import Path
import json,hashlib,inspect,itertools,re,tempfile,copy
import numpy as np
import pandas as pd
import xgboost as xgb
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
 for path in [Path(xgb.core.__file__),Path(xgb.training.__file__),Path(xgb.core._LIB._name)]:sources[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
 assert xgb.__version__=='3.4.1'and xgb.build_info()['USE_CUDA'];assert len(p['variants'])==577 and p['execution']['task_count']==1731
 assert {tuple(v[k]for k in p['grid'])for v in p['variants'][1:]}==set(itertools.product(*p['grid'].values()))
 ids=[f"{v['id']}_seed{s}"for v in p['variants']for s in p['seeds']];assert len(ids)==len(set(ids))==1731 and all(re.fullmatch(r'[A-Za-z0-9_]+',i)for i in ids)
 for v in p['variants'][1:]:
  for seed in p['seeds']:
   params=W.params(v,seed);assert params['device']=='cuda:0'and params['tree_method']=='hist'and params['nthread']==2 and params['seed']==seed
 _,_,_,folds=W.B._prepared();designs={}
 for fold in folds:
  original,query=W.design(fold);atr,ate,yy,qid,order=W.ordered_training(fold);matrix=W.training_matrix(atr,yy,qid)
  assert (yy<0).any()and np.array_equal(matrix.get_label(),yy.astype(np.float32))and ate.equals(query)
  assert len(matrix.get_uint_info('group_ptr'))==len(order['cohorts'])+1
  # Shuffling initial input order reproduces the identical cohort-then-PID ordering.
  perm=np.arange(len(fold['tr']))[::-1];changed={**fold,'tr':fold['tr'].iloc[perm].copy(),'yy':np.asarray(fold['yy'])[perm]}
  old_design=W.design
  try:
   W.design=lambda _: (original.iloc[perm].copy(),query)
   a2,q2,y2,g2,o2=W.ordered_training(changed)
  finally:W.design=old_design
  assert a2.equals(atr)and q2.equals(ate)and np.array_equal(y2,yy)and np.array_equal(g2,qid)
  designs[str(fold['year'])]={'train_hash':W.B._matrix_hash(original),'query_hash':W.B._matrix_hash(ate),'training_target_hash':W.D.h(np.asarray(fold['yy'])),'columns':list(original),'train_rows':len(atr),'query_rows':len(ate),'training_order':order}
  for seed in p['seeds']:
   old=next(r for r in W.D.references()[seed]['rows']if r['season']==fold['year']);assert list(original)==old['audit']['input_columns'];assert [W.B._hash(k)for k in W.B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
   anchor=next(r for r in W.anchors()[(p['reference_id'],seed)]['rows']if r['season']==fold['year']);assert anchor['predictions']==old['predictions']and anchor['stack']==old['stack']
 first=folds[0];atr,ate,yy,qid,_=W.ordered_training(first)
 reject(lambda:W.training_matrix(atr,yy,qid[::-1]));reject(lambda:W.training_matrix(atr,yy[:-1],qid))
 class SpyModel:
  feature_names=list(atr)
  def num_boosted_rounds(self):return 1200
  def save_config(self):return json.dumps({'learner':{'generic_param':{'device':'cuda:0'},'objective':{'name':'rank:pairwise'}}})
  def predict(self,data,iteration_range=None):assert iteration_range in [(0,200),(0,600),(0,1200)]and not len(data.get_label())and data.feature_names==list(ate);return np.zeros(data.num_row())
 def spy_train(params,data,num_boost_round):
  assert num_boost_round==1200 and data.num_row()==len(atr)and np.array_equal(data.get_label(),yy.astype(np.float32))and data.feature_names==list(atr);return SpyModel()
 saved=xgb.train
 try:
  xgb.train=spy_train;W.fit_native({'objective':'rank:pairwise'},atr,yy,qid)
 finally:xgb.train=saved
 reject(lambda:W.fit_native({},atr,yy,qid,eval_set=(ate,None)))
 spy=SpyModel()
 for bad in [0,199,201,1201]:reject(lambda bad=bad:W.predict_checkpoint(spy,ate,bad))
 for end in p['tree_checkpoints']:W.predict_checkpoint(spy,ate,end)
 with tempfile.TemporaryDirectory(dir=O)as tmp:
  reject(lambda:Q.save_immutable(Path(tmp),{'task_id':'bad.03'}));Q.save_immutable(Path(tmp),{'task_id':'good0p03'})
 matrix=pd.DataFrame({'a':[np.nan,np.nan,2.],'b':[0.,-0.,1.]});pred,_=W.B._canonical_predictions(matrix,np.array([1.,3.,9.]),['a','b','c']);assert np.array_equal(pred,[2.,2.,9.])
 a=np.array([1.,1.,3.,5.]);b=np.array([5.,5.,1.,3.]);order=np.array([3,1,0,2])
 for step in range(11):assert np.array_equal(rank_blend(a[order],b[order],step),rank_blend(a,b,step)[order])
 support={'version':xgb.__version__,'sources':sources,'source_designs':designs,'build_info':xgb.build_info(),'no_query_data_in_fit':True,'native_NaNs_verified':True,'negative_training_targets_preserved':True,'cohort_then_PID_order_invariance':True,'GPU_fixture_protocol':'After F successful completion, run two unscored two-tree objective compatibility probes on original pre2019 fold2012 train data; verify actual CUDA device and negative targets. No scores.'}
 path=O/'runtime_support.json'
 if path.exists():assert json.loads(path.read_text())==support
 else:Q.atomic_json(path,support)
 proof={'passed':True,'CPU_and_source_checks_passed':True,'fit_query_exclusion_fixture':True,'checkpoint_range_guards':True,'identical_input_ties':True,'safe_unique_task_ids':True,'rank_blend_order_invariance':True,'exact_B_and_E_anchor_inputs':True,'registered_tasks':1731,'negative_targets_unchanged':True,'cohort_group_order_and_row_replay':True}
 Q.atomic_json(O/'tests.json',proof)
 if gpu_fixture:
  probes=[]
  for objective in p['grid']['objective']:
   v=next(v for v in p['variants'][1:]if v['objective']==objective and v['max_depth']==7 and v['min_child_weight']==1 and v['reg_lambda']==1 and v['subsample']==.7 and v['colsample_bytree']==.7 and v['learning_rate']==.1)
   kwargs=W.params(v,0);model=W.fit_native(kwargs,atr,yy,qid,rounds=2);effective=json.loads(model.save_config());W.validate_effective(effective,kwargs);assert effective['learner']['generic_param']['device']=='cuda:0'
   for end in [1,2]:W.predict_checkpoint(model,ate,end,allowed=[1,2])
   reject(lambda:W.predict_checkpoint(model,ate,3,allowed=[3]));probes.append({'objective':objective,'iterations':2,'actual_device':'cuda:0','constructor':kwargs,'effective_constructor':effective,'negative_labels_present':bool((yy<0).any()),'scored':False})
  Q.atomic_json(O/'gpu_fixture.json',{'passed':True,'fixtures':probes,'models_scored':0,'frozen_manifest_sha256':hashlib.sha256((R/'frozen.json').read_bytes()).hexdigest()})
 print(json.dumps({**proof,'GPU_fixtures_run':gpu_fixture}),flush=True)
if __name__=='__main__':
 import sys
 prepare(gpu_fixture='--gpu-fixture'in sys.argv)
