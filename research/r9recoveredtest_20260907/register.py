"""Freeze a single archived-identity adaptation before GPU fitting or scoring."""
from pathlib import Path
import json,time
from verify import ROOT,sha,read,save_new

def main():
 inp=read(ROOT/'inputs_manifest.json');p=read(ROOT/'code/protocol.json');c=read(ROOT/'results/cpu_preflight.json')
 assert inp['all7_query_arrays_exact_to_prior_stacktest'] and inp['all42_training_label_arrays_exact_to_verified_export']
 assert inp['actual_model_fits']==inp['benchmark_scores_computed']==0
 assert c['passed'] and len(c['tasks'])==7 and c['actual_model_fits']==0
 assert p['outer_years']==list(range(2019,2026)) and p['target_modes']==['prefix5']
 assert p['primary_architecture']=='recovered_gen11' and p['primary_prediction_set']=='family_seed_rank_average'
 assert sha(ROOT/'archived_recipe.json')=='45447a0d6a53bffb94e85fa8dabd0c24f1189459cb54b3430064483336a563c0'
 assert read(ROOT/'controller_fixture_proof.json')['passed']
 for name,h in inp['source_pins'].items():assert sha(name)==h,name
 for name,h in inp['code_files'].items():assert sha(ROOT/name)==h,name
 for task in inp['tasks']:
  d=ROOT/'inputs'/task['id'];assert sha(d/'manifest.json')==task['input_manifest_sha256']
  m=read(d/'manifest.json');pre=read(ROOT/'results/jobs'/task['id']/'preflight.json')
  assert pre['passed'] and pre['model_fits']==0 and pre['input_manifest_sha256']==task['input_manifest_sha256']
  assert pre['protocol_sha256']==sha(ROOT/'code/protocol.json')
  for name,h in m['files'].items():assert sha(d/name)==(h['sha256'] if isinstance(h,dict) else h)
 old=read(ROOT/'previous_test_result.json')
 plan={'study':'r9recoveredtest','frozen_before_fits_at':time.time(),'years':list(range(2019,2026)),'tasks':inp['tasks'],'workers':4,'model_fits':182,
       'primary_recipe':'recovered_gen11','primary_mode':'family_seed_rank_average','selection_basis':'Archived gen11 identity, not benchmark scores','benchmark_selection_allowed':False,
       'target_mode':'prefix5','training_start_year':2007,'seeds':[0,101,202],
       'horizons':{'2019':5,'2020':5,'2021':5,'2022':4,'2023':3,'2024':2,'2025':1},
       'answer_hashes':{str(r['season']):r['answer_sha256'] for r in old['rows']},
       'benchmark_answer_hash_source':'Previously completed frozen test result; no new answer-file access during preparation',
       'primary_metric':'Mean all seven full-available-pool Spearman correlations; undefined year means aggregate undefined',
       'matched_years_secondary':list(range(2020,2026)),
       'controls':'Fixed prior-baseline routing, always-rich and individual members; diagnostics only, no benchmark selection',
       'archived_recipe_sha256':sha(ROOT/'archived_recipe.json'),'inputs_manifest_sha256':sha(ROOT/'inputs_manifest.json'),
       'limitations':p['limitations']+['Main scorer retains inherited missing outcome components as zero; observed target subset reported separately.','2019–2025 are historically reused benchmark years, not an untouched holdout.','Fixed family-seed rank average is an explicit adaptation; original historical seed/runtime and257inputbytes were not recovered.','Full means the provided incomplete player pool.','Verified training label coverage ends2022; allowed later seasons are unavailable.']}
 save_new(ROOT/'plan.json',plan)
 names=['plan.json','inputs_manifest.json','README.md','archived_recipe.json','legacy_AUDIT.md','previous_test_result.json','verify.py','research.py','score_frozen.py','test_controller.py','controller_fixture_proof.json','register.py','prepare_inputs.py','run_task_sandbox.sh','cpu_preflight.py','cpu_fixture_proof.json','results/cpu_preflight.json']
 paths=[ROOT/x for x in names]
 for directory in ['code','inputs','label_provenance','dashboard']:
  paths += [x for x in (ROOT/directory).rglob('*') if x.is_file() and '__pycache__' not in x.parts]
 paths += sorted((ROOT/'results/jobs').glob('*/preflight.json'))
 assert len(paths)==len(set(paths))
 save_new(ROOT/'frozen.json',{'files':{str(x.relative_to(ROOT)):sha(x) for x in sorted(paths)},'primary_fixed_before_fits':True,'private_inputs_excluded_from_publication':True})
 save_new(ROOT/'launch_authorization.json',{'model_fits_authorized':True,'benchmark_scoring_authorized':True,'authorization':'User explicitly requested2019–2025 testing and recovery of the original stack; latest steering prioritizes that fixed comparison over further2012–2014selection.','plan_sha256':sha(ROOT/'plan.json'),'frozen_sha256':sha(ROOT/'frozen.json'),'cpu_preflight_sha256':sha(ROOT/'results/cpu_preflight.json'),'jobs':7,'fits':182,'workers':4,'limits':{'runtime_seconds':7200,'memory_gib':140,'cpu_quota_percent':2200},'automatic_retry':False,'all_predictions_required_before_answers':True,'benchmark_model_selection_allowed':False})
 print(json.dumps({'frozen_files':len(paths),'plan_sha256':sha(ROOT/'plan.json'),'frozen_sha256':sha(ROOT/'frozen.json'),'authorization_sha256':sha(ROOT/'launch_authorization.json'),'model_fits':182}))
if __name__=='__main__':main()
