"""Future authorized H prediction replay only; no2019+inputs or evaluation labels."""
from pathlib import Path
import json,hashlib,importlib.util
import numpy as np
import model_core as M
CODE=Path('/code');HR=Path('/h_reference');OUT=Path('/predictions')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 recipe=json.loads((CODE/'recipe.json').read_text());approval=json.loads((CODE/'reference_approval.json').read_text());assert approval['approved']and approval['recipe_sha256']==sha(CODE/'recipe.json')and approval['frozen_code_sha256']==sha(CODE/'frozen.json')
 for name,digest in json.loads((CODE/'frozen.json').read_text())['files'].items():assert sha(CODE/name)==digest
 runtime=json.loads((CODE/'runtime_support.json').read_text());assert runtime['checkpoint_files']
 for path,info in {**runtime['sources'],**runtime['checkpoint_files']}.items():assert sha(Path(path))==info['sha256']
 spec=importlib.util.spec_from_file_location('selected_H',HR/'worker.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H);H.plan();H.environment();assert sha(HR/'frozen.json')==recipe['selected_H_frozen_sha256']
 reference=json.loads((CODE/'reference_contract.json').read_text());bp,manifest,data,labels=H.B._load_inputs();assert data.draft_year.max()<=2018 and labels.season_end.max()<=2018;fields=recipe['physical_source_fields'];checks=[]
 for year in recipe['reference_gate']['years']:
  training=data[data.draft_year.between(2000,year-1)][['pid','draft_year','was_drafted']+fields];query=data[(data.draft_year==year)&(data.was_drafted==1)][['pid','draft_year']+fields];used=labels[labels.pid.isin(training.pid)&labels.ordinal.isin([1,2])&labels.season_end.le(year-1)&np.isfinite(labels.war)][['pid','draft_year','ordinal','season_end','war']]
  atr,ate,yy,pids,qids,audit=M.build_payload(training,query,used,recipe,year);original=next(x for x in recipe['reference_gate']['payload_audits']if x['year']==year)
  for x,y in [('training_matrix_hash','matrix_hash'),('target_hash','target_hash'),('training_PID_hash','pid_hash'),('source_fact_hash','source_fact_hash')]:assert audit[x]==original[y]
  for seed in recipe['seeds']:
   path=HR/'results/tasks'/f"{recipe['selected_H_variant']}_seed{seed}.json";assert sha(path)==reference['record_hashes'][str(seed)];old=next(r for r in json.loads(path.read_text())['rows']if r['season']==year)
   result=M.predict_one(atr,ate,yy,qids,recipe,seed);assert result['predictions']==old['predictions']and result['prediction_ties']==old['audit']['canonical_prediction_ties'];assert result['effective_constructor']==old['model_design']['effective_constructor']and result['effective_features']==old['model_design']['effective_features']and result['effective_estimators']==old['model_design']['effective_estimators'];checks.append({'year':year,'seed':seed,'all_raw_canonical_predictions_tie_audits_effective_settings_exact':True})
 proof={'passed':True,'recipe_sha256':sha(CODE/'recipe.json'),'checks':checks,'reference_seed_runs':3,'reference_fold_fits':9,'test_inputs_or_outcomes_accessed':False};(OUT/'reference_gate.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
