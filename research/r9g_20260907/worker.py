"""Native XGBoost on frozen B44 matrices; fixed checkpoints and no query data in fitting."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import importlib.util,json,hashlib,time,copy,math
import numpy as np
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r9g_frozen_d',R/'d_reference/worker.py');D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D);B=D.B
_PLAN=None;_ANCHORS=None;_ENV=None;_SUPPORT=None

def load_plan():
 global _PLAN
 if _PLAN is None:
  p=json.loads((R/'plan.json').read_text());m=json.loads((R/'source_manifest.json').read_text())
  for name,digest in m['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
  assert hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()==m['verified_scheduler_sha256']
  for key in ['folds','seeds','ordering_policy','baseline_config']:assert p[key]==D.load_plan()[key]
  assert p['tree_checkpoints']==[200,600,1200]and p['boost_rounds']==1200 and p['no_confirmation_or_test_scoring'];_PLAN=p
 return _PLAN

def anchors():
 global _ANCHORS
 if _ANCHORS is None:
  package=json.loads((R/'anchor_records.json').read_text());assert package['source']=='r9e'and package['frozen_sha256']=='7b9a43ec3148f5cfb5fa3b018b5c4f77b841a85cc7475261e1c48b58f301c34c'
  for e in package['records']:assert hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==package['record_hashes'][e['task_id']+'.json']
  _ANCHORS={(e['config']['id'],e['seed']):e for e in package['records']};assert len(_ANCHORS)==6
 return _ANCHORS

def design(fold):
 a,b=D.design(fold);assert a.shape[1]==b.shape[1]==44 and list(a)==list(b);assert not np.isinf(a.to_numpy(dtype=float)).any()and not np.isinf(b.to_numpy(dtype=float)).any();assert 'pid'not in a and 'draft_pick'not in a
 return a,b

def params(v,seed):
 p=load_plan();assert v['kind']=='xgboost'and seed in p['seeds'];return {**p['xgboost_fixed'],**{k:v[k]for k in p['grid']},'seed':seed}

def ordered_training(fold):
 atr,ate=design(fold);tr=fold['tr'];assert atr.index.equals(tr.index)
 order=np.asarray(sorted(range(len(tr)),key=lambda i:(int(tr.iloc[i].draft_year),hashlib.sha256(str(tr.iloc[i].pid).encode()).hexdigest())))
 assert sorted(order.tolist())==list(range(len(tr)))
 years=tr.iloc[order].draft_year.to_numpy(dtype=int);assert np.all(years[:-1]<=years[1:])
 qid=np.searchsorted(np.unique(years),years).astype(np.uint32);yy=np.asarray(fold['yy']);ordered=atr.iloc[order].copy();target=yy[order].copy()
 assert ordered.iloc[np.argsort(order)].equals(atr)and np.array_equal(target[np.argsort(order)],yy)
 forbidden={'pid','draft_year','actual_pick','draft_pick','qid'};assert not set(ordered)&forbidden
 proof={'policy':load_plan()['training_order'],'original_train_matrix_hash':B._matrix_hash(atr),'original_training_target_hash':D.h(yy),'original_train_pid_hash':B._hash(tr.pid.tolist()),'training_permutation':order.tolist(),'ordered_train_matrix_hash':B._matrix_hash(ordered),'ordered_training_target_hash':D.h(target),'ordered_train_pid_hash':B._hash(tr.iloc[order].pid.tolist()),'qid_hash':D.h(qid),'cohorts':[{ 'draft_year':int(y),'count':int(np.sum(years==y))}for y in np.unique(years)],'predictor_columns':list(ordered),'query_hash':B._matrix_hash(ate),'query_pid_hash':B._hash(fold['te'].pid.tolist()),'unchanged_values_labels_and_population':True}
 return ordered,ate,target,qid,proof

def training_matrix(atr,yy,qid):
 import xgboost as xgb
 yy=np.asarray(yy);qid=np.asarray(qid);assert yy.shape==qid.shape==(len(atr),)and np.isfinite(yy).all()and np.all(qid[:-1]<=qid[1:])and np.issubdtype(qid.dtype,np.integer)
 data=xgb.DMatrix(atr.astype(float),label=yy,qid=qid,missing=np.nan,nthread=2,feature_names=list(atr))
 assert np.array_equal(data.get_label(),yy.astype(np.float32))and data.feature_names==list(atr)
 group_ptr=data.get_uint_info('group_ptr');counts=np.bincount(qid);assert np.array_equal(np.diff(group_ptr),counts)and group_ptr[-1]==len(atr)
 return data

def fit_native(kwargs,atr,yy,qid,rounds=1200):
 # Query data and evaluation/early-stopping arguments cannot enter this API.
 import xgboost as xgb
 assert rounds in [2,1200];before=B._matrix_hash(atr);target=D.h(np.asarray(yy));data=training_matrix(atr,yy,qid)
 model=xgb.train(kwargs,data,num_boost_round=rounds)
 assert B._matrix_hash(atr)==before and D.h(np.asarray(yy))==target and model.num_boosted_rounds()==rounds and model.feature_names==list(atr)
 effective=json.loads(model.save_config());assert effective['learner']['generic_param']['device']=='cuda:0',effective['learner']['generic_param']
 assert effective['learner']['objective']['name']==kwargs['objective']
 return model

def validate_effective(effective,kwargs):
 learner=effective['learner'];generic=learner['generic_param'];booster=learner['gradient_booster'];tree=booster['tree_train_param']
 assert generic['device']=='cuda:0'and int(generic['nthread'])==2 and int(generic['seed'])==kwargs['seed']
 assert learner['objective']['name']==kwargs['objective']and booster['gbtree_train_param']['tree_method']=='hist'
 for requested,saved in [('max_depth','max_depth'),('min_child_weight','min_child_weight'),('reg_lambda','lambda'),('subsample','subsample'),('colsample_bytree','colsample_bytree'),('learning_rate','eta')]:
  assert np.isclose(float(tree[saved]),kwargs[requested],rtol=2e-7,atol=1e-9),(requested,tree[saved],kwargs[requested])

def predict_checkpoint(model,ate,end,allowed=None):
 import xgboost as xgb
 allowed=load_plan()['tree_checkpoints']if allowed is None else allowed
 assert end in allowed and isinstance(end,int)and 0<end<=model.num_boosted_rounds()
 query=xgb.DMatrix(ate.astype(float),missing=np.nan,nthread=2,feature_names=list(ate))
 assert len(query.get_label())==0
 raw=np.asarray(model.predict(query,iteration_range=(0,end)),dtype=float);assert raw.shape==(len(ate),)and np.isfinite(raw).all();return raw

def support():
 global _SUPPORT
 if _SUPPORT is None:_SUPPORT=json.loads((R/'results/runtime_support.json').read_text())
 return _SUPPORT

def environment():
 global _ENV
 if _ENV is None:
  import xgboost
  x=support();assert xgboost.__version__==x['version']=='3.4.1'
  for path,digest in x['sources'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest['sha256']
  _ENV={'xgboost_version':x['version'],'source_hashes':x['sources']}
 return _ENV

def run_variant(vid,seed):
 p=load_plan();v=next(v for v in p['variants']if v['id']==vid)
 if vid==p['reference_id']:return D.run_variant(vid,seed)
 started=time.time();env=environment();_,_,_,folds=B._prepared();rows=[]
 for fold in folds:
  atr,ate,yy,qid,order=ordered_training(fold);kwargs=params(v,seed);model=fit_native(kwargs,atr,yy,qid);effective=json.loads(model.save_config());validate_effective(effective,kwargs);checkpoints=[]
  for end in p['tree_checkpoints']:
   raw=predict_checkpoint(model,ate,end);pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth'])
   checkpoints.append({'ntree_end':end,'iteration_range':[0,end],'stack':score,'canonical_prediction_ties':ties,'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)}for pid,a,b in zip(fold['te'].pid,pred,raw)]})
  old=next(r for r in D.references()[seed]['rows']if r['season']==fold['year']);audit=copy.deepcopy(old['audit']);audit.pop('canonical_prediction_ties');audit['registered_model_parameters']=kwargs
  rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':checkpoints[-1]['stack'],'draft':old['draft'],'members':{'xgboost1200':checkpoints[-1]['stack']},'audit':audit,'training_target_hash':D.h(np.asarray(fold['yy'])),'training_order':order,'tree_count':model.num_boosted_rounds(),'feature_names':model.feature_names,'effective_constructor':effective,'evaluation_sets':[],'checkpoints':checkpoints})
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack']for r in rows])),'seconds':round(time.time()-started,2),'environment':env,'diagnostic_only':True,'score_checkpoint':1200}

def validate_entry(entry,p=None):
 p=p or load_plan();vid=entry['config']['id'];v=next(v for v in p['variants']if v['id']==vid);seed=entry['seed'];assert entry['config']==v and seed in p['seeds']and entry['task_id']==f'{vid}_seed{seed}'and 'error'not in entry
 if vid==p['reference_id']:D.validate_entry(entry);return
 assert entry['environment']==environment()and entry['diagnostic_only']and entry['score_checkpoint']==1200
 assert [r['season']for r in entry['rows']]==p['folds'] and math.isfinite(entry['score'])and np.isclose(entry['score'],np.mean([r['stack']for r in entry['rows']]),rtol=0,atol=1e-15)
 kwargs=params(v,seed)
 for row,old in zip(entry['rows'],D.references()[seed]['rows']):
  assert row['training_target_hash']==support()['source_designs'][str(row['season'])]['training_target_hash']
  validate_effective(row['effective_constructor'],kwargs)
  assert row['effective_constructor']['learner']['objective']['name']==v['objective']
  assert row['training_order']==support()['source_designs'][str(row['season'])]['training_order']
  assert row['tree_count']==1200 and row['feature_names']==old['audit']['input_columns']and row['evaluation_sets']==[]
  a=copy.deepcopy(row['audit']);o=copy.deepcopy(old['audit']);o.pop('canonical_prediction_ties');o['registered_model_parameters']=kwargs;assert a==o
  for key in ['season','k','n','ntrain','cutoff','max_label_season']:assert row[key]==old[key]
  assert [cp['ntree_end']for cp in row['checkpoints']]==p['tree_checkpoints']and row['stack']==row['checkpoints'][-1]['stack']
  for cp in row['checkpoints']:
   assert cp['iteration_range']==[0,cp['ntree_end']]and math.isfinite(cp['stack'])and [x['pid']for x in cp['predictions']]==[x['pid']for x in old['predictions']]
   assert cp['canonical_prediction_ties']['row_vector_hashes']==old['audit']['canonical_prediction_ties']['row_vector_hashes']
   B._validate_tie_record({**row,'predictions':cp['predictions'],'audit':{**row['audit'],'canonical_prediction_ties':cp['canonical_prediction_ties']}})

def summarize_matched(entries):
 p=load_plan();tasks={}
 for e in entries:
  validate_entry(e,p);key=(e['config']['id'],e['seed']);assert key not in tasks;tasks[key]=e
 missing=[f"{p['reference_id']}_seed{s}"for s in p['seeds']if(p['reference_id'],s)not in tasks]
 common={'completed_tasks':len(tasks),'expected_tasks':p['execution']['task_count'],'reference_replays_passed':3-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,'metric':'Pre2019 mean-fold Spearman, not classification accuracy','progress_checkpoint':1200}
 if missing:return {**common,'configurations':[]}
 configs=[]
 for v in p['variants']:
  if v['id']==p['reference_id']or not all((v['id'],s)in tasks for s in p['seeds']):continue
  checkpoints=[]
  for end in p['tree_checkpoints']:
   pairs=[{'seed':s,'season':row['season'],'score':next(cp['stack']for cp in row['checkpoints']if cp['ntree_end']==end),'baseline':old['stack']}for s in p['seeds']for row,old in zip(tasks[(v['id'],s)]['rows'],tasks[(p['reference_id'],s)]['rows'])]
   for row in pairs:row['delta']=row['score']-row['baseline']
   checkpoints.append({'ntree_end':end,'mean_score':float(np.mean([r['score']for r in pairs])),'mean_delta_vs_baseline':float(np.mean([r['delta']for r in pairs])),'fold_deltas':{str(y):float(np.mean([r['delta']for r in pairs if r['season']==y]))for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r['delta']for r in pairs if r['seed']==s]))for s in p['seeds']},'paired_rows':pairs})
  configs.append({'id':v['id'],'settings':v,'mean_score':checkpoints[-1]['mean_score'],'mean_delta_vs_baseline':checkpoints[-1]['mean_delta_vs_baseline'],'fold_deltas':checkpoints[-1]['fold_deltas'],'seed_deltas':checkpoints[-1]['seed_deltas'],'checkpoints':checkpoints})
 return {**common,'baseline_score':float(np.mean([tasks[(p['reference_id'],s)]['score']for s in p['seeds']])),'configurations':configs,'blend_diagnostics':'Fixed rank blends of every checkpoint with both registered anchors, all alpha steps and all seeds, computed from saved predictions after fits.'}
