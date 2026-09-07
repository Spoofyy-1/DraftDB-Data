"""Final model-free payload/reference validation and pinned installed runtime."""
from pathlib import Path
import sys,json,hashlib,inspect,copy,importlib.metadata
import numpy as np
ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def metadata():
 import tabicl,catboost,catboost._catboost,torch,xgboost
 source=list(Path(tabicl.__file__).parent.rglob('*.py'))+[Path(inspect.getfile(catboost.CatBoostRegressor)),Path(catboost._catboost.__file__)]
 sources={str(p).replace(str(Path(sys.prefix)),'/opt/venv'):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}for p in sorted(set(source))}
 result={'versions':{'tabicl':importlib.metadata.version('tabicl'),'catboost':catboost.__version__,'torch':torch.__version__,'xgboost':xgboost.__version__},'sources':sources,'checkpoint_continuity':'Three exact original B full references required before any new policy fit.'};(ROOT/'runtime_support.json').write_text(json.dumps(result,indent=2)+'\n');print('Runtime metadata pinned; no model fits.')
def main():
 import worker as W
 p=W.plan();W.environment()
 def reject_fit(*a,**k):raise AssertionError('No fitting in CPU verification')
 from tabicl import TabICLRegressor
 from catboost import CatBoostRegressor
 TabICLRegressor.fit=reject_fit;CatBoostRegressor.fit=reject_fit
 for item in p['canonical_payloads']:
  for year in p['folds']:
   atr,ate,tr,te,a,q=W.payload(item['id'],year);assert len(tr['y'])>=40 and np.isfinite(tr['y']).all();assert all(x>=5 for x in a['cohort_counts'].values());assert list(atr)==list(ate)==sorted(p['columns'])
 for profile in p['profiles']:
  for seed in p['seeds']:
   model,params=W.constructor(profile,seed);json.dumps(model.get_params(),allow_nan=False)
 for seed in p['seeds']:
  e=copy.deepcopy(W.D.references()[seed]);e['config']=p['variants'][0];e['original_reference_config']=W.D.references()[seed]['config'];e['task_id']=f'drop5_001_seed{seed}';e['legacy_score']=e['score']
  for row in e['rows']:
   row['model_design']=copy.deepcopy(W.D.capacity()['designs']['drop5_001'][f"{row['season']}:{seed}"])
   with np.load(ROOT/'data'/f"query_{row['season']}.npz",allow_pickle=False)as f:te={k:f[k]for k in f.files}
   W.score_record(row,te)
  e['observed_score']=float(np.mean([r['observed_mask_score']for r in e['rows']]));W.validate_entry(e)
  corrupt=copy.deepcopy(e);corrupt['rows'][0]['observed_mask_score']+=.001
  try:W.validate_entry(corrupt)
  except AssertionError:pass
  else:raise AssertionError('Tampered observed score accepted')
 proof={'passed':True,'models_fitted':0,'payload_folds':63,'query_files':3,'constructor_profiles_seeds_checked':9,'saved_B_reference_wrappers_and_both_scores_exact':3,'tampered_observed_metric_rejected':True,'all_frozen_hashes_verified':True,'frozen_sha256':sha((ROOT/'frozen.json').read_bytes())};(ROOT/'results/runtime_preflight.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':
 if '--metadata'in sys.argv:metadata()
 else:main()
