"""Root-reviewed launch registration after all isolated CPU preflights pass."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f:f.write(json.dumps(x,indent=2,allow_nan=False)+'\n')
p=read(R/'plan.json');c=read(R/'results/cpu_preflight.json')
assert sha(R/'plan.json')=='cebfe908d2cf0d03bf9f2de6052d30ef8c8a1b7f8a1a23948b782750cc5247e3'
assert sha(R/'code/protocol.json')=='5ffabcc9f0e4d00f17456c441224bb565caf7eb20ff34ac378c53296aa3e70d1'
assert p['task_count']==24 and p['new_model_jobs']==18 and p['model_fits']==162
assert c['passed'] and c['models_fitted']==0 and c['tasks_checked']==24
assert c['runtime_sources_checked']==111 and c['plan_sha256']==sha(R/'plan.json')
assert c['reuse_gate']['passed'] and c['reuse_gate']['reused_records']==6 and c['reuse_gate']['new_control_fits']==0
assert read(R/'root_review.json')['passed']
files=[]
for directory,count in [('code',6),('inputs',72),('scoring',3),('source_refs',10)]:
    found=sorted(x for x in (R/directory).rglob('*') if x.is_file() and '__pycache__' not in x.parts)
    assert len(found)==count,(directory,len(found))
    files.extend(found)
for name in ['plan.json','README.md','cpu_fixture_proof.json','root_review.json','build_inputs.py','reuse_controls.py','research.py','postprocess.py','cross_panel.py','cpu_preflight.py','run_task_sandbox.sh','test_cross_panel.py','prepare_protocol.py','freeze_registration.py']:
    files.append(R/name)
assert len(set(files))==105
save(R/'frozen.json',{'files':{str(x.relative_to(R)):sha(x) for x in sorted(files)},'target_percent':55,'no_2019plus_scoring':True})
save(R/'launch_authorization.json',{'model_fits_authorized':True,'authorization':'User-directed ongoing GPU model stacking toward55%; root reviewed preregistered development-only study.','plan_sha256':sha(R/'plan.json'),'frozen_sha256':sha(R/'frozen.json'),'cpu_preflight_sha256':sha(R/'results/cpu_preflight.json'),'new_jobs':18,'new_model_fits':162,'reused_control_records':6,'reused_original_fits':54,'workers':4,'limits':{'runtime_seconds':7200,'memory_gib':140,'cpu_quota_percent':2200},'automatic_retry':False,'no_benchmark_evaluation':True})
print(json.dumps({'frozen_files':105,'frozen_sha256':sha(R/'frozen.json'),'plan_sha256':sha(R/'plan.json'),'cpu_preflight_sha256':sha(R/'results/cpu_preflight.json'),'authorization_sha256':sha(R/'launch_authorization.json')}))
