"""Read frozen savedI/J, validate, replay arithmetic into a separate directory. Neverfit."""
from pathlib import Path
import collections,gzip,hashlib,importlib.util,json,sys,time,tarfile,os
import numpy as np
ROOT=Path('/workspace');OUT=Path('/verification');NAME=sys.argv[1];assert NAME in ['r9i','r9j'];OUT.mkdir(exist_ok=True,parents=True)
sys.path.insert(0,str(ROOT));import worker as W
spec=importlib.util.spec_from_file_location('saved_postprocess',ROOT/'postprocess.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
def deny(*a,**kw):raise AssertionError('Verification prohibits model execution')
for module in [W,W.H]:
 for name in ['run_variant','fit_native','make_model','constructor']:
  if hasattr(module,name):setattr(module,name,deny)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
p=W.plan();f=read(ROOT/'frozen.json');assert len(f['files'])==15
for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
sm=read(ROOT/'source_manifest.json');assert len(sm['H_files'])==81
for name,digest in sm['H_files'].items():assert sha(Path('/h_reference')/name)==digest,name
for name,info in sm['H_reference_files'].items():assert sha(Path('/h_reference')/name)==info['sha256'],name
expected={f"{t['variant']}_seed{t['seed']}"for t in p['tasks']};assert len(expected)==(336 if NAME=='r9i' else 48)
result=ROOT/'results';completion=read(result/'completion.json');assert completion['status']=='completed'and completion['tasks']==len(expected)and completion['reference_gate']
gate=read(result/'reference_gate.json');assert gate['passed']and gate['exact_references']==12
raw=(result/'completed.jsonl').read_bytes();assert raw.endswith(b'\n');records=[];registered={}
for line in raw.splitlines():
 r=json.loads(line);tid=r['task_id'];assert tid in expected and tid not in registered and r['file']==tid+'.json'
 path=result/'tasks'/r['file'];assert sha(path)==r['sha256'];e=read(path);W.validate_entry(e);registered[tid]=r;records.append(e)
assert set(registered)==expected
refs=[e for e in records if e['config']['kind'] not in ['CatBoost_checkpoint_candidate','stack_member_candidate']];assert len(refs)==12
assert all([r['season']for r in e['rows']]==[2012,2013,2014]for e in records)
print(json.dumps({'study':NAME,'records_verified':len(records),'exact_references':12,'frozen_study15_H81_verified':True}),flush=True)
replay=OUT/'replay';replay.mkdir(exist_ok=True);started=time.monotonic();P.process(records,replay)
manifest_name='blend_manifest.json'if NAME=='r9i'else'stack_manifest.json';summary_name='blend_summary.json'if NAME=='r9i'else'stack_summary.json'
old=read(result/manifest_name);new=read(replay/manifest_name);assert old==new,'Deterministic savedrecipe manifest differs';assert sha(result/summary_name)==sha(replay/summary_name)
count=0
for ch in old['chunks']:
 path=result/ch['file'];assert sha(path)==ch['sha256']and path.stat().st_size==ch['bytes'];assert sha(path)==sha(replay/ch['file'])
 unc=hashlib.sha256();nbytes=0
 with gzip.open(path,'rb')as z:
  for i,l in enumerate(ch['recipes'],1):
   b=z.readline();assert b.endswith(b'\n')and l['line_1based']==i and len(b)-1==l['bytes']and hashlib.sha256(b[:-1]).hexdigest()==l['sha256'];unc.update(b);nbytes+=len(b);count+=1
  assert not z.read()
 assert unc.hexdigest()==ch['uncompressed_sha256']and nbytes==ch['uncompressed_bytes']
assert count==(14256 if NAME=='r9i' else 2244)
# Report only full-pool selected diagnostics; subset is secondary, no best-seedselection.
if NAME=='r9i':
 groups=collections.defaultdict(list);fixed={}
 for r in read(replay/summary_name)['diagnostics']:
  key=(r['id'],r['ntree_end'],r['alpha_step'])
  if r['seed']is None:fixed[key]=r
  else:groups[key].append(r)
 items=[]
 for key,rs in groups.items():
  assert sorted(r['seed']for r in rs)==p['seeds'];v=next(v for v in p['variants']if v['id']==key[0]);setting=next(s for s in p['settings']if s['id']==v['setting_id'])
  items.append({'variant_id':key[0],'payload_id':v['payload_id'],'setting_id':v['setting_id'],'CatBoost_parameters':setting['parameters'],'ntree_end':key[1],'alpha_step':key[2],'mode':'mean_all_three_seed_fold_correlations','legacy':float(np.mean([r['legacy']['mean_score']for r in rs])),'observed':float(np.mean([r['observed']['mean_score']for r in rs])),'fixed_three_seed_raw_prediction_average_then_rankblend':{m:fixed[key][m]['mean_score']for m in ['legacy','observed']}})
 ranked=sorted(items,key=lambda r:(-r['legacy'],r['variant_id'],r['ntree_end'],r['alpha_step']))
 report={'best_predefined_two_family_blend':next(r for r in ranked if 0<r['alpha_step']<10),'best_single_member_endpoint_control':next(r for r in ranked if r['alpha_step']in[0,10]),'best_standalone_CatBoost':next(r for r in ranked if r['alpha_step']==10),'mean_seed_vs_fixed':'Primarylegacy/observed are mean3seed×3fold correlations. Fixed-mode first arithmetic-averages each family raw prediction across3seeds, then ranks/blends; it is not Jfamily-rank-average.'}
else:
 rows=read(replay/summary_name)['summaries'];ranked=sorted(rows,key=lambda r:(-r['legacy']['mean_score'],r['payload_id'],r['recipe_id']))
 def families(r):
  recipe=r['recipe']
  return len({m['family']for m in recipe['members']if recipe['kind']!='fixed_rank_weights'or m['units']>0})
 report={'best_actual_two_plus_family_stack':next(r for r in ranked if families(r)>=2),'best_single_family_control':next(r for r in ranked if families(r)==1),'best_adapted_coverage_control':next(r for r in ranked if r['recipe']['kind']=='adapted_coverage_control'),'mean_seed_vs_fixed':'Primarymean is meanall3seedcorrelations over3folds. Fixedthree mode averages within-familyseedrankvectors, then applies frozenfamilyrankblend; it is a differentpredictionrule.'}
allowed=set(f['files'])|{'frozen.json','results/completed.jsonl','results/reference_gate.json','results/completion.json','results/'+manifest_name,'results/'+summary_name}
for r in registered.values():allowed.add('results/tasks/'+r['file'])
for ch in old['chunks']:allowed.add('results/'+ch['file'])
for optional in ['results/preregistered_plan.json','results/queue_registration.json']:
 if (ROOT/optional).is_file():allowed.add(optional)
assert all(not Path(n).is_absolute()and'..'not in Path(n).parts and not n.endswith(('.npz','.pem'))for n in allowed)
files={n:{'sha256':sha(ROOT/n),'bytes':(ROOT/n).stat().st_size}for n in sorted(allowed)}
verification={'study':NAME,'status':'PASS','completed_tasks':len(records),'frozen_study_files':15,'H_frozen_files':81,'H_reference_metadata_files':len(sm['H_reference_files']),'exact_reference_gate':12,'immutable_task_hashes_configs_ties_and_scores_checked':True,'recipe_records':count,'saved_chunk_count':len(old['chunks']),'all_compressed_and_uncompressed_and_perline_hashes_pass':True,'deterministic_math_replay_all_saved_chunks_byte_identical':True,'saved_summary_replay_byte_identical':True,'replay_seconds':time.monotonic()-started,'model_fits':0,'model_execution_functions_disabled':True,'GPU_devices_mounted':False,'development_years_only':[2012,2013,2014],'new_benchmark_or_2019_plus_outcomes_read':False,'no_automatic_promotion':True,'report':report,'source_completion_sha256':sha(result/'completion.json'),'source_frozen_sha256':sha(ROOT/'frozen.json')}
save(OUT/'verification.json',verification);save(OUT/'PUBLICATION_ALLOWLIST.json',{'study':NAME,'policy':'ExplicitI/J saveddevelopmentoutputs/code only; noKfiles, label/inputNPZs, privateidentities, rawsourcearticles orkeys; parentmustauthorize publication.','files':files})
archive=OUT/(NAME+'_saved_raw.tar.gz')
with tarfile.open(archive,'w:gz',compresslevel=6)as tar:
 for n in files:tar.add(ROOT/n,arcname=NAME+'/'+n,recursive=False)
with tarfile.open(archive,'r:gz')as tar:
 members=tar.getmembers();assert all(m.isfile()for m in members);assert {m.name for m in members}=={NAME+'/'+n for n in files}
 for member in members:
  n=member.name[len(NAME)+1:];b=tar.extractfile(member).read();assert len(b)==files[n]['bytes']and hashlib.sha256(b).hexdigest()==files[n]['sha256']
save(OUT/'archive_manifest.json',{'file':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'members':len(files),'every_archive_member_roundtrip_verified':True,'allowlist_sha256':sha(OUT/'PUBLICATION_ALLOWLIST.json'),'verification_sha256':sha(OUT/'verification.json')})
# Original frozen/artifact paths were read-only throughout the namespace.
print(json.dumps({'study':NAME,'status':'PASS','recipes':count,'archive':read(OUT/'archive_manifest.json'),'report':report}),flush=True)
