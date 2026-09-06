"""Exact model-free preprocessing/ensemble deduplication before registration freeze."""
from pathlib import Path
import json,hashlib,inspect,importlib.metadata,warnings
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import validate_data
from tabicl import TabICLRegressor
from tabicl._sklearn.preprocessing import EnsembleGenerator,TransformToNumerical,PreprocessingPipeline,OutlierRemover
import worker as W
R=Path(__file__).resolve().parent;p=W.load_plan();E,bp,g,folds=W.B._prepared();designs={s['id']:{} for s in p['requested_grid']};warning_counts={}
for fold in folds:
 atr,ate=W.design(fold)
 for seed in p['seeds']:
  for setting in p['requested_grid']:
   model,kwargs,effective=W.constructor(setting,seed);a,y=validate_data(model,atr.astype(float),fold['yy'],dtype=None,skip_check_array=True);query=validate_data(model,ate.astype(float),reset=False,dtype=None,skip_check_array=True)
   y=np.asarray(y,dtype=np.float32);ys=StandardScaler().fit_transform(y.reshape(-1,1)).flatten();encoder=TransformToNumerical(verbose=False);a=encoder.fit_transform(a);b=encoder.transform(query)
   params=model.get_params(deep=False)
   with warnings.catch_warnings(record=True) as logged:
    warnings.simplefilter('always');gen=EnsembleGenerator(classification=False,n_estimators=params['n_estimators'],norm_methods=params['norm_methods'],feat_shuffle_method=params['feat_shuffle_method'],outlier_threshold=params['outlier_threshold'],random_state=seed);gen.fit(a,ys);fp=W.fingerprint(gen,b)
   for message in logged:warning_counts[str(message.message)]=warning_counts.get(str(message.message),0)+1
   # Infinite learned bounds make clipping identity for every finite train/query value.
   if setting['outlier_threshold']=='disabled':
    for pre in gen.preprocessors_.values():
     clip=pre.outlier_remover_;assert np.isneginf(clip.lower_bounds_).all() and np.isposinf(clip.upper_bounds_).all()
     assert np.array_equal(clip.transform(pre.X_transformed_),pre.X_transformed_)
   designs[setting['id']][f"{fold['year']}:{seed}"]={'generator':fp,'effective_constructor':effective}
# Ignore only CPU preprocessing/request-count constructor fields, whose complete fitted
# model payload is separately compared byte-exact. All other effective options must agree.
signatures={}
for vid,items in designs.items():
 comparable={key:{'generator':value['generator'],'effective_constructor':{k:v for k,v in value['effective_constructor'].items() if k not in ['n_estimators','outlier_threshold']}} for key,value in items.items()};signatures[vid]=W.h(comparable)
representatives={};mapping={}
for s in p['requested_grid']:
 vid=s['id'];signature=signatures[vid];representatives.setdefault(signature,vid);mapping[vid]=representatives[signature]
keep=set(mapping.values());p['variants']=[v for v in p['variants'] if v['id']in keep];p['execution']['task_count']=len(p['variants'])*3;p['requested_to_evaluated']=mapping
sources={}
for cls in [TabICLRegressor,EnsembleGenerator]:
 path=Path(inspect.getfile(cls));sources[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
cap={'models_fitted':0,'GPU_predictions':0,'tabicl_version':importlib.metadata.version('tabicl'),'supported_named_normalizations':p['normalizations'],'factory_default_mixture_not_part_of_named_method_factorial':['none','power'],'disabled_threshold_encoding':'JSON string disabled converted to positive infinity only inside constructor','disabled_train_and_query_passthrough_verified':True,'sources':sources,'designs':designs,'requested_configurations':60,'distinct_configurations':len(keep),'tasks':p['execution']['task_count'],'requested_to_evaluated':mapping,'equality_signatures':signatures,'warning_counts':warning_counts}
(R/'results/capacity_check.json').write_text(json.dumps(cap,indent=2,allow_nan=False)+'\n');(R/'results/effective_plan.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in cap.items() if k not in ['designs','equality_signatures','warning_counts','requested_to_evaluated']}),flush=True)
