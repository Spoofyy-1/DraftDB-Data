"""Only registered TabICL settings vary on the exact frozen44-column B design."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import importlib.util,json,hashlib,time,math,copy
import numpy as np
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r9d_frozen_b',R/'b_reference/worker.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P);B=P.B;X=P.X
_PLAN=None;_REF=None;_DESIGN={};_CAP=None

def h(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=lambda a:a.tolist()).encode()).hexdigest()
def normalize(value):
 if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
 if isinstance(value,float) and math.isinf(value):assert value>0;return 'disabled'
 return value

def load_plan():
 global _PLAN
 if _PLAN is None:
  p=json.loads((R/'plan.json').read_text());m=json.loads((R/'source_manifest.json').read_text())
  for name,sha in m['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==sha,name
  assert hashlib.sha256((R/'queue_runtime.py').read_bytes()).hexdigest()==m['verified_scheduler_sha256']
  assert p['diagnostic_only'] and p['no_confirmation_or_test_scoring']
  for key in ['folds','seeds','model_constructor','ordering_policy']:assert p[key]==P.load_plan()[key]
  _PLAN=p
 return _PLAN

def references():
 global _REF
 if _REF is None:_REF={r['seed']:r for r in json.loads((R/'references.json').read_text())['records']}
 return _REF

def capacity():
 global _CAP
 if _CAP is None:_CAP=json.loads((R/'results/capacity_check.json').read_text())
 return _CAP

def design(fold):
 y=fold['year']
 if y not in _DESIGN:
  p=load_plan();atr,ate,families,pair,ablation=P.design(fold,p['baseline_config']);old=next(r for r in references()[0]['rows'] if r['season']==y)
  assert list(atr)==list(ate)==old['audit']['input_columns'] and len(atr.columns)==44
  assert families==old['audit']['families'] and pair==old['audit']['pair_design'] and ablation==old['audit']['ablation']
  for key,value in fold['audit'].items():assert value==old['audit'][key]
  assert [B._hash(k) for k in B._exact_vector_keys(ate)]==old['audit']['canonical_prediction_ties']['row_vector_hashes']
  _DESIGN[y]=(atr,ate)
 return _DESIGN[y]

def constructor(setting,seed):
 from tabicl import TabICLRegressor
 p=load_plan();kwargs={**p['model_constructor'],'norm_methods':setting['norm_methods'],'outlier_threshold':float('inf') if setting['outlier_threshold']=='disabled' else float(setting['outlier_threshold']),'n_estimators':setting['n_estimators'],'random_state':seed}
 model=TabICLRegressor(**kwargs);actual=model.get_params(deep=False);assert all(actual[k]==v for k,v in kwargs.items())
 return model,normalize(kwargs),normalize(actual)

def fingerprint(gen,query):
 views=gen.transform(query,mode='both');sha=hashlib.sha256()
 for name,arrays in views.items():
  sha.update(name.encode())
  for array in arrays:
   assert np.isfinite(array).all();sha.update(str(array.shape).encode());sha.update(str(array.dtype).encode());sha.update(array.tobytes())
 return {'effective_estimators':sum(len(v) for v in gen.ensemble_configs_.values()),'effective_features':int(gen.n_features_in_),'ensemble_config_hash':h(gen.ensemble_configs_),'feature_permutation_hash':h(gen.feature_shuffles_),'ordered_methods':list(views),'transformed_views_hash':sha.hexdigest()}

def run_variant(vid,seed):
 start=time.time();p=load_plan();v=next(v for v in p['variants'] if v['id']==vid);s=p['settings_by_id'][vid];assert seed in p['seeds']
 E,bp,g,folds=B._prepared();os.environ['SEED_SHIFT']=str(seed);rows=[]
 for fold in folds:
  atr,ate=design(fold);model,kwargs,effective=constructor(s,seed)
  model.fit(atr.astype(float),fold['yy']);raw=np.asarray(model.predict(ate.astype(float)),dtype=float);assert len(raw)==len(ate) and np.isfinite(raw).all()
  # Exact fitted generator payload check against the pre-model CPU registration.
  from sklearn.utils.validation import validate_data
  query=validate_data(model,ate.astype(float),reset=False,dtype=None,skip_check_array=True);fp=fingerprint(model.ensemble_generator_,model.X_encoder_.transform(query))
  expected=capacity()['designs'][vid][f"{fold['year']}:{seed}"];assert fp==expected['generator'] and effective==expected['effective_constructor']
  pred,ties=B._canonical_predictions(ate,raw,fold['te'].pid.tolist());score=B.rho(pred,fold['truth']);old=next(r for r in references()[seed]['rows'] if r['season']==fold['year'])
  audit={**copy.deepcopy(old['audit']),'registered_model_parameters':kwargs,'canonical_prediction_ties':ties}
  rows.append({'season':fold['year'],'k':fold['k'],'n':len(ate),'ntrain':len(atr),'cutoff':fold['cutoff'],'max_label_season':fold['audit']['max_label_season'],'stack':score,'draft':old['draft'],'members':{'tabicl':score},'audit':audit,'model_design':{'generator':fp,'effective_constructor':effective},'predictions':[{'pid':pid,'score':float(a),'raw_score':float(b)} for pid,a,b in zip(fold['te'].pid,pred,raw)]})
 return {'config':v,'seed':seed,'task_id':f'{vid}_seed{seed}','rows':rows,'score':float(np.mean([r['stack'] for r in rows])),'seconds':round(time.time()-start,2),'diagnostic_only':True}

def validate_entry(entry,p=None):
 p=p or load_plan();v=next(v for v in p['variants'] if v['id']==entry['config']['id']);seed=entry['seed'];s=p['settings_by_id'][v['id']]
 assert 'error'not in entry and entry['diagnostic_only'] and entry['config']==v and seed in p['seeds'] and entry['task_id']==f"{v['id']}_seed{seed}"
 assert [r['season'] for r in entry['rows']]==p['folds'] and math.isfinite(entry['score']) and np.isclose(entry['score'],np.mean([r['stack'] for r in entry['rows']]),rtol=0,atol=1e-15)
 kwargs={**p['model_constructor'],'norm_methods':s['norm_methods'],'outlier_threshold':s['outlier_threshold'],'n_estimators':s['n_estimators'],'random_state':seed}
 for row,old in zip(entry['rows'],references()[seed]['rows']):
  B._validate_tie_record(row);a=copy.deepcopy(row['audit']);o=copy.deepcopy(old['audit']);assert a['registered_model_parameters']==kwargs
  a.pop('canonical_prediction_ties');o.pop('canonical_prediction_ties');o['registered_model_parameters']=kwargs;assert a==o
  for key in ['season','k','n','ntrain','cutoff','max_label_season']:assert row[key]==old[key]
  assert [v['pid'] for v in row['predictions']]==[v['pid'] for v in old['predictions']]
  expected=capacity()['designs'][v['id']][f"{row['season']}:{seed}"];assert row['model_design']==expected
 if v['id']==p['reference_id']:X.exact_reference(entry,references()[seed])

def summarize_matched(entries):
 p=load_plan();tasks={}
 for e in entries:
  validate_entry(e,p);key=(e['config']['id'],e['seed']);assert key not in tasks;tasks[key]=e
 missing=[f"{p['reference_id']}_seed{s}" for s in p['seeds'] if (p['reference_id'],s)not in tasks]
 common={'completed_tasks':len(tasks),'expected_tasks':p['execution']['task_count'],'reference_replays_passed':3-len(missing),'reference_replays_pending':missing,'interpretation_allowed':not missing,'diagnostic_only':True,'automatic_promotion':False,'metric':'Pre2019 mean fold Spearman, not classification accuracy'}
 if missing:return {**common,'configurations':[]}
 results=[]
 for v in p['variants']:
  if not all((v['id'],s)in tasks for s in p['seeds']):continue
  paired=[{'seed':s,'season':a['season'],'score':a['stack'],'baseline':b['stack'],'delta':a['stack']-b['stack']} for s in p['seeds'] for a,b in zip(tasks[(v['id'],s)]['rows'],tasks[(p['reference_id'],s)]['rows'])]
  results.append({'id':v['id'],'settings':p['settings_by_id'][v['id']],'mean_score':float(np.mean([r['score'] for r in paired])),'mean_delta_vs_baseline':float(np.mean([r['delta'] for r in paired])),
  'fold_deltas':{str(y):float(np.mean([r['delta'] for r in paired if r['season']==y])) for y in p['folds']},'seed_deltas':{str(s):float(np.mean([r['delta'] for r in paired if r['seed']==s])) for s in p['seeds']},'paired_rows':paired,'effective_estimator_counts':sorted({r['model_design']['generator']['effective_estimators'] for s in p['seeds'] for r in tasks[(v['id'],s)]['rows']})})
 return {**common,'baseline_score':float(np.mean([tasks[(p['reference_id'],s)]['score'] for s in p['seeds']])),'configurations':results,'requested_to_evaluated':p['requested_to_evaluated'],'seed_average_diagnostic':'Computed after model completion from all three saved canonical predictions with fixed equal weights; separate artifact.'}

def mean_saved_predictions(rows):
 assert len(rows)==3
 pids=[r['pid'] for r in rows[0]['predictions']];assert len(pids)==len(set(pids)) and all([r['pid'] for r in row['predictions']]==pids for row in rows)
 return pids,np.array([math.fsum(row['predictions'][i]['score'] for row in rows)/3 for i in range(len(pids))])

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
