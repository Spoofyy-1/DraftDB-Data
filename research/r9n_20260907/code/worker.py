"""Single outer-task worker: its namespace has no validation truth or scorer."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import argparse,json,hashlib,time,tempfile
import numpy as np
import pandas as pd
import stack_core as C
from model_backend import Backend
import preprocessing as P
CODE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(directory):
 directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text());protocol=json.loads((CODE/'protocol.json').read_text())
 assert {p.name for p in directory.iterdir()}=={'training.npz','inference.npz','manifest.json'},'Unexpected files in model input directory'
 assert manifest['outer_year']in[2012,2013,2014]and protocol['seeds']==[0,101,202]and protocol['outer_years']==[2012,2013,2014]
 assert manifest['protocol_sha256']==sha(CODE/'protocol.json')
 assert set(manifest['files'])=={'training.npz','inference.npz'}
 for name,info in manifest['files'].items():assert sha(directory/name)==info['sha256']
 with np.load(directory/'training.npz',allow_pickle=False)as f:
  assert set(f.files)=={'X','pid','draft_year','label_value','y','prefix_length'};tr={k:f[k].copy()for k in f.files}
 with np.load(directory/'inference.npz',allow_pickle=False)as f:
  assert set(f.files)=={'X','pid'};te={k:f[k].copy()for k in f.files}
 columns=manifest['columns'];assert len(set(columns))==len(columns)
 panel=next(p for p in protocol['panels']if p['id']==manifest['panel_id']);assert columns==panel['columns']and len(columns)==panel['width']and manifest['policy_id']==protocol['policy_id']=='h_s2008_gap1_all_h1'
 assert tr['X'].shape==(len(tr['pid']),len(columns))and te['X'].shape==(len(te['pid']),len(columns))and len(te['pid'])>0
 assert tr['pid'].ndim==te['pid'].ndim==1 and tr['pid'].dtype.kind in['U','S']and te['pid'].dtype.kind in['U','S']
 assert all(tr[k].shape==(len(tr['pid']),)for k in ['draft_year','label_value','y','prefix_length'])
 assert np.all(tr['prefix_length']==1)and tr['draft_year'].max()<manifest['outer_year']and tr['draft_year'].min()>=2008
 pids=tr['pid'].tolist();query_pids=te['pid'].tolist();assert all(isinstance(p,str)for p in pids+query_pids)and not set(pids)&set(query_pids)
 assert np.array_equal(C.canonical_order(pids),np.arange(len(pids)))and np.array_equal(C.canonical_order(query_pids),np.arange(len(query_pids)))
 audit=manifest['label_audit'];assert audit['outer_year']==manifest['outer_year']and audit['max_actual_label_season']<=manifest['outer_year']-1 and audit['all_labels_finite_observed']and not audit['missing_training_labels_zero_filled']
 assert audit['training_pid_hash']==C.digest(pids)and audit['label_value_hash']==C.array_hash(tr['label_value'])and audit['target_hash']==C.array_hash(tr['y'])and audit['source_fact_hash']
 assert np.isfinite(tr['label_value']).all()and np.isfinite(tr['y']).all()and np.array_equal(C.gaussian_target(tr['label_value'],tr['draft_year']),tr['y'])
 assert not np.isinf(tr['X']).any()and not np.isinf(te['X']).any()and len(pids)>=40
 profile=next(p for p in protocol['profiles']if p['id']==manifest['profile_id'])
 for seed in protocol['seeds']:
  P.parameters(profile,seed,protocol);expected=manifest['preprocessing_designs'][str(seed)]
  assert expected['profile_id']==profile['id']and expected['seed']==seed and expected['original_training_matrix_hash']==C.array_hash(tr['X'])and expected['original_query_matrix_hash']==C.array_hash(te['X'])and expected['original_target_hash']==C.array_hash(tr['y'])and expected['columns']==columns and expected['training_pid_hash']==C.digest(pids)and expected['query_pid_hash']==C.digest(query_pids)
 return protocol,manifest,tr,te
def runtime():
 path=CODE/'runtime_support.json';assert path.exists(),'Pinned runtime/checkpoint manifest is required before any model fits';support=json.loads(path.read_text())
 assert support.get('sources')and support.get('checkpoint_files')
 for key in ['sources','checkpoint_files']:
  for name,info in support[key].items():assert sha(Path(name))==(info['sha256']if isinstance(info,dict)else info)
 return {'support_sha256':sha(path),'versions':support.get('versions',{})}
def save_new(path,value):
 raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
 with tempfile.NamedTemporaryFile(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent,delete=False)as f:
  temporary=Path(f.name);f.write(raw);f.flush();os.fsync(f.fileno())
 try:
  try:os.link(temporary,path)
  except FileExistsError:assert path.read_bytes()==raw,'Conflicting immutable worker output'
  directory_fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(directory_fd)
  finally:os.close(directory_fd)
 finally:temporary.unlink(missing_ok=True)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--input-dir',required=True);parser.add_argument('--output',required=True);parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args()
 protocol,m,tr,te=load(args.input_dir);profile=next(p for p in protocol['profiles']if p['id']==m['profile_id']);X=pd.DataFrame(tr['X'],columns=m['columns']);q=pd.DataFrame(te['X'],columns=m['columns'])
 forbidden=['/scoring','/reference','/h_reference','/source_refs','/home/ubuntu/nba/handoff'];assert all(not Path(p).exists()for p in forbidden);namespace={'passed':True,'inaccessible_paths':forbidden,'input_files':sorted(p.name for p in Path(args.input_dir).iterdir())};support=runtime()
 if args.preflight_only:
  designs={str(seed):P.prepare(X,tr['y'],q,profile,seed,protocol,tr['pid'].tolist(),te['pid'].tolist())for seed in protocol['seeds']};assert designs==m['preprocessing_designs']
  save_new(args.output,{'passed':True,'preflight_only':True,'model_fits':0,'task_id':m['task_id'],'profile_id':profile['id'],'input_manifest_sha256':sha(Path(args.input_dir)/'manifest.json'),'protocol_sha256':sha(CODE/'protocol.json'),'training_rows':len(X),'query_rows':len(q),'preprocessing_design_hash':C.digest(designs),'namespace_proof':namespace,'runtime':support});return
 start=time.time();backend=Backend(protocol,profile);members=[]
 for seed in protocol['seeds']:
  raw,audit=backend.fit_predict(X,tr['y'],q,tr['pid'].tolist(),seed,m['preprocessing_designs'][str(seed)]);pred,ties=C.canonicalize(q,raw,te['pid'].tolist());members.append({'seed':seed,'raw_predictions':raw.tolist(),'canonical_predictions':pred.tolist(),'model_audit':audit,'tie_audit':ties})
 assert backend.fits==3;result={'task_id':m['task_id'],'profile_id':profile['id'],'panel_id':m['panel_id'],'policy_id':m['policy_id'],'outer_year':m['outer_year'],'columns':m['columns'],'training_pids':tr['pid'].tolist(),'query_pids':te['pid'].tolist(),'training_matrix_hash':C.array_hash(X),'query_matrix_hash':C.array_hash(q),'target_hash':C.array_hash(tr['y']),'label_audit':m['label_audit'],'members':members,'fit_counts':{'tabicl':3},'input_manifest_sha256':sha(Path(args.input_dir)/'manifest.json'),'protocol_sha256':sha(CODE/'protocol.json'),'runtime':support,'namespace_proof':namespace,'seconds':time.time()-start,'query_outcome_labels_accessed':False}
 save_new(args.output,result);print(json.dumps({'task_id':result['task_id'],'fits':3,'seconds':result['seconds']}))
if __name__=='__main__':main()
