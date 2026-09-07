"""Verify downloaded archive boundaries and prepare explicit publication wrapper."""
from pathlib import Path
import hashlib,json,tarfile
R=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text())
checks={}
for n in ['r9i','r9j']:
 d=R/n;a=read(d/'archive_manifest.json');al=read(d/'PUBLICATION_ALLOWLIST.json');v=read(d/'verification.json');assert v['status']=='PASS'
 assert sha((d/a['file']).read_bytes())==a['sha256'];assert sha((d/'PUBLICATION_ALLOWLIST.json').read_bytes())==a['allowlist_sha256'];assert sha((d/'verification.json').read_bytes())==a['verification_sha256']
 contents={}
 with tarfile.open(d/a['file'],'r:gz')as t:
  members=t.getmembers();assert all(m.isfile()and m.name.startswith(n+'/')and'..'not in Path(m.name).parts for m in members)
  assert {m.name[len(n)+1:]for m in members}==set(al['files'])
  for m in members:
   k=m.name[len(n)+1:];b=t.extractfile(m).read();assert sha(b)==al['files'][k]['sha256']and len(b)==al['files'][k]['bytes'];contents[k]=b
 # Crosslink archive contents to the frozen registrations and originally saved records/chunks.
 frozen=json.loads(contents['frozen.json']);assert len(frozen['files'])==15
 for k,h in frozen['files'].items():assert sha(contents[k])==h
 logs=[json.loads(x)for x in contents['results/completed.jsonl'].splitlines()];assert len(logs)==v['completed_tasks'] and len({x['task_id']for x in logs})==len(logs)
 for x in logs:assert x['file']==x['task_id']+'.json' and sha(contents['results/tasks/'+x['file']])==x['sha256']
 mn='blend_manifest.json'if n=='r9i'else'stack_manifest.json';mm=json.loads(contents['results/'+mn])
 for x in mm['chunks']:assert sha(contents['results/'+x['file']])==x['sha256']
 assert not any(k.endswith(('.npz','.pem'))or'private' in Path(k).parts or 'r9k' in Path(k).parts for k in contents)
 checks[n]={'status':'PASS','archive_members':len(contents),'archive_sha256':a['sha256'],'downloaded_archive_roundtrip_and_embedded_log_chunk_frozen_links_verified':True,'verification_sha256':a['verification_sha256']}
i=read(R/'r9i/verification.json')['report'];j=read(R/'r9j/verification.json')['report'];ii=i['best_predefined_two_family_blend'];jj=j['best_actual_two_plus_family_stack'];jc=j['best_single_family_control'];ic=i['best_single_member_endpoint_control'];cb=i['best_standalone_CatBoost']
summary={'status':'PASS','studies':checks,'I_best_predefined_two_family_blend':ii,'J_best_actual_two_plus_family_stack':jj,'J_best_single_family_control':jc,'I_best_single_member_endpoint_control':ic,'I_best_standalone_CatBoost':cb,'primary_full_comparison_J_stack_minus_I_blend':jj['legacy']['mean_score']-ii['legacy'],'primary_mode':'Meanall3seedcorrelations across3developmentfolds; neverbestseed.','secondary_mode':'Samefrozenobserved-truth subset; notwholeclassaccuracy.','fixed_prediction_modes_differ':{'I':i['mean_seed_vs_fixed'],'J':j['mean_seed_vs_fixed']},'source_or_model_files_modified':False,'models_fitted':0,'new_2019_plus_benchmark_access':False,'publication_performed':False,'verifier_source_versions':{'I':sha((R/'verify_saved.py').read_bytes()),'J':sha((R/'verify_saved_J_executed.py').read_bytes())}}
(R/'independent_verification.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['# I/J saved-result verification and archive','','Bothstudies pass independent saved-record validation, exact reference checks and deterministic replay. Originalstudy directories were mountedread-only, model-execution functions disabled, noGPUdevices mounted, and outputs written separately. No refits, new benchmark evaluation or2019+outcome reads occurred.','','|Study|Frozenstudy/Hfiles|Taskrecords|Exactreferences|Savedrecipes/chunks|Rawarchive|','|---|---:|---:|---:|---:|---:|','|I|15/81|336|12|14256/108|24.90MB|','|J|15/81|48|12|2244/12|4.15MB|','','Every task/configuration, recorded canonicaltie rule and saved score passed the existing validator. All savedrecipe compressed bytes, uncompressed hashes, individual lines and summaries exactly match a fresh arithmetic replay from saved predictions. Downloaded archives were independentlychecked against their allowlists, embeddedfrozen manifests, completedtask logs and chunk manifests.','','|Registered result|Primaryfull meanseedcorrelation|Secondarysubset meanseedcorrelation|','|---|---:|---:|',f"|J50%TabICL+50%Ridge300|{100*jj['legacy']['mean_score']:.4f}%|{100*jj['observed']['mean_score']:.4f}%|",f"|Jbest singlefamily:Ridge300|{100*jc['legacy']['mean_score']:.4f}%|{100*jc['observed']['mean_score']:.4f}%|",f"|I40%TabICL+60%CatBoost,600trees|{100*ii['legacy']:.4f}%|{100*ii['observed']:.4f}%|",f"|Ibest endpointcontrol:TabICL|{100*ic['legacy']:.4f}%|{100*ic['observed']:.4f}%|",f"|Ibest standaloneCatBoost,600trees|{100*cb['legacy']:.4f}%|{100*cb['observed']:.4f}%|",'', 'All listed winners use s2008_gap1_all_h1 and were ranked byfullpoolmean across allthree seeds and2012/13/14folds. These percentages are Spearman correlations, not percentages of correctly ordered players. The subset score issecondary and inherits selection/immature-label caveats. No modelis promoted.','','TheI CatBoostsetting isMAE,depth3,learning_rate0.1,L2=100,bagging_temperature1,nan_modeMax. The originalmodel fit1200trees and these predictions use checkpoint600; fitting a new600-treemodel is a separately registered choice.','','Fixed seed averaging is a differentpredictionrule from meanseedcorrelations. ForJ, within-familyseedrank averaging thenfamilyblending gives37.3701%full/40.5267%subset for its selectedstack. I first averages eachfamily rawprediction across3seeds andthenrank-blends:37.3290%full/48.2387%subset for its selectedblend. Thosefixedmodes are not averagedscores and mustnot be conflated.','','Only the explicitwrapperallowlist may be published afterparentapproval. Archives contain savedI/J developmentoutputs and their frozen code/metadata; noKprivate outputs,input/labelNPZs,identitycrosswalks orkeys. Originalfrozen H/G input artifacts remain elsewhere and are not bundled.']
(R/'README.md').write_text('\n'.join(lines)+'\n')
files=['README.md','independent_verification.json','verify_saved.py','verify_saved_J_executed.py','run_verify.sh','finalize.py']
for n in ['r9i','r9j']:files += [n+'/'+x for x in ['verification.json','PUBLICATION_ALLOWLIST.json','archive_manifest.json',n+'_saved_raw.tar.gz']]
manifest={'publication_authorized':False,'policy':'Explicit verification/code andI/J rawsaveddevelopmentarchives only. Parentpublishrequired; do notrecursivelycopythisdirectory.','files':{f:{'sha256':sha((R/f).read_bytes()),'bytes':(R/f).stat().st_size}for f in files}}
(R/'PUBLIC_ALLOWLIST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'status':'PASS','files':len(files),'public_allowlist_sha256':sha((R/'PUBLIC_ALLOWLIST.json').read_bytes()),'total_bytes':sum(x['bytes']for x in manifest['files'].values())}))
