"""Independent saved-result arithmetic; no estimator imports or model fitting.

Run inside a read-only R9M namespace, with no GPU devices or other studies.
Only 2012--2014 development truth is available. Never export those labels.
"""
from pathlib import Path
from collections import defaultdict
import hashlib, json, math, os, tarfile, gzip, io
import numpy as np

ROOT=Path('/workspace'); OUT=Path('/verification')
PIN='32a9ac2ec968ebb281027020e5a244eb9a040d589318b3c5dd577da9ece27b00'
PLAN_PIN='cebfe908d2cf0d03bf9f2de6052d30ef8c8a1b7f8a1a23948b782750cc5247e3'
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
 frozen=read(ROOT/'frozen.json');assert len(frozen['files'])==105
 for n,s in frozen['files'].items():assert sha(ROOT/n)==s,n
 assert sha(ROOT/'plan.json')==PLAN_PIN
 p=read(ROOT/'plan.json');proto=read(ROOT/'code/protocol.json');auth=read(ROOT/'launch_authorization.json')
 assert auth['frozen_sha256']==PIN and auth['plan_sha256']==sha(ROOT/'plan.json') and auth['model_fits_authorized']
 assert sha(ROOT/'results/cpu_preflight.json')==auth['cpu_preflight_sha256'] and read(ROOT/'results/cpu_preflight.json')['passed']
 assert p['outer_years']==[2012,2013,2014] and p['seeds']==[0,101,202] and p['task_count']==24 and p['model_fits']==162 and p['reused_original_model_fits']==54 and p['new_model_jobs']==18 and p['reused_control_records']==6
 assert p['architectures']==proto['architectures'] and len(p['architectures'])==38
 tasks={t['id']:t for t in p['tasks']};assert len(tasks)==24
 recipes={r['id']:r for r in p['architectures']};families=['tabicl','ridge_a30','ridge_a300','ridge_a3000','catboost']
 for recipe in recipes.values():
  ms=recipe['members'];types={'ridge' if m['family'].startswith('ridge_') else m['family']for m in ms}
  assert len(types)==len(ms),'A recipe cannot masquerade as multiple families by combining two Ridge alphas.'
 entries=[json.loads(line)for line in (ROOT/'results/completed.jsonl').read_text().splitlines()]
 assert len(entries)==24 and {e['task_id']for e in entries}==set(tasks)
 assert {e['task_id']for e in entries[:6]}=={f'{panel}_y{y}'for panel in ['base44','add_f50']for y in p['outer_years']}
 manifest=read(ROOT/'results/result_manifest.json');completion=read(ROOT/'results/completion.json')
 assert completion['status']=='completed' and completion['tasks']==24 and completion['new_model_fits']==162 and completion['reused_original_model_fits']==54
 assert completion['result_manifest_sha256']==sha(ROOT/'results/result_manifest.json')
 assert manifest['diagnostics_sha256']==sha(ROOT/'results/stack_diagnostics.json') and manifest['scoring_records']==4128
 assert manifest['tasks']=={e['task_id']:e for e in entries}
 src=read(ROOT/'source_refs/manifest.json');assert sha(ROOT/'source_refs/manifest.json')==p['reference_source_manifest_sha256']
 Lallow=read(Path('/auditcode/L_ARCHIVE_ALLOWLIST.json'));Lproof=read(Path('/auditcode/L_verification.json'))
 assert sha(Path('/auditcode/L_ARCHIVE_ALLOWLIST.json'))=='b52036d7069600ca40b876d5d1a58dcbd4b13ab2bf666a133de5a501ee64ff07'
 assert sha(Path('/auditcode/L_verification.json'))=='5212dabcd493534b78f52a2a5cd889a37d579428e0a3129f7fa827ca995f64b4' and Lproof['passed']
 assert src['L_frozen_sha256']==sha(ROOT/'source_refs/L_frozen.json')==Lproof['frozen_sha256']==proto['L_frozen_sha256']
 assert src['L_protocol_sha256']==proto['L_protocol_sha256']==Lallow['files']['code/protocol.json']['sha256']
 assert src['L_runtime_sha256']==sha(ROOT/'code/runtime_support.json')==Lallow['files']['code/runtime_support.json']['sha256']
 assert src['source_records_unchanged'] and src['control_model_refits']==0 and len(src['control_records'])==6
 for f,k in [('L_completed.jsonl','source_completed_log_sha256'),('L_completion.json','source_completion_sha256')]:assert sha(ROOT/'source_refs'/f)==src[k]
 lfrozen=read(ROOT/'source_refs/L_frozen.json')['files']
 lentries=[json.loads(line)for line in (ROOT/'source_refs/L_completed.jsonl').read_text().splitlines()];lmap={e['task_id']:e for e in lentries};assert len(lentries)==len(lmap)==24
 assert src['source_completed_log_sha256']==Lproof['source_hashes']['results/completed.jsonl']
 assert sha(ROOT/'source_refs/L_completion.json')==Lallow['files']['results/completion.json']['sha256']
 for n,h in proto['unchanged_L_model_files'].items():assert sha(ROOT/'code'/n)==h==Lallow['files']['code/'+n]['sha256']
 gate=read(ROOT/'results/reference_gate.json');assert gate['passed'] and gate['exact_member_fold_seed_vectors']==90 and gate['reused_records']==6 and gate['new_control_fits']==0
 support=read(ROOT/'code/runtime_support.json')
 for group in ['sources','checkpoint_files']:
  for name,meta in support[group].items():assert Path(name).stat().st_size==meta['bytes'] and sha(name)==meta['sha256'],name
 diag=read(ROOT/'results/stack_diagnostics.json');saved={}
 for d in diag['prediction_details']:
  k=(d['panel_id'],d['architecture'],d['year'],str(d['seed']));assert k not in saved;saved[k]=d
 assert len(saved)==4128
 rows=defaultdict(list);members_checked=0;refs=0;scored=0;max_score_delta=0.;widths={};ranges={};fit_total=0;all_vectors={};all_keys={};all_records={};truths={};newfits=0;reusedfits=0
 for e in entries:
  task=tasks[e['task_id']];year=task['outer_year'];tid=task['id'];reuse=task['kind']=='reused_L_control';assert e['kind']==task['kind']
  expected_path=f'source_refs/records/{tid}.json'if reuse else f'results/jobs/{tid}/result.json';assert e['file']==expected_path
  path=ROOT/e['file'];assert sha(path)==e['sha256'];r=read(path);all_records[(r['panel_id'],year)]=r
  for field in ['panel_id','policy_id','outer_year']:assert r[field]==task[field]
  assert r['task_id']==tid and p['protocol_sha256']==sha(ROOT/'code/protocol.json')
  if reuse:
   original=src['control_records'][tid];assert original['source_completed_entry']==lmap[tid] and original['file']==e['file']
   assert sha(path)==original['sha256']==lmap[tid]['sha256']==Lallow['files'][f'results/jobs/{tid}/result.json']['sha256']
   assert r['protocol_sha256']==proto['L_protocol_sha256'] and r['input_manifest_sha256']==original['source_input_manifest_sha256']==lfrozen[f'inputs/{tid}/manifest.json']
  else:assert r['protocol_sha256']==p['protocol_sha256'] and r['input_manifest_sha256']==task['input_manifest_sha256']
  im=read(ROOT/'inputs'/tid/'manifest.json');assert sha(ROOT/'inputs'/tid/'manifest.json')==task['input_manifest_sha256']
  assert r['columns']==im['columns'] and r['label_audit']==im['label_audit']
  if reuse:
   om=original['source_input_manifest'];assert {k:v for k,v in om.items()if k!='protocol_sha256'}=={k:v for k,v in im.items()if k!='protocol_sha256'}
   assert hashlib.sha256((json.dumps(om,indent=2,allow_nan=False)+'\n').encode()).hexdigest()==original['source_input_manifest_sha256']
   for fn,meta in om['files'].items():assert meta['sha256']==lfrozen[f'inputs/{tid}/{fn}']
  widths[r['panel_id']]=len(r['columns'])
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
  if reuse:reusedfits+=9
  else:newfits+=9
  assert not r['query_outcome_labels_accessed'] and not r['query_outcomes_accessed'] and not r['learned_weights'] and r['selector_fits']==0
  ns=r['namespace_proof'];assert ns['passed'] and ns['input_files']==['inference.npz','manifest.json','training.npz'] and ns['inaccessible_paths']==['/scoring','/reference','/h_reference','/home/ubuntu/nba/handoff']
  assert r['runtime']['support_sha256']==sha(ROOT/'code/runtime_support.json') and r['runtime']['versions']==support['versions']
  assert sha(ROOT/'scoring'/f'{year}.npz')==p['scoring'][str(year)]['sha256']
  with np.load(ROOT/'scoring'/f'{year}.npz',allow_pickle=False)as q:
   assert q['pid'].tolist()==qp;truth=q['legacy_truth'];mask=q['observed_truth_mask']
  assert truth.shape==(n,) and np.isfinite(truth).all() and mask.shape==(n,) and mask.dtype==np.dtype(bool) and int(mask.sum())>1
  ranges[str(year)]={'full_query_rows':n,'observed_subset_rows':int(mask.sum()),'training_rows':len(tp),'max_label_season':la['max_actual_label_season']}
  truths[year]=(qp,truth,mask);qkeys=keys(Q);all_keys[(r['panel_id'],year)]=[digest(k)for k in qkeys];seed_vectors={};assert [s['seed']for s in r['seed_results']]==[0,101,202]
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
    if reuse:refs+=1
   seed_vectors[seed]=vs
  averaged={f:seed_vectors[0][f] if f.startswith('ridge_') else np.sum([ranks2(seed_vectors[s][f])for s in [0,101,202]],axis=0,dtype=np.int64)/(6*n) for f in families}
  assert set(r['fixed_three_seed_family_rank_average']['members'])==set(families)
  for f,v in averaged.items():exact(v,r['fixed_three_seed_family_rank_average']['members'][f])
  modes=[(s['seed'],seed_vectors[s['seed']],s['architectures'])for s in r['seed_results']]+[('fixed_three_seed_family_rank_average',averaged,r['fixed_three_seed_family_rank_average']['architectures'])]
  for mode,vs,stored_arch in modes:
   all_vectors[(r['panel_id'],year,mode)]=vs
   assert set(stored_arch)==set(recipes)
   vectors={name:blend(vs,recipe,n)for name,recipe in recipes.items()}
   for name,v in vectors.items():exact(v,stored_arch[name])
   vectors.update({'control_'+f:v for f,v in vs.items()})
   for name,v in vectors.items():
    d=saved[(r['panel_id'],name,year,str(mode))];assert d['query_pids']==qp;exact(v,d['prediction'])
    actual={'full':rho(v,truth),'observed':rho(v[mask],truth[mask])}
    for metric,value in actual.items():close(value,d[metric]);max_score_delta=max(max_score_delta,abs(value-d[metric]))
    rows[(r['panel_id'],name)].append({'year':year,'seed':mode,**actual});scored+=1
 assert fit_total==216 and newfits==162 and reusedfits==54 and refs==90 and members_checked==360 and scored==4128
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

 assert gate['source_record_hash_manifest_sha256']==digest({tid:s['sha256']for tid,s in src['control_records'].items()})
 assert gate['source_completed_log_sha256']==src['source_completed_log_sha256'] and gate['source_manifest_sha256']==sha(ROOT/'source_refs/manifest.json')
 for year in p['outer_years']:
  base=all_records[('base44',year)]
  for panel in widths:
   assert all(all_records[(panel,year)][k]==base[k]for k in ['training_pids','query_pids','target_hash','label_audit','policy_id'])
 cp=proto['cross_panel_stacks'];assert p['cross_panel_stacks']==cp and cp['distinct_recipes']==len(cp['recipes'])==950
 assert cp['aggregation_modes']==[0,101,202,'fixed_three_seed_family_rank_average']
 cross_saved={}
 for d in diag['cross_panel_prediction_details']:
  key=(d['architecture'],d['year'],str(d['seed']));assert key not in cross_saved;cross_saved[key]=d
 assert len(cross_saved)==11400;signatures=set();cross_rows=defaultdict(list);cross_summary={};rankcache={};cross_count=0;alias_count=0
 for recipe in cp['recipes']:
  ms=recipe['members'];assert recipe['kind']=='fixed_rank_weights' and recipe['weight_total']==12
  assert all(type(m['units'])is int and m['units']>0 and m['panel_id']in widths for m in ms) and sum(m['units']for m in ms)==12
  signature=tuple(sorted((m['family'],m['panel_id'],m['units'])for m in ms));assert signature not in signatures;signatures.add(signature)
  for alias in recipe['design_aliases']:
   same=recipes[alias['same_panel_recipe']];assert sorted((m['family'],m['units'])for m in same['members'])==sorted((m['family'],m['units'])for m in ms);alias_count+=1
  multi=len({'ridge'if m['family'].startswith('ridge_')else m['family']for m in ms})>=2
  for year in p['outer_years']:
   qp,truth,mask=truths[year];n=len(qp)
   for mode in cp['aggregation_modes']:
    rr=[];kk=[]
    for m in ms:
     key=(m['panel_id'],year,mode,m['family'])
     if key not in rankcache:rankcache[key]=ranks2(all_vectors[key[:3]][m['family']])
     rr.append((m['units'],rankcache[key]));kk.append(all_keys[(m['panel_id'],year)])
    v=np.array([sum(u*int(r[i])for u,r in rr)for i in range(n)],dtype=np.int64)/(24*n)
    union=[list(k)for k in zip(*kk)];groups={}
    for k,value in zip(union,v):
     k=tuple(k)
     if k in groups:assert groups[k]==value
     else:groups[k]=value
    d=cross_saved[(recipe['id'],year,str(mode))];exact(v,d['prediction']);assert d['prediction_hash']==ah(v)
    assert d['query_pids']==qp and d['multi_family_stack']==multi and d['participating_views']==sorted({m['panel_id']for m in ms})
    assert d['union_input_vector_key_hash']==digest(union) and d['fixed_weights'] and not d['query_outcome_labels_accessed']
    actual={'year':year,'seed':mode,'full':rho(v,truth),'observed':rho(v[mask],truth[mask])}
    for metric in ['full','observed']:close(actual[metric],d[metric]);max_score_delta=max(max_score_delta,abs(actual[metric]-d[metric]))
    cross_rows[recipe['id']].append(actual);cross_count+=1
  rr=cross_rows[recipe['id']];direct=[r for r in rr if type(r['seed'])is int];fixed=[r for r in rr if type(r['seed'])is str];assert len(direct)==9 and len(fixed)==3
  item={'architecture':recipe['id'],'recipe':recipe,'multi_family_every_fold_seed':multi,'member_control':not multi}
  for metric in ['full','observed']:
   item[metric]={'mean_score':mean([r[metric]for r in direct]),'fold_scores':{str(y):mean([r[metric]for r in direct if r['year']==y])for y in p['outer_years']},'seed_scores':{str(s):mean([r[metric]for r in direct if r['seed']==s])for s in p['seeds']},'fixed_three_seed_family_rank_average':mean([r[metric]for r in fixed])}
  cross_summary[recipe['id']]=item
 assert cross_count==11400 and len(signatures)==950 and alias_count==cp['pre_dedup_designs']==1824
 assert len(diag['cross_panel_summaries'])==950
 for s in diag['cross_panel_summaries']:
  z=cross_summary[s['architecture']];assert s['recipe']==z['recipe'] and s['multi_family_every_fold_seed']==z['multi_family_every_fold_seed'] and s['member_control']==z['member_control']
  for metric in ['full','observed']:
   for k in ['mean_score','fixed_three_seed_family_rank_average']:close(s[metric][k],z[metric][k])
   for k in ['fold_scores','seed_scores']:
    for f in z[metric][k]:close(s[metric][k][f],z[metric][k][f])
  same=z['recipe']['design_aliases'][0]['same_panel_recipe']
  for panel,suffix in [('base44','44'),('add_f50','f50')]:
   b=summaries[(panel,same)];close(s[f'full_gain_vs_same_recipe_{suffix}'],z['full']['mean_score']-b['full']['mean_score'])
   for key,target in [('fold_scores','full_fold_gains_vs_'),('seed_scores','full_seed_gains_vs_')]:
    for f in z['full'][key]:close(s[target+suffix][f],z['full'][key][f]-b['full'][key][f])
 cross_order=sorted(cross_summary.values(),key=lambda s:(-s['full']['mean_score'],s['architecture']))
 for field,multi in [('best_cross_panel_actual_stack',True),('best_cross_panel_standalone_control',False)]:
  winner=next(s for s in cross_order if s['multi_family_every_fold_seed']==multi);assert diag[field]['architecture']==winner['architecture']
 overall=max([diag['best_actual_multifamily_stack'],diag['best_cross_panel_actual_stack']],key=lambda s:s['full']['mean_score'])
 state=read(ROOT/'results/state.json');assert state['status']=='completed' and state['best_configuration']['id']==overall['architecture'] and state['best_configuration']['panel_id']==overall['panel_id'];close(state['best_configuration']['score'],overall['full']['mean_score'])
 assert diag['scored_prediction_records']==4128 and diag['cross_panel_scored_prediction_records']==11400
 evidence={'passed':True,'study':'R9M','frozen_sha256':PIN,'plan_sha256':PLAN_PIN,'frozen_files_verified':105,'result_records':24,'new_jobs':18,'new_registered_fits':162,'reused_control_records':6,'reused_original_fits':54,'saved_member_records_verified':360,'reused_control_member_vectors':90,'same_panel_score_records':4128,'cross_panel_score_records':11400,'same_panel_summaries_verified':344,'same_panel_comparisons_verified':301,'cross_panel_summaries_verified':950,'cross_panel_paired_reference_comparisons_verified':1900,'recipe_aliases_verified':1824,'maximum_score_absolute_difference':max_score_delta,'score_arithmetic':'Independent doubled tied ranks, centered math.fsum Pearson, exact member/tie/seed/blend arrays; scores and aggregates tolerance 2e-14. No coordinator or model imports.','runtime_sources_verified':len(support['sources']),'checkpoint_files_verified':len(support['checkpoint_files']),'model_fits_performed':0,'gpu_devices_available':False,'network_available':False,'other_studies_mounted':False,'no_2019plus_access':True,'scoring_truth_exported':False,'reused_controls_against_independent_L_archive':True,'registered_gate_order':'Pinned scheduler calls the exact source gate before submission; first six durable log entries are reused controls. No independent historical process tracing.','widths':widths,'cohort_contract':ranges,'best_actual_multifamily_stack':overall,'best_same_panel_stack':diag['best_actual_multifamily_stack'],'best_standalone_control':diag['best_member_control'],'best_cross_panel_standalone_control':diag['best_cross_panel_standalone_control'],'best_same_panel_by_panel':panelbest,'source_hashes':{n:sha(ROOT/n)for n in ['plan.json','results/completed.jsonl','results/result_manifest.json','results/stack_diagnostics.json','results/reference_gate.json','source_refs/manifest.json','launch_authorization.json']},'verifier_sha256':sha(Path(__file__)),'limitations':proto['limitations']+['Development full-pool correlation is primary. Complete-outcome subset is secondary; no goal attainment or unbiased holdout claim.','950 cross recipes plus same-panel recipes were examined on the same three development folds. Selection optimism remains.','Fixed three-seed family-rank averaging differs from mean fold/seed correlation.','Audit consistency and pinned scheduler ordering do not replace independent historical process tracing.']}
 write('verification.json',evidence)
 chosen=[n for n in frozen['files']if not n.startswith(('inputs/','scoring/'))]+['frozen.json','launch_authorization.json','results/completed.jsonl','results/completion.json','results/result_manifest.json','results/stack_diagnostics.json','results/reference_gate.json','results/cpu_preflight.json']+[e['file']for e in entries if e['kind']=='new_model_job']
 assert len(chosen)==len(set(chosen)) and all(not n.startswith(('inputs/','scoring/'))and not n.endswith('.npz')and '..'not in Path(n).parts for n in chosen)
 allow={'study':'R9M','policy':'Explicit original development results, original L controls, source hashes/metadata and code only. No input/scoring datasets, private labels/identities, K files, keys or raw source bodies. Parent controls publication.','files':{n:{'sha256':sha(ROOT/n),'bytes':(ROOT/n).stat().st_size}for n in sorted(chosen)}}
 write('ARCHIVE_ALLOWLIST.json',allow);archive=OUT/'r9m_saved_results.tar.gz'
 with archive.open('wb')as base:
  with gzip.GzipFile(fileobj=base,mode='wb',mtime=0,filename='')as gz:
   with tarfile.open(fileobj=gz,mode='w')as tar:
    for n in sorted(chosen):
     info=tar.gettarinfo(str(ROOT/n),arcname=n);assert info.isfile();info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o644
     with (ROOT/n).open('rb')as f:tar.addfile(info,f)
 with tarfile.open(archive,'r:gz')as tar:
  members=tar.getmembers();assert {m.name for m in members}==set(chosen)and len(members)==len(chosen)
  for m in members:
   data=tar.extractfile(m).read();assert len(data)==allow['files'][m.name]['bytes']and hashlib.sha256(data).hexdigest()==allow['files'][m.name]['sha256']
 write('archive_manifest.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'members':len(chosen),'uncompressed_bytes':sum(x['bytes']for x in allow['files'].values()),'member_hash_roundtrip_passed':True,'archive_allowlist_sha256':sha(OUT/'ARCHIVE_ALLOWLIST.json'),'verification_sha256':sha(OUT/'verification.json')})
 print(json.dumps({'passed':True,'best_stack':overall,'best_same_panel':diag['best_actual_multifamily_stack'],'best_control':diag['best_member_control'],'maximum_score_difference':max_score_delta,'archive':read(OUT/'archive_manifest.json')},indent=2))

if __name__=='__main__':main()
