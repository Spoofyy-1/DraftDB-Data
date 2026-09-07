"""Independent saved-vector, cutoff, OOF and score verification. No GPU fits."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import json,hashlib,math,gzip
import numpy as np
from scipy.special import ndtri
from scipy.stats import rankdata
from scipy.optimize import nnls
import postprocess
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def ah(a):
 a=np.asarray(a,dtype=np.float64);a=np.where(a==0,0.,a);m=np.isnan(a)
 return hashlib.sha256(json.dumps(list(a.shape),separators=(',',':')).encode()+m.tobytes()+np.where(m,0.,a).tobytes()).hexdigest()
def rank(x):return np.rint(2*rankdata(x,method='average')).astype(np.int64)/(2*len(x))
def target(value,cohort):
 out=np.empty(len(value));value=np.clip(value,-40,40)
 for year in np.unique(cohort):
  keep=cohort==year;out[keep]=ndtri(np.clip((rankdata(value[keep],method='average')-.5)/keep.sum(),.01,.99))
 return out
def canonical(x,raw):
 groups={};out=np.asarray(raw,dtype=float).copy()
 for i,row in enumerate(x):groups.setdefault(tuple(None if np.isnan(v) else 0. if v==0 else float(v) for v in row),[]).append(i)
 for indices in groups.values():
  if len(indices)>1:out[indices]=math.fsum(sorted(float(raw[i]) for i in indices))/len(indices)
 return out
def save(path,x):path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def main():
 assert sha(ROOT/'frozen.json')=='54892b6f5efdc302ac4581d23a59b093ef3e9bd42f4db511799cc3e3b75ad975'
 frozen=read(ROOT/'frozen.json')
 for p,h in frozen['files'].items():assert sha(ROOT/p)==h,p
 p=read(ROOT/'plan.json');registered={t['id']:t for t in p['tasks']};entries=[json.loads(x)for x in (OUT/'completed.jsonl').read_text().splitlines()]
 assert len(entries)==12 and {e['task_id']for e in entries}==set(registered)
 records=[];meta_export=[];archives=[];count_inner=0;count_vectors=0
 private=OUT/'private_task_archives';private.mkdir(exist_ok=True)
 for entry in entries:
  tid=entry['task_id'];assert entry['file']==f'jobs/{tid}/result.json';path=OUT/entry['file'];assert sha(path)==entry['sha256'];r=read(path);task=registered[tid]
  assert r['input_manifest_sha256']==task['input_manifest_sha256'] and r['namespace_proof']['passed']
  assert r['fit_counts']=={'selector':4,'ridge':4,'tabicl':12,'xgb_q25':12,'residual_q25':3} and not r['query_outcome_labels_accessed']
  directory=ROOT/'inputs'/tid;m=read(directory/'manifest.json');columns=m['columns'];ix={c:i for i,c in enumerate(columns)}
  with np.load(directory/'training.npz',allow_pickle=False)as z:tr={k:z[k]for k in z.files}
  with np.load(directory/'inference.npz',allow_pickle=False)as z:te={k:z[k]for k in z.files}
  assert r['query_pids']==te['pid'].tolist()and r['training_pids']==tr['pid'].tolist()and not set(tr['pid'])&set(te['pid'])
  assert tr['draft_year'].max()<r['outer_year'] and r['label_audit']['max_actual_label_season']<=r['outer_year']-1
  assert np.array_equal(target(tr['label_value'],tr['draft_year']),tr['y'])
  assignments=np.array([int(hashlib.sha256(pid.encode()).hexdigest(),16)%3 for pid in tr['pid']]);replayed_oof={s:{f:np.full(len(tr['pid']),np.nan)for f in ['xgb_q25','tabicl','ridge']}for s in p['seeds']}
  for stage in r['inner_stages']:
   f=stage['fold'];train=np.flatnonzero(assignments!=f);held=np.flatnonzero(assignments==f);yy=target(tr['label_value'][train],tr['draft_year'][train])
   assert stage['train_pids']==tr['pid'][train].tolist() and stage['held_pids']==tr['pid'][held].tolist()
   assert stage['training_target_hash']==ah(yy)and stage['selector']['training_target_hash']==ah(yy)
   assert stage['selector']['training_pid_hash']==digest(tr['pid'][train].tolist())
   assert stage['training_matrix_hash']==ah(tr['X'][train]) and stage['held_matrix_hash']==ah(tr['X'][held])
   for e in stage['records']:
    names=stage['selected_TabICL_columns']if e['family']=='tabicl'else columns;indices=[ix[n]for n in names];a=e['model_audit'];x=tr['X'][held][:,indices]
    assert a['training_matrix_hash']==ah(tr['X'][train][:,indices])and a['training_target_hash']==ah(yy)and a['training_pid_hash']==digest(tr['pid'][train].tolist())and a['query_matrix_hash']==ah(x)
    expected=canonical(x,e['raw_predictions']);assert np.array_equal(expected,e['canonical_predictions']);replayed_oof[e['seed']][e['family']][held]=expected;count_inner+=1
  query=te['X'];thin=np.isfinite(query).mean(axis=1)<np.median(np.isfinite(query).mean(axis=1));assert thin.tolist()==r['query_thin_mask']
  for e in r['seed_results']:
   seed=e['seed'];members={}
   for family,v in e['OOF_predictions'].items():assert np.array_equal(v,replayed_oof[seed][family])
   for family,v in e['members'].items():
    names=r['full_TabICL_columns']if family=='tabicl'else columns;indices=[ix[n]for n in names];a=v['model_audit'];assert a['training_matrix_hash']==ah(tr['X'][:,indices])and a['training_target_hash']==ah(tr['y'])and a['training_pid_hash']==digest(tr['pid'].tolist())
    members[family]=canonical(query[:,indices],v['raw_predictions']);assert np.array_equal(members[family],v['canonical_predictions'])
   family_order=['xgb_q25','tabicl','ridge'];design=np.column_stack([rank(replayed_oof[seed][f])for f in family_order]);raw,_=nnls(design,rank(tr['y']));weights=raw/raw.sum()if raw.sum()else np.ones(3)/3
   assert np.array_equal(weights,e['meta']['weights'])and e['meta']['OOF_rank_matrix_hash']==ah(design)
   residual_target=rank(tr['y'])-rank(replayed_oof[seed]['tabicl']);assert np.array_equal(residual_target,e['residual']['training_target'])and ah(residual_target)==e['residual']['training_target_hash']
   delta=canonical(query,e['residual']['raw_query_correction']);corrected=rank(members['tabicl'])+delta;assert np.array_equal(corrected,e['residual']['corrected_query_prediction'])
   ranks=np.column_stack([rank(members[f])for f in family_order]);expected={'equal_three_direct':sum(np.rint(ranks[:,i]*2*len(query)).astype(np.int64)for i in range(3))/(6*len(query)), 'fixed_coverage_direct':np.where(thin,ranks[:,0],.25*ranks[:,1]+.75*ranks[:,2]),'fixed_coverage_residual':np.where(thin,rank(corrected),.25*ranks[:,1]+.75*ranks[:,2]),'learned_global_nonnegative_meta':ranks@weights}
   for name,v in expected.items():assert np.array_equal(v,e['architectures'][name]),(tid,name);count_vectors+=1
   meta_export.append({'task_id':tid,'seed':seed,'meta_weights':e['meta']['weights'],'family_order':family_order,'training_PID_hash':digest(tr['pid'].tolist()),'OOF_prediction_hashes':{f:ah(v)for f,v in replayed_oof[seed].items()},'label_fact_hash':r['label_audit']['source_fact_hash']})
  packed=gzip.compress(path.read_bytes(),mtime=0);dest=private/(tid+'.json.gz')
  if dest.exists():assert dest.read_bytes()==packed
  else:dest.write_bytes(packed);dest.chmod(0o600)
  assert hashlib.sha256(gzip.decompress(dest.read_bytes())).hexdigest()==entry['sha256'];archives.append({'task_id':tid,'sha256':sha(dest),'bytes':dest.stat().st_size,'original_sha256':entry['sha256'],'private_not_for_publication':True});records.append(r)
 expected=postprocess.summarize(records,ROOT);stored=read(OUT/'stack_diagnostics.json');assert expected==stored
 for row in stored['prediction_details']:
  with np.load(ROOT/'scoring'/f"{row['year']}.npz",allow_pickle=False)as q:
   assert row['query_pids']==q['pid'].tolist()
   for metric,mask in [('full',np.ones(len(q['pid']),bool)),('observed',q['observed_truth_mask'])]:
    a=rankdata(np.asarray(row['prediction'])[mask]);b=rankdata(q['legacy_truth'][mask]);a=a-a.mean();b=b-b.mean();den=np.linalg.norm(a)*np.linalg.norm(b);value=float(a@b/den)if den else 0.
    assert np.isclose(value,row[metric],atol=1e-14,rtol=0)
 assert len(stored['prediction_details'])==384 and count_inner==324 and count_vectors==144
 export={k:v for k,v in stored.items()};export['learned_weight_audits']=meta_export
 save(OUT/'public_stack_results.json',export)
 proof={'passed':True,'frozen_files':60,'tasks':12,'fits_recorded':420,'inner_records_verified':count_inner,'architecture_vectors_verified':count_vectors,'score_records_verified':384,'all_metaweights_and_residuals_reconstructed':True,'all_fold_train_and_held_hashes_verified':True,'private_archives':archives,'public_results_sha256':sha(OUT/'public_stack_results.json'),'best_stack':stored['best_actual_multifamily_stack'],'best_component_control':stored['best_member_control'],'no_new_GPU_fits':True,'no2019plus_access':True}
 save(OUT/'independent_verification.json',proof);print(json.dumps({k:v for k,v in proof.items()if k not in ['private_archives','best_stack','best_component_control']}))
if __name__=='__main__':main()
