"""CPU-only equality check of actual pre-2019 ensemble views; no TabICL fit/predict."""
from pathlib import Path
import json,hashlib,inspect
import numpy as np
from sklearn.preprocessing import StandardScaler
from tabicl._sklearn.regressor import EnsembleGenerator,TransformToNumerical,TabICLRegressor
import worker as Y
R=Path(__file__).resolve().parent

def h(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=lambda a:a.tolist()).encode()).hexdigest()
p=Y.plan();E,bp,g,folds=Y.B._prepared();proof=[]
for context in p['contexts']:
 for fold in folds:
  atr,ate,_,_=Y.design(fold,context,p);encoder=TransformToNumerical(verbose=False);a=encoder.fit_transform(atr.astype(float));b=encoder.transform(ate.astype(float));y=StandardScaler().fit_transform(np.asarray(fold['yy']).reshape(-1,1)).flatten()
  for seed in p['seeds']:
   variants=[]
   for n in [64,128,256]:
    model,kwargs=Y.constructor(p,{'n_estimators':n},seed)
    gen=EnsembleGenerator(classification=False,n_estimators=n,norm_methods=kwargs['norm_methods'],feat_shuffle_method=model.get_params()['feat_shuffle_method'],outlier_threshold=kwargs['outlier_threshold'],random_state=seed)
    gen.fit(a,y);views=gen.transform(b,mode='both');vh=hashlib.sha256()
    for name,arrays in views.items():
     vh.update(name.encode())
     for array in arrays:vh.update(str(array.shape).encode());vh.update(str(array.dtype).encode());vh.update(array.tobytes())
    variants.append({'requested':n,'effective':sum(map(len,gen.ensemble_configs_.values())),'features':int(gen.n_features_in_),'config_hash':h(gen.ensemble_configs_),'permutation_hash':h(gen.feature_shuffles_),'transformed_views_hash':vh.hexdigest()})
   comparable=[{k:v for k,v in r.items() if k!='requested'} for r in variants]
   proof.append({'context':context,'fold':fold['year'],'seed':seed,'identical':all(r==comparable[0] for r in comparable),'variants':variants})
out={'TabICL_models_fitted':0,'GPU_predictions':0,'all_64_128_256_identical':all(r['identical'] for r in proof),'proofs':proof,'source_file':inspect.getfile(EnsembleGenerator),'source_sha256':hashlib.sha256(Path(inspect.getfile(EnsembleGenerator)).read_bytes()).hexdigest()}
(R/'results/capacity_check.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='proofs'}))
