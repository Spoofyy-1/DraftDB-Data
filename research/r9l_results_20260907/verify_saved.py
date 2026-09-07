"""Independent saved-result arithmetic; no estimator imports or model fitting.

Run inside a read-only R9L namespace, with no GPU devices or other studies.
Only 2012--2014 development truth is available. Never export those labels.
"""
from pathlib import Path
from collections import defaultdict
import hashlib, json, math, os, tarfile, gzip, io
import numpy as np

ROOT=Path('/workspace'); OUT=Path('/verification')
PIN='db5f0f5bccf62f923cd84fbc7e7cba42055f2236bec9bb9c5865b350af260af0'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(name,obj):
 p=OUT/name;p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n');return p
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def ah(v):
 a=np.asarray(v,dtype=np.float64);a=np.where(a==0,0,a);m=np.isnan(a)
 return hashlib.sha256(json.dumps(list(a.shape),separators=(',',':')).encode()+m.tobytes()+np.where(m,0.,a).tobytes()).hexdigest()
def exact(a,b):assert np.array_equal(np.asarray(a),np.asarray(b),equal_nan=True)
def close(a,b,tol=2e-14):assert math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=tol,(a,b)
def ranks2(v):
 """Own exact integer doubled average ranks, without scipy.rankdata."""
 a=list(map(float,v));assert len(a)>0 and all(map(math.isfinite,a))
 order=sorted(range(len(a)),key=lambda i:a[i]);r=[0]*len(a);start=0
 while start<len(a):
  end=start+1
  while end<len(a) and a[order[end]]==a[order[start]]:end+=1
  for j in range(start,end):r[order[j]]=start+1+end
  start=end
 return np.array(r,dtype=np.int64)
def rho(a,b):
 x=ranks2(a).astype(float);y=ranks2(b).astype(float);n=len(x);assert n==len(y)
 x-=math.fsum(x)/n;y-=math.fsum(y)/n
 xx=math.fsum(v*v for v in x);yy=math.fsum(v*v for v in y)
 return math.fsum(float(u*v)for u,v in zip(x,y))/math.sqrt(xx*yy) if xx and yy else 0.
def keys(X):return [tuple(None if np.isnan(v) else ('0x0.0p+0' if v==0 else float(v).hex())for v in row)for row in X]
def mean(v):return math.fsum(v)/len(v)
def blend(members,recipe,n):
 assert recipe['kind']=='fixed_rank_weights' and recipe['weight_total']==12
 ms=recipe['members'];assert sum(m['units']for m in ms)==12 and all(type(m['units'])is int and m['units']>0 for m in ms)
 assert len({m['family']for m in ms})==len(ms)
 return np.array([sum(int(ranks2(members[m['family']])[i])*m['units']for m in ms)for i in range(n)],dtype=np.int64)/(24*n)
def check_ties(qkeys,raw,canonical,audit,pids):
 raw=np.array(raw,dtype=float);assert raw.shape==(len(pids),) and np.isfinite(raw).all()
 groups=defaultdict(list)
 for i,k in enumerate(qkeys):groups[k].append(i)
 expected=raw.copy();dups=[]
 for g in groups.values():
  if len(g)>1:
   v=math.fsum(sorted(float(raw[i])for i in g))/len(g);expected[g]=v
   dups.append({'pids':[pids[i]for i in g],'assigned':v,'raw':[float(raw[i])for i in g]})
 exact(expected,canonical);assert audit['duplicate_groups']==dups
 assert audit['raw_hash']==ah(raw) and audit['canonical_hash']==ah(expected)
 assert audit['input_vector_hashes']==[digest(k)for k in qkeys]
 return expected
def check_preprocessing(X,Q,p):
 med=np.array([np.median(col[np.isfinite(col)])if np.isfinite(col).any()else 0. for col in X.T]);exact(med,p['median'])
 inds=np.flatnonzero(np.isnan(X).any(axis=0));exact(inds,p['indicator_columns']);assert p['training_rows_seen']==len(X)
 x=np.concatenate([np.where(np.isnan(X),med,X),np.isnan(X[:,inds])],axis=1)
 q=np.concatenate([np.where(np.isnan(Q),med,Q),np.isnan(Q[:,inds])],axis=1)
 assert ah(x)==p['imputed_training_hash'] and ah(q)==p['imputed_query_hash']
 assert np.allclose(x.mean(axis=0),p['scaler_mean'],rtol=1e-12,atol=1e-12)
 assert np.allclose(x.var(axis=0),p['scaler_var'],rtol=1e-12,atol=1e-12)
 scale=np.array(p['scaler_scale']);assert np.isfinite(scale).all() and (scale>0).all()
 assert np.allclose(scale,np.where(x.var(axis=0)==0,1,np.sqrt(x.var(axis=0))),rtol=1e-11,atol=1e-11)
 assert ah((x-np.array(p['scaler_mean']))/scale)==p['transformed_training_hash']
 assert ah((q-np.array(p['scaler_mean']))/scale)==p['transformed_query_hash']

def main():
 assert not Path('/dev/nvidia0').exists() and not Path('/home/ubuntu/nba/handoff').exists()
 assert sha(ROOT/'frozen.json')==PIN
 frozen=read(ROOT/'frozen.json');assert len(frozen['files'])==90
 for n,s in frozen['files'].items():assert sha(ROOT/n)==s,n
 p=read(ROOT/'plan.json');proto=read(ROOT/'code/protocol.json');auth=read(ROOT/'launch_authorization.json')
 assert auth['frozen_sha256']==PIN and auth['plan_sha256']==sha(ROOT/'plan.json') and auth['model_fits_authorized']
 assert sha(ROOT/'results/cpu_preflight.json')==auth['cpu_preflight_sha256'] and read(ROOT/'results/cpu_preflight.json')['passed']
 assert p['outer_years']==[2012,2013,2014] and p['seeds']==[0,101,202] and p['task_count']==24 and p['model_fits']==216
 assert p['architectures']==proto['architectures'] and len(p['architectures'])==38
 tasks={t['id']:t for t in p['tasks']};assert len(tasks)==24
 recipes={r['id']:r for r in p['architectures']};families=['tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost']
 for recipe in recipes.values():
  ms=recipe['members'];types={'ridge' if m['family'].startswith('ridge_') else m['family']for m in ms}
  assert len(types)==len(ms),'A recipe cannot masquerade as multiple families by combining two Ridge alphas.'
 entries=[json.loads(line)for line in (ROOT/'results/completed.jsonl').read_text().splitlines()]
 assert len(entries)==24 and {e['task_id']for e in entries}==set(tasks)
 assert {e['task_id']for e in entries[:3]}=={f'base44_y{y}'for y in p['outer_years']}
 manifest=read(ROOT/'results/result_manifest.json');completion=read(ROOT/'results/completion.json')
 assert completion['status']=='completed' and completion['tasks']==24 and completion['model_fits']==216
 assert completion['result_manifest_sha256']==sha(ROOT/'results/result_manifest.json')
 assert manifest['diagnostics_sha256']==sha(ROOT/'results/stack_diagnostics.json') and manifest['scoring_records']==4128
 assert manifest['tasks']=={e['task_id']:e for e in entries}
 ref=read(ROOT/'scoring/reference_vectors.json');assert sha(ROOT/'scoring/reference_vectors.json')==p['reference_vectors_sha256']
 gate=read(ROOT/'results/reference_gate.json');assert gate['passed'] and gate['exact_member_fold_seed_vectors']==36
 support=read(ROOT/'code/runtime_support.json')
 for group in ['sources','checkpoint_files']:
  for name,meta in support[group].items():assert Path(name).stat().st_size==meta['bytes'] and sha(name)==meta['sha256'],name
 diag=read(ROOT/'results/stack_diagnostics.json');saved={}
 for d in diag['prediction_details']:
  k=(d['panel_id'],d['architecture'],d['year'],str(d['seed']));assert k not in saved;saved[k]=d
 assert len(saved)==4128
 rows=defaultdict(list);members_checked=0;refs=0;scored=0;max_score_delta=0.;widths={};ranges={};fit_total=0
 for e in entries:
  task=tasks[e['task_id']];year=task['outer_year'];tid=task['id'];assert e['file']==f'jobs/{tid}/result.json'
  path=ROOT/'results'/e['file'];assert sha(path)==e['sha256'];r=read(path)
  for field in ['panel_id','policy_id','outer_year','input_manifest_sha256']:assert r[field]==task[field]
  assert r['task_id']==tid and r['protocol_sha256']==p['protocol_sha256']==sha(ROOT/'code/protocol.json')
  im=read(ROOT/'inputs'/tid/'manifest.json');assert sha(ROOT/'inputs'/tid/'manifest.json')==task['input_manifest_sha256']
  assert r['columns']==im['columns'] and r['label_audit']==im['label_audit'];widths[r['panel_id']]=len(r['columns'])
  for f,m in im['files'].items():assert sha(ROOT/'inputs'/tid/f)==m['sha256']
  with np.load(ROOT/'inputs'/tid/'training.npz',allow_pickle=False)as a:tr={k:a[k]for k in a.files}
  with np.load(ROOT/'inputs'/tid/'inference.npz',allow_pickle=False)as a:qu={k:a[k]for k in a.files}
  X=tr['X'];Q=qu['X'];tp=tr['pid'].tolist();qp=qu['pid'].tolist();n=len(qp)
  assert set(tr)=={'X','pid','draft_year','label_value','y','prefix_length'} and set(qu)=={'X','pid'}
  assert tp==r['training_pids'] and qp==r['query_pids'] and len(tp)==task['training_rows'] and n==task['query_rows']
  assert len(set(tp))==len(tp) and len(set(qp))==n and not set(tp)&set(qp)
  for ids in [tp,qp]:assert sorted(ids,key=lambda x:(hashlib.sha256(x.encode()).hexdigest(),x))==ids
  assert not np.isinf(X).any() and not np.isinf(Q).any() and np.isfinite(tr['y']).all() and np.isfinite(tr['label_value']).all()
  assert (tr['draft_year']>=2008).all() and (tr['draft_year']<year).all() and (tr['prefix_length']==1).all()
  la=r['label_audit'];assert la['max_actual_label_season']<=year-1 and la['all_labels_finite_observed'] and not la['missing_training_labels_zero_filled'] and la['cutoff_broker_reverified']
  assert la['training_pid_hash']==digest(tp) and la['label_value_hash']==ah(tr['label_value']) and la['target_hash']==ah(tr['y'])
  assert r['training_matrix_hash']==ah(X) and r['query_matrix_hash']==ah(Q) and r['target_hash']==ah(tr['y'])
  assert r['fit_counts']=={'ridge_a30':1,'ridge_a300':1,'ridge_a3000':1,'tabicl':3,'catboost':3};fit_total+=sum(r['fit_counts'].values())
  assert not r['query_outcome_labels_accessed'] and not r['query_outcomes_accessed'] and not r['learned_weights'] and r['selector_fits']==0
  ns=r['namespace_proof'];assert ns['passed'] and ns['input_files']==['inference.npz','manifest.json','training.npz'] and ns['inaccessible_paths']==['/scoring','/reference','/h_reference','/home/ubuntu/nba/handoff']
  assert r['runtime']['support_sha256']==sha(ROOT/'code/runtime_support.json') and r['runtime']['versions']==support['versions']
  assert sha(ROOT/'scoring'/f'{year}.npz')==p['scoring'][str(year)]['sha256']
  with np.load(ROOT/'scoring'/f'{year}.npz',allow_pickle=False)as q:
   assert q['pid'].tolist()==qp;truth=q['legacy_truth'];mask=q['observed_truth_mask']
  assert truth.shape==(n,) and np.isfinite(truth).all() and mask.shape==(n,) and mask.dtype==np.dtype(bool) and int(mask.sum())>1
  ranges[str(year)]={'full_query_rows':n,'observed_subset_rows':int(mask.sum()),'training_rows':len(tp),'max_label_season':la['max_actual_label_season']}
  qkeys=keys(Q);seed_vectors={};assert [s['seed']for s in r['seed_results']]==[0,101,202]
  for s in r['seed_results']:
   seed=s['seed'];assert set(s['members'])==set(families);vs={}
   for family,m in s['members'].items():
    a=m['model_audit'];assert a['family']==family and a['seed']==(0 if family.startswith('ridge_')else seed)
    assert a['input_columns']==r['columns'] and a['training_pid_hash']==digest(tp) and a['training_matrix_hash']==ah(X) and a['query_matrix_hash']==ah(Q) and a['training_target_hash']==ah(tr['y'])
    assert not a['query_or_validation_labels_seen'] and not a['eval_set_supplied'] and not a['early_stopping']
    if family.startswith('ridge_'):
     expected={'alpha':int(family.split('a')[-1]),'solver':'svd'};assert a['parameters']==expected==a['effective_constructor'] and a['actual_device']=='CPU'
     check_preprocessing(X,Q,a['preprocessing'])
     assert m==r['seed_results'][0]['members'][family]
    elif family=='tabicl':
     expected={**proto['tabicl'],'random_state':seed};assert a['parameters']==expected
     for k,v in expected.items():assert a['effective_constructor'][k]==v
     # Pinned TransformToNumerical mean-imputes training numeric columns, then
     # EnsembleGenerator's UniqueFeatureFilter drops training constants. The
     # 22 historically unavailable combine slots therefore do not survive.
     variable=sum(len(np.unique(c[np.isfinite(c)]))>1 for c in X.T)
     assert a['actual_devices']==['cuda:0'] and a['effective_feature_count']==max(1,variable) and a['effective_ensemble_count']==32 and a['requested_ensemble_count']==32
    else:
     expected={**proto['catboost']['parameters'],'random_seed':seed};assert a['parameters']==expected and a['tree_count']==a['checkpoint']==600 and a['actual_device']=='GPU'
     for k in ['iterations','loss_function','depth','learning_rate','l2_leaf_reg','bagging_temperature','nan_mode','bootstrap_type','boosting_type','random_strength','use_best_model','random_seed','task_type']:
      if type(expected[k])in(int,float):assert np.isclose(a['effective_constructor'][k],expected[k],rtol=2e-7,atol=1e-9)
      else:assert a['effective_constructor'][k]==expected[k]
    vs[family]=check_ties(qkeys,m['raw_predictions'],m['canonical_predictions'],m['tie_audit'],qp);members_checked+=1
    if r['panel_id']=='base44' and family!='catboost':
     old=ref[str(year)]['members'][family][str(seed)];assert ref[str(year)]['query_pids']==qp
     exact(old['raw'],m['raw_predictions']);exact(old['canonical'],m['canonical_predictions']);refs+=1
   seed_vectors[seed]=vs
  averaged={f:seed_vectors[0][f] if f.startswith('ridge_') else np.sum([ranks2(seed_vectors[s][f])for s in [0,101,202]],axis=0,dtype=np.int64)/(6*n) for f in families}
  assert set(r['fixed_three_seed_family_rank_average']['members'])==set(families)
  for f,v in averaged.items():exact(v,r['fixed_three_seed_family_rank_average']['members'][f])
  modes=[(s['seed'],seed_vectors[s['seed']],s['architectures'])for s in r['seed_results']]+[('fixed_three_seed_family_rank_average',averaged,r['fixed_three_seed_family_rank_average']['architectures'])]
  for mode,vs,stored_arch in modes:
   assert set(stored_arch)==set(recipes)
   vectors={name:blend(vs,recipe,n)for name,recipe in recipes.items()}
   for name,v in vectors.items():exact(v,stored_arch[name])
   vectors.update({'control_'+f:v for f,v in vs.items()})
   for name,v in vectors.items():
    d=saved[(r['panel_id'],name,year,str(mode))];assert d['query_pids']==qp;exact(v,d['prediction'])
    actual={'full':rho(v,truth),'observed':rho(v[mask],truth[mask])}
    for metric,value in actual.items():close(value,d[metric]);max_score_delta=max(max_score_delta,abs(value-d[metric]))
    rows[(r['panel_id'],name)].append({'year':year,'seed':mode,**actual});scored+=1
 assert fit_total==216 and refs==36 and members_checked==360 and scored==4128
 summaries={}
 for (panel,name),rr in rows.items():
  direct=[x for x in rr if type(x['seed'])is int];fixed=[x for x in rr if type(x['seed'])is str];assert len(direct)==9 and len(fixed)==3
  recipe=recipes.get(name);multi=bool(recipe and len(recipe['members'])>=2)
  result={'panel_id':panel,'architecture':name,'recipe':recipe,'multi_family_every_fold_seed':multi,'member_control':not multi}
  for metric in ['full','observed']:
   result[metric]={'mean_score':mean([x[metric]for x in direct]),'fold_scores':{str(y):mean([x[metric]for x in direct if x['year']==y])for y in p['outer_years']},'seed_scores':{str(s):mean([x[metric]for x in direct if x['seed']==s])for s in p['seeds']},'fixed_three_seed_family_rank_average':mean([x[metric]for x in fixed])}
  summaries[(panel,name)]=result
 saved_summaries=diag['stack_summaries_oof']+diag['control_summaries_oof'];assert len(saved_summaries)==len(summaries)==344
 def compare_summary(s):
  z=summaries[(s['panel_id'],s['architecture'])];assert s['recipe']==z['recipe'] and s['multi_family_every_fold_seed']==z['multi_family_every_fold_seed'] and s['member_control']==z['member_control']
  for metric in ['full','observed']:
   for k in ['mean_score','fixed_three_seed_family_rank_average']:close(s[metric][k],z[metric][k])
   for k in ['fold_scores','seed_scores']:
    assert set(s[metric][k])==set(z[metric][k])
    for f in s[metric][k]:close(s[metric][k][f],z[metric][k][f])
  if s['panel_id']!='base44':
   b=summaries[('base44',s['architecture'])];gain=z['full']['mean_score']-b['full']['mean_score'];close(s['full_gain_vs_same_recipe44'],gain)
   gains=[]
   for key,target in [('fold_scores','full_fold_gains_vs44'),('seed_scores','full_seed_gains_vs44')]:
    for f in z['full'][key]:
     g=z['full'][key][f]-b['full'][key][f];close(s[target][f],g);gains.append(g)
   assert s['all_fold_and_seed_means_improved']==all(g>0 for g in gains)
 for s in saved_summaries:compare_summary(s)
 assert len(diag['paired_panel_comparisons'])==301
 for s in diag['paired_panel_comparisons']:compare_summary(s)
 stacks=sorted([z for z in summaries.values()if z['multi_family_every_fold_seed']],key=lambda z:(-z['full']['mean_score'],z['panel_id'],z['architecture']))
 controls=sorted([z for z in summaries.values()if z['member_control']],key=lambda z:(-z['full']['mean_score'],z['panel_id'],z['architecture']))
 for kind,values in [('best_actual_multifamily_stack',stacks),('best_member_control',controls)]:
  assert (diag[kind]['panel_id'],diag[kind]['architecture'])==(values[0]['panel_id'],values[0]['architecture']);compare_summary(diag[kind])
 panelbest={panel:next(s for s in stacks if s['panel_id']==panel)for panel in widths}
 evidence={'passed':True,'study':'R9L','frozen_sha256':PIN,'frozen_files_verified':90,'result_records':24,'unique_registered_fits':216,'saved_member_records_verified':360,'reference_vector_pairs':36,'raw_and_canonical_reference_arrays':72,'scored_prediction_records':scored,'score_arithmetic':'Own exact doubled tied ranks plus centered math.fsum Pearson; independent of coordinator/scipy rankdata. Canonical vectors, seed averages and blends exact; score/aggregate tolerance 2e-14.','maximum_score_absolute_difference':max_score_delta,'score_summaries_verified':344,'paired_panel_comparisons_verified':301,'runtime_sources_verified':len(support['sources']),'checkpoint_files_verified':len(support['checkpoint_files']),'model_fits_performed':0,'network_access':False,'gpu_devices_available':False,'other_studies_available':False,'no_2019plus_access':True,'scoring_truth_exported':False,'registered_gate_order':'Pinned scheduler has gate before non-base submission; first three durable completed log entries are the three base44 tasks. No independent process tracing was recorded.','widths':widths,'cohort_contract':ranges,'best_actual_multifamily_stack':diag['best_actual_multifamily_stack'],'best_member_control':diag['best_member_control'],'best_actual_multifamily_by_panel':panelbest,'source_hashes':{n:sha(ROOT/n)for n in ['plan.json','results/completed.jsonl','results/result_manifest.json','results/stack_diagnostics.json','results/reference_gate.json','launch_authorization.json']},'verifier_sha256':sha(Path(__file__)),'limitations':proto['limitations']+['Many configurations were evaluated on the same three development folds. These scores do not establish held-out generalization or attainment of the 60% goal.','Full-query score is primary; complete-outcome subset is secondary. The fixed three-seed family rank average is separate from the mean of nine seed/fold correlations.','Saved audit verification certifies internal arithmetic and pinned evidence, not forensic proof that a process could never have accessed external information.']}
 write('verification.json',evidence)
 chosen=['frozen.json','launch_authorization.json','plan.json','build_inputs.py','research.py','postprocess.py','cpu_preflight.py','run_task_sandbox.sh','README.md','cpu_fixture_proof.json','code/model_backend.py','code/protocol.json','code/runtime_support.json','code/stack_core.py','code/test_worker.py','code/worker.py','results/completed.jsonl','results/completion.json','results/result_manifest.json','results/stack_diagnostics.json','results/reference_gate.json','results/cpu_preflight.json']+[f"results/jobs/{t['id']}/result.json"for t in p['tasks']]
 assert len(chosen)==len(set(chosen))==46
 assert all(not n.startswith(('inputs/','scoring/')) and not n.endswith('.npz') and '..'not in Path(n).parts for n in chosen)
 allow={'study':'R9L','policy':'Only explicitly listed development result records, prediction/score diagnostics, registration, code and aggregate audits. No input/scoring NPZ, query truth arrays, training labels, private identity, credentials, source bodies, or K files. No autonomous publication.','files':{n:{'sha256':sha(ROOT/n),'bytes':(ROOT/n).stat().st_size}for n in sorted(chosen)}}
 write('ARCHIVE_ALLOWLIST.json',allow)
 archive=OUT/'r9l_saved_results.tar.gz'
 with archive.open('wb')as base:
  with gzip.GzipFile(fileobj=base,mode='wb',mtime=0,filename='')as gz:
   with tarfile.open(fileobj=gz,mode='w')as tar:
    for n in sorted(chosen):
     info=tar.gettarinfo(str(ROOT/n),arcname=n);assert info.isfile();info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o644
     with (ROOT/n).open('rb')as f:tar.addfile(info,f)
 with tarfile.open(archive,'r:gz')as tar:
  members=tar.getmembers();assert {m.name for m in members}==set(chosen) and len(members)==46
  for m in members:
   data=tar.extractfile(m).read();assert len(data)==allow['files'][m.name]['bytes'] and hashlib.sha256(data).hexdigest()==allow['files'][m.name]['sha256']
 write('archive_manifest.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'members':46,'uncompressed_bytes':sum(m['bytes']for m in allow['files'].values()),'member_hash_roundtrip_passed':True,'archive_allowlist_sha256':sha(OUT/'ARCHIVE_ALLOWLIST.json'),'verification_sha256':sha(OUT/'verification.json')})
 print(json.dumps({'passed':True,'best_stack':evidence['best_actual_multifamily_stack'],'best_control':evidence['best_member_control'],'panel_best':{k:{'architecture':v['architecture'],'full':v['full']['mean_score'],'observed':v['observed']['mean_score']}for k,v in panelbest.items()},'archive':read(OUT/'archive_manifest.json')},indent=2))

if __name__=='__main__':main()
