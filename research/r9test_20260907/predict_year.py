"""Single audited-year process: training inputs only, write predictions, never score."""
from pathlib import Path
import json,hashlib,os
import numpy as np
import pandas as pd
from model_core import build_payload,predict_one,fixed_rank_average,values_hash
CODE=Path('/code');BUNDLE=Path('/bundle');OUT=Path('/predictions')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 recipe=json.loads((CODE/'recipe.json').read_text());approval=json.loads((CODE/'approval.json').read_text());frozen=json.loads((CODE/'frozen.json').read_text());manifest=json.loads((BUNDLE/'manifest.json').read_text());year=manifest['year'];assert year in recipe['years']
 assert approval['scoring_policy_sha256']==recipe['scoring_policy_sha256']
 assert approval['approved']and approval['audited_feature_cutoffs']and approval['audited_label_cutoffs']and approval['query_population_frozen']and approval['reference_gate_passed']
 assert sha(CODE/'frozen.json')==approval['frozen_code_sha256']
 assert sha(CODE/'recipe.json')==approval['recipe_sha256']and sha(BUNDLE/'manifest.json')==approval['year_manifest_sha256'][str(year)]
 for name,digest in frozen['files'].items():assert sha(CODE/name)==digest
 runtime=json.loads((CODE/'runtime_support.json').read_text());assert runtime['checkpoint_files']
 for path,info in {**runtime['sources'],**runtime['checkpoint_files']}.items():assert sha(Path(path))==info['sha256']
 assert manifest['label_cutoff']==year-1 and manifest['recipe_sha256']==sha(CODE/'recipe.json');assert set(manifest['files'])=={'train_features.csv','query_features.csv','train_labels.csv'}
 data={}
 for name,meta in manifest['files'].items():
  assert sha(BUNDLE/name)==meta['sha256'];frame=pd.read_csv(BUNDLE/name,dtype={'pid':str},float_precision='round_trip');assert len(frame)==meta['rows']and list(frame)==meta['columns'];data[name]=frame
 atr,ate,target,trainpids,querypids,audit=build_payload(data['train_features.csv'],data['query_features.csv'],data['train_labels.csv'],recipe,year)
 assert audit['query_PID_hash']==manifest['canonical_query_PID_hash'];results=[predict_one(atr,ate,target,querypids,recipe,seed)for seed in recipe['seeds']]
 vectors=[np.array([p['score']for p in r['predictions']])for r in results];average=fixed_rank_average(vectors);payload={'year':year,'input_manifest_sha256':sha(BUNDLE/'manifest.json'),'recipe_sha256':sha(CODE/'recipe.json'),'frozen_code_sha256':sha(CODE/'frozen.json'),'audit':audit,'seed_results':results,'fixed_rank_average':[{'pid':pid,'score':float(x)}for pid,x in zip(querypids,average)],'fixed_rank_average_hash':values_hash(average),'test_outcomes_accessed':False,'evaluation_scores_computed':False}
 frame=pd.DataFrame({'pid':querypids,'season':year,**{f'seed_{seed}':vector for seed,vector in zip(recipe['seeds'],vectors)},'score':average});assert list(frame)==['pid','season','seed_0','seed_101','seed_202','score']
 csv=frame.to_csv(index=False,float_format='%.17g').encode();payload['prediction_csv_sha256']=hashlib.sha256(csv).hexdigest();raw=(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 for name,content in [('predictions.json',raw),('predictions.csv',csv)]:
  path=OUT/name;assert not path.exists(),'Never overwrite frozen predictions';temporary=OUT/(name+'.tmp');temporary.write_bytes(content);os.link(temporary,path);temporary.unlink()
 proof={'year':year,'rows':len(querypids),'seeds':recipe['seeds'],'predictions_sha256':hashlib.sha256(raw).hexdigest(),'predictions_csv_sha256':hashlib.sha256(csv).hexdigest(),'scoring_performed':False};(OUT/'completion.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
