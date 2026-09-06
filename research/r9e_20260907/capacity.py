"""Exact model-free preprocessing/ensemble deduplication before registration freeze."""
from pathlib import Path
import json,hashlib,inspect,importlib.metadata,warnings
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import validate_data
from tabicl import TabICLRegressor
from tabicl._sklearn.preprocessing import EnsembleGenerator,TransformToNumerical,PreprocessingPipeline,OutlierRemover
import worker as W
R=Path(__file__).resolve().parent;p=W.load_plan();E,bp,g,folds=W.B._prepared();designs={s['id']:{} for s in p['requested_grid']};warning_counts={};invalid={}
for fold in folds:
 atr,ate=W.design(fold)
 for seed in p['seeds']:
  for setting in p['requested_grid']:
   model,kwargs,effective=W.constructor(setting,seed);a,y=validate_data(model,atr.astype(float),W.transform_target(fold['yy'],setting['target_transform'])[0],dtype=None,skip_check_array=True);query=validate_data(model,ate.astype(float),reset=False,dtype=None,skip_check_array=True)
   y=np.asarray(y,dtype=np.float32);ys=StandardScaler().fit_transform(y.reshape(-1,1)).flatten();encoder=TransformToNumerical(verbose=False);a=encoder.fit_transform(a);b=encoder.transform(query)
   params=model.get_params(deep=False)
   with warnings.catch_warnings(record=True) as logged:
    warnings.simplefilter('always');gen=EnsembleGenerator(classification=False,n_estimators=params['n_estimators'],norm_methods=params['norm_methods'],feat_shuffle_method=params['feat_shuffle_method'],outlier_threshold=params['outlier_threshold'],random_state=seed);gen.fit(a,ys)
    try:fp=W.fingerprint(gen,b)
    except AssertionError:
     views=gen.transform(b,mode='both');detail={'setting':setting,'fold':fold['year'],'seed':seed,'nonfinite':{name:[{'shape':list(x.shape),'nan':int(np.isnan(x).sum()),'inf':int(np.isinf(x).sum())} for x in arrays] for name,arrays in views.items()}}
     assert any(v['nan'] or v['inf'] for arrays in detail['nonfinite'].values() for v in arrays)
     detail['nonfinite_clipping_columns']={name:[str(atr.columns[i]) for i in np.flatnonzero(~np.isfinite(pre.outlier_remover_.lower_bounds_)|~np.isfinite(pre.outlier_remover_.upper_bounds_))] for name,pre in gen.preprocessors_.items()}
     invalid.setdefault(setting['id'],[]).append(detail)
     for message in logged:warning_counts[str(message.message)]=warning_counts.get(str(message.message),0)+1
     continue
   for message in logged:warning_counts[str(message.message)]=warning_counts.get(str(message.message),0)+1
   designs[setting['id']][f"{fold['year']}:{seed}"]={'generator':fp,'effective_constructor':effective,'training_target_transform':W.transform_target(fold['yy'],setting['target_transform'])[1]}
# Ignore only CPU preprocessing/request-count constructor fields, whose complete fitted
# model payload is separately compared byte-exact. All other effective options must agree.
signatures={}
for vid,items in designs.items():
 if vid in invalid:continue
 assert len(items)==9
 comparable={key:{'generator':value['generator'],'effective_constructor':{k:v for k,v in value['effective_constructor'].items() if k not in ['n_estimators','outlier_threshold']},'training_target_transform':{k:v for k,v in value['training_target_transform'].items() if k!='name'}} for key,value in items.items()};signatures[vid]=W.h(comparable)
representatives={};mapping={}
for s in p['requested_grid']:
 vid=s['id']
 if vid in invalid:mapping[vid]=None;continue
 signature=signatures[vid];representatives.setdefault(signature,vid);mapping[vid]=representatives[signature]
keep={v for v in mapping.values()if v is not None};assert all(v in keep for v in p['reference_ids']);p['excluded_before_fitting']={vid:{'reason':'nonfinite installed preprocessing in at least one registered fold/seed','contexts':len(details)}for vid,details in invalid.items()};p['variants']=[v for v in p['variants'] if v['id']in keep];p['execution']['task_count']=len(p['variants'])*3;p['requested_to_evaluated']=mapping
sources={}
for cls in [TabICLRegressor,EnsembleGenerator]:
 path=Path(inspect.getfile(cls));sources[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
import scipy.special._ufuncs as scipy_ufuncs
path=Path(scipy_ufuncs.__file__);sources[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
cap={'library_versions':{name:importlib.metadata.version(name) for name in ['numpy','scipy','scikit-learn','tabicl']},'invalid_configurations':invalid,'invalid_requested_configurations':len(invalid),'invalid_preprocessing_policy':'Exclude whole configuration before any model if any fold/seed has nonfinite CPU predictor/target payload; no source changes or imputation workaround.','models_fitted':0,'GPU_predictions':0,'tabicl_version':importlib.metadata.version('tabicl'),'supported_named_normalizations':p['normalizations'],'fixed_B44_inputs_before_transform':True,'query_truth_used_for_transform_or_dedupe':False,'training_target_transforms':p['target_transforms'],'sources':sources,'designs':designs,'requested_configurations':432,'distinct_configurations':len(keep),'tasks':p['execution']['task_count'],'requested_to_evaluated':mapping,'equality_signatures':signatures,'warning_counts':warning_counts}
(R/'results/capacity_check.json').write_text(json.dumps(cap,indent=2,allow_nan=False)+'\n');(R/'results/effective_plan.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in cap.items() if k not in ['designs','equality_signatures','warning_counts','requested_to_evaluated','invalid_configurations']}),flush=True)
