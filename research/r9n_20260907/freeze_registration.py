"""Root launch gate: all actual input preflights and exact cap aliases first."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f:f.write(json.dumps(x,indent=2,allow_nan=False)+'\n')
p=read(R/'plan.json');c=read(R/'results/cpu_preflight.json');scan=read(R/'results/preprocessing_scan.json')
assert sha(R/'plan.json')=='edea708ee96d5d4dd9daaa0e72f318f8dec3813a446eb2b39ebfdec7f1945f48'
assert sha(R/'code/protocol.json')=='953dc21703999afdf5e181e78b02da2d41da1da0902610c95ef019a08ff6dfaf'
assert p['task_count']==51 and p['model_fits']==153 and p['stack_recipe_count']==1358
assert len(p['active_profiles'])==18 and len(p['profile_mapping'])==23 and not p['rejected_profiles']
assert c['passed'] and c['model_fits']==0 and c['tasks_checked']==51 and c['runtime_sources_checked']==111
assert c['plan_sha256']==sha(R/'plan.json') and c['preprocessing_scan_sha256']==sha(R/'results/preprocessing_scan.json')==p['preprocessing_scan_sha256']
assert c['reference_gate']['passed'] and c['reference_gate']['exact_M_recipe_prediction_records']==24
assert c['reference_gate']['exact_member_fold_seed_vectors']==90 and c['reference_gate']['new_control_fits']==0
assert scan['model_fits']==0 and scan['GPU_predictions']==0 and read(R/'root_review.json')['passed']
aliases=[]
for requested,representative in p['profile_mapping'].items():
    x,y=scan['designs'][requested],scan['designs'][representative]
    assert set(x)==set(y)=={f'{yr}:{seed}' for yr in [2012,2013,2014] for seed in [0,101,202]}
    for key in x:
        a,b=x[key],y[key]
        # Independent structural comparison: preserve every numerical/layout field.
        for field in a:
            if field in ['profile_id','warnings']:continue
            if field in ['parameters','effective_constructor']:
                av={k:v for k,v in a[field].items() if k!='n_estimators'}
                bv={k:v for k,v in b[field].items() if k!='n_estimators'}
                assert av==bv,(requested,key,field)
            else:assert a[field]==b[field],(requested,key,field)
    if requested!=representative:aliases.append({'requested':requested,'representative':representative,'all_nine_designs_exact':True})
assert len(aliases)==5
save(R/'root_capacity_verification.json',{'passed':True,'aliases':aliases,'duplicate_fits_avoided':45,'requested_fits':198,'actual_new_fits':153,'no_score_values_used':True,'original_requests_retained':True})
files=[]
for directory,count in [('code',6),('inputs',153),('source_inputs',18),('source_refs',13),('scoring',3)]:
    found=sorted(x for x in (R/directory).rglob('*') if x.is_file() and '__pycache__' not in x.parts)
    assert len(found)==count,(directory,len(found));files.extend(found)
for name in ['plan.json','README.md','cpu_fixture_proof.json','root_review.json','root_capacity_verification.json','build_inputs.py','reuse_controls.py','research.py','postprocess.py','stack_predictions.py','cpu_preflight.py','run_task_sandbox.sh','test_n.py','prepare_protocol.py','capacity.py','freeze_registration.py','results/preprocessing_scan.json']:
    files.append(R/name)
assert len(set(files))==210
save(R/'frozen.json',{'files':{str(x.relative_to(R)):sha(x) for x in sorted(files)},'target_percent':55,'no_2019plus_scoring':True})
save(R/'launch_authorization.json',{'model_fits_authorized':True,'authorization':'User-directed ongoing GPU stacking toward55%; root reviewed development-only profile study and exact cap aliases.','plan_sha256':sha(R/'plan.json'),'frozen_sha256':sha(R/'frozen.json'),'cpu_preflight_sha256':sha(R/'results/cpu_preflight.json'),'new_jobs':51,'new_TabICL_fits':153,'requested_new_fits':198,'exact_duplicate_fits_avoided':45,'reused_member_records':6,'workers':4,'limits':{'runtime_seconds':7200,'memory_gib':140,'cpu_quota_percent':2200},'automatic_retry':False,'no_benchmark_evaluation':True})
print(json.dumps({'frozen_files':210,'frozen_sha256':sha(R/'frozen.json'),'plan_sha256':sha(R/'plan.json'),'cpu_preflight_sha256':sha(R/'results/cpu_preflight.json'),'authorization_sha256':sha(R/'launch_authorization.json'),'aliases':aliases}))
