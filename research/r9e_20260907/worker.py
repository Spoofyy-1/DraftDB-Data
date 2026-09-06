"""Registered deterministic training-only target transforms on the exact B44 inputs."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import importlib.util,json,hashlib,time,math,copy
import numpy as np
from scipy.special import ndtr
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r9e_frozen_d',R/'d_reference/worker.py');D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D);B=D.B
h=D.h;normalize=D.normalize;fingerprint=D.fingerprint;mean_saved_predictions=D.mean_saved_predictions
_PLAN=None;_CAP=None;_DREF=None

def load_plan():
 global _PLAN
 if _PLAN is None:
  p=json.loads((R/'plan.json').read_text());m=json.loads((R/'source_manifest.json').read_text())
  for name,digest in m['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
  assert hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()==m['verified_scheduler_sha256']
  for key in ['folds','seeds','model_constructor','ordering_policy','baseline_config']:assert p[key]==D.load_plan()[key]
  assert p['diagnostic_only'] and p['no_confirmation_or_test_scoring'];_PLAN=p
 return _PLAN

def capacity():
 global _CAP
 if _CAP is None:_CAP=json.loads((R/'results/capacity_check.json').read_text())
 return _CAP

def d_references():
 global _DREF
 if _DREF is None:
  package=json.loads((R/'d_references.json').read_text());assert package['source']=='r9d' and package['source_frozen_sha256']=='a4189ca0c01786d5af1e2263e20224e311a96449edae27ae8e077bb5f67d97de'
  records=package['records'];assert len(records)==18
  for e in records:assert hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==package['record_hashes'][e['task_id']+'.json']
  _DREF={(e['config']['id'],e['seed']):e for e in records}
  assert set(_DREF)=={(v,s)for v in load_plan()['reference_ids']for s in load_plan()['seeds']}
 return _DREF

def design(fold):return D.design(fold)
def constructor(setting,seed):return D.constructor(setting,seed)
def array_hash(value):
 a=np.asarray(value);return h({'shape':list(a.shape),'dtype':str(a.dtype),'bytes_sha256':hashlib.sha256(a.tobytes()).hexdigest()})

def transform_target(original,name):
 y=np.asarray(original);before=y.copy();assert y.ndim==1 and len(y)>0 and np.isfinite(y).all()
 transforms={'identity':lambda a:a.copy(),'ndtr':ndtr,'signed_log1p':lambda a:np.sign(a)*np.log1p(np.abs(a)),'asinh':np.arcsinh,'tanh_half':lambda a:np.tanh(.5*a),'tanh':np.tanh,'clip1_5':lambda a:np.clip(a,-1.5,1.5),'clip2':lambda a:np.clip(a,-2,2)}
 assert name in transforms;z=np.asarray(transforms[name](y));assert np.array_equal(y,before) and z.shape==y.shape and np.isfinite(z).all()
 order=np.argsort(y,kind='stable');dy=np.diff(y[order]);dz=np.diff(z[order]);assert (dz>=0).all() and (dz[dy==0]==0).all()
 if name=='identity':assert array_hash(z)==array_hash(y)
 audit={'name':name,'original_hash':array_hash(y),'transformed_hash':array_hash(z),'n':len(y),'original_unique':int(len(np.unique(y))),'transformed_unique':int(len(np.unique(z))),'nondecreasing':True,'original_equal_ties_preserved':True,'additional_tied_adjacent_pairs':int(np.sum((dy>0)&(dz==0))),'uses_frozen_training_targets_only':True,'original_unchanged':True}
 return z,audit

def exact_d_reference(entry):
 p=load_plan();vid=entry['config']['id'];seed=entry['seed'];s=p['settings_by_id'][vid];assert vid in p['reference_ids'] and s['target_transform']=='identity' and s['outlier_threshold']==2
 old=d_references()[(vid,seed)];ds=D.load_plan()['settings_by_id'][vid]
 assert all(s[k]==ds[k] for k in ['norm_methods','outlier_threshold','n_estimators'])
 assert entry['score']==old['score'] and entry['seed']==old['seed']
 for row,ref in zip(entry['rows'],old['rows']):
  a=copy.deepcopy(row);t=a['audit'].pop('training_target_transform');assert t['name']=='identity' and t['original_hash']==t['transformed_hash']
  a['model_design'].pop('training_target_transform');assert a==ref

def run_variant(vid,seed):
 started=time.time();p=load_plan();v=next(v for v in p['variants']if v['id']==vid);s=p['settings_by_id'][vid];assert seed in p['seeds']
 _,_,_,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
 for fold in folds:
  atr,ate=design(fold);yy,target=transform_target(fold['yy'],s['target_transform']);model,kwargs,effective=constructor(s,seed)
  model.fit(atr.astype(float),yy);raw=np.asarray(model.predict(ate.astype(float)),dtype=float);assert len(raw)==len(ate) and np.isfinite(raw).all()
  from sklearn.utils.validation import validate_data
  query=validate_data(model,ate.astype(float),reset=False,dtype=None,skip_check_array=True);fp=fingerprint(model.ensemble_generator_,model.X_encoder_.transform(query));expected=capacity()['designs'][vid][f"{fold['year']}:{seed}"]
  model_design={'generator':fp,'effective_constructor':effective,'training_target_transform':target};assert model_design==expected
  pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth']);old=next(r for r in D.references()[seed]['rows']if r['season']==fold['year'])
  audit={**copy.deepcopy(old['audit']),'registered_model_parameters':kwargs,'canonical_prediction_ties':ties,'training_target_transform':target}
  rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':score,'draft':old['draft'],'members':{'tabicl':score},'audit':audit,'model_design':model_design,'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)}for pid,a,b in zip(fold['te'].pid,pred,raw)]})
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack']for r in rows])),'seconds':round(time.time()-started,2),'diagnostic_only':True}

def validate_entry(entry,p=None):
 p=p or load_plan();v=next(v for v in p['variants']if v['id']==entry['config']['id']);seed=entry['seed'];s=p['settings_by_id'][v['id']]
 assert 'error'not in entry and entry['diagnostic_only'] and entry['config']==v and seed in p['seeds'] and entry['task_id']==f"{v['id']}_seed{seed}"
 assert [r['season']for r in entry['rows']]==p['folds'] and math.isfinite(entry['score']) and np.isclose(entry['score'],np.mean([r['stack']for r in entry['rows']]),rtol=0,atol=1e-15)
 kwargs={**p['model_constructor'],'norm_methods':s['norm_methods'],'outlier_threshold':s['outlier_threshold'],'n_estimators':s['n_estimators'],'random_state':seed}
 for row,old in zip(entry['rows'],D.references()[seed]['rows']):
  B._validate_tie_record(row);a=copy.deepcopy(row['audit']);o=copy.deepcopy(old['audit']);assert a['registered_model_parameters']==kwargs
  expected=capacity()['designs'][v['id']][f"{row['season']}:{seed}"];assert row['model_design']==expected and a.pop('training_target_transform')==expected['training_target_transform']
  a.pop('canonical_prediction_ties');o.pop('canonical_prediction_ties');o['registered_model_parameters']=kwargs;assert a==o
  for key in ['season','k','n','ntrain','cutoff','max_label_season']:assert row[key]==old[key]
  assert [v['pid']for v in row['predictions']]==[v['pid']for v in old['predictions']]
 if v['id']in p['reference_ids']:exact_d_reference(entry)

def summarize_matched(entries):
 p=load_plan();tasks={}
 for e in entries:
  validate_entry(e,p);key=(e['config']['id'],e['seed']);assert key not in tasks;tasks[key]=e
 missing=[f'{vid}_seed{s}'for vid in p['reference_ids']for s in p['seeds']if(vid,s)not in tasks]
 common={'completed_tasks':len(tasks),'expected_tasks':p['execution']['task_count'],'reference_replays_passed':18-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,'metric':'Pre2019 mean fold Spearman, not classification accuracy'}
 if missing:return {**common,'configurations':[]}
 results=[]
 for v in p['variants']:
  if not all((v['id'],s)in tasks for s in p['seeds']):continue
  paired=[{'seed':s,'season':a['season'],'score':a['stack'],'baseline':b['stack'],'delta':a['stack']-b['stack']}for s in p['seeds']for a,b in zip(tasks[(v['id'],s)]['rows'],tasks[(p['reference_id'],s)]['rows'])]
  results.append({'id':v['id'],'settings':p['settings_by_id'][v['id']],'mean_score':float(np.mean([r['score']for r in paired])),'mean_delta_vs_baseline':float(np.mean([r['delta']for r in paired])),'fold_deltas':{str(y):float(np.mean([r['delta']for r in paired if r['season']==y]))for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r['delta']for r in paired if r['seed']==s]))for s in p['seeds']},'paired_rows':paired,'effective_estimator_counts':sorted({r['model_design']['generator']['effective_estimators']for s in p['seeds']for r in tasks[(v['id'],s)]['rows']})})
 return {**common,'baseline_score':float(np.mean([tasks[(p['reference_id'],s)]['score']for s in p['seeds']])),'configurations':results,'requested_to_evaluated':p['requested_to_evaluated'],'seed_average_diagnostic':'All three saved canonical predictions with fixed equal weights, separate artifact; never choose favorable seeds.'}

def seed_average(records):
 p=load_plan();tasks={(e['config']['id'],e['seed']):e for e in records};assert len(tasks)==len(records)==p['execution']['task_count'];_,_,_,folds=B._prepared();out=[]
 for v in p['variants']:
  rows=[]
  for fold in folds:
   rs=[next(r for r in tasks[(v['id'],s)]['rows'] if r['season']==fold['year']) for s in p['seeds']];pids=[r['pid'] for r in rs[0]['predictions']]
   assert pids==fold['te'].pid.tolist() and all([r['pid'] for r in row['predictions']]==pids for row in rs)
   pids,avg=mean_saved_predictions(rs)
   rows.append({'season':fold['year'],'stack':B.rho(avg,fold['truth']),'predictions':[{'pid':pid,'score':float(score)} for pid,score in zip(pids,avg)],'source_canonical_hashes':[row['audit']['canonical_prediction_ties']['canonical_prediction_hash'] for row in rs]})
  out.append({'id':v['id'],'settings':p['settings_by_id'][v['id']],'mean_score':float(np.mean([r['stack'] for r in rows])),'rows':rows})
 baseline=next(e for e in out if e['id']==p['reference_id'])
 for e in out:e['delta_vs_seed_averaged_baseline']=e['mean_score']-baseline['mean_score']
 return {'diagnostic_only':True,'separate_from_single_fit_means':True,'prespecified':p['seed_ensemble'],'no_favorable_seed_selection':True,'configurations':out}
