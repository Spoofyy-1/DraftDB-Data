"""Single outer-task worker: its namespace has no validation truth or scorer."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
import argparse,json,hashlib,time,tempfile
import numpy as np
import pandas as pd
import stack_core as C
from model_backend import Backend,ridge_statistics,ridge_transform,finite_list
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
 columns=manifest['columns'];assert len(set(columns))==len(columns)and len(columns)in[44,174]
 panel_id=manifest['panel_id'];assert isinstance(panel_id,str)and panel_id.startswith('panel')
 panel_width=int(panel_id.removeprefix('panel'));assert panel_id==f'panel{panel_width}'and panel_width==len(columns)and panel_width in protocol['panel_ids']and manifest['policy_id']in protocol['policy_ids']
 assert tr['X'].shape==(len(tr['pid']),len(columns))and te['X'].shape==(len(te['pid']),len(columns))and len(te['pid'])>0
 assert tr['pid'].ndim==te['pid'].ndim==1 and tr['pid'].dtype.kind in['U','S']and te['pid'].dtype.kind in['U','S']
 assert all(tr[k].shape==(len(tr['pid']),)for k in ['draft_year','label_value','y','prefix_length'])
 assert np.isin(tr['prefix_length'],[1,2,3,4,5]).all()and tr['draft_year'].max()<manifest['outer_year']and tr['draft_year'].min()>=2000
 if manifest['policy_id']=='h_s2000_gap1_drafted_h2':assert np.all(tr['prefix_length']==2)
 else:assert tr['draft_year'].min()>=2007
 pids=tr['pid'].tolist();query_pids=te['pid'].tolist();assert all(isinstance(p,str)for p in pids+query_pids)and not set(pids)&set(query_pids)
 assert np.array_equal(C.canonical_order(pids),np.arange(len(pids)))and np.array_equal(C.canonical_order(query_pids),np.arange(len(query_pids)))
 audit=manifest['label_audit'];assert audit['outer_year']==manifest['outer_year']and audit['max_actual_label_season']<=manifest['outer_year']-1 and audit['all_labels_finite_observed']and not audit['missing_training_labels_zero_filled']
 assert audit['training_pid_hash']==C.digest(pids)and audit['label_value_hash']==C.array_hash(tr['label_value'])and audit['target_hash']==C.array_hash(tr['y'])and audit['source_fact_hash']
 assert np.isfinite(tr['label_value']).all()and np.isfinite(tr['y']).all()and np.array_equal(C.gaussian_target(tr['label_value'],tr['draft_year']),tr['y'])
 assert not np.isinf(tr['X']).any()and not np.isinf(te['X']).any()and len(pids)>=40
 assignment=C.assignments(pids);assert set(assignment)=={0,1,2}
 for f in range(3):assert np.sum(assignment!=f)>=20 and np.sum(assignment==f)>0
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
 parser=argparse.ArgumentParser();parser.add_argument('--input-dir',required=True);parser.add_argument('--output',required=True);parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args();protocol,manifest,tr,te=load(args.input_dir);backend=Backend(protocol)
 inaccessible=['/scoring','/reference','/h_reference','/home/ubuntu/nba/handoff'];assert all(not Path(p).exists()for p in inaccessible),'Unexpected access to external study or scoring paths'
 namespace_proof={'input_files':sorted(p.name for p in Path(args.input_dir).iterdir()),'inaccessible_paths':inaccessible,'passed':True}
 if args.preflight_only:
  def reject_fit(*a,**k):raise AssertionError('No fitting during worker preflight')
  for family in ['selector','ridge','xgb_q25','residual_q25','tabicl']:
   for seed in([0]if family in['selector','ridge']else protocol['seeds']):m,kw=backend.constructor(family,seed);m.fit=reject_fit
  frame=pd.DataFrame(tr['X'],columns=manifest['columns']);query=pd.DataFrame(te['X'],columns=manifest['columns']);mean,std=ridge_statistics(frame);standard_train=ridge_transform(frame,mean,std);standard_query=ridge_transform(query,mean,std);assert np.isfinite(np.asarray(standard_train)).all()and np.isfinite(np.asarray(standard_query)).all()
  proof={'passed':True,'preflight_only':True,'model_fits':0,'panel_id':manifest['panel_id'],'policy_id':manifest['policy_id'],'outer_year':manifest['outer_year'],'training_rows':len(tr['pid']),'query_rows':len(te['pid']),'input_manifest_sha256':sha(Path(args.input_dir)/'manifest.json'),'protocol_sha256':sha(CODE/'protocol.json'),'training_matrix_hash':C.array_hash(tr['X']),'query_matrix_hash':C.array_hash(te['X']),'label_audit':manifest['label_audit'],'namespace_proof':namespace_proof,'runtime':runtime(),'inner_counts':[int(np.sum(C.assignments(tr['pid'].tolist())==f))for f in range(3)],'Ridge_preprocessing_only':{'training_mean':finite_list(mean),'sample_std_ddof1':finite_list(std),'standardized_training_hash':C.array_hash(standard_train),'standardized_query_hash':C.array_hash(standard_query)}};save_new(args.output,proof);print(json.dumps({k:v for k,v in proof.items()if k not in ['Ridge_preprocessing_only','label_audit']}));return
 support=runtime();started=time.time();X=pd.DataFrame(tr['X'],columns=manifest['columns']);query=pd.DataFrame(te['X'],columns=manifest['columns']);metadata=pd.DataFrame({'pid':tr['pid'],'draft_year':tr['draft_year']})
 result=C.run_outer(X,query,metadata,te['pid'].tolist(),tr['label_value'],tr['y'],manifest['outer_year'],backend,seeds=protocol['seeds'],label_audit=manifest['label_audit'])
 expected={'selector':4,'ridge':4,'tabicl':12,'xgb_q25':12,'residual_q25':3};assert dict(backend.counts)==expected
 result.update(task_id=manifest['task_id'],panel_id=manifest['panel_id'],policy_id=manifest['policy_id'],query_pids=te['pid'].tolist(),input_manifest_sha256=sha(Path(args.input_dir)/'manifest.json'),protocol_sha256=sha(CODE/'protocol.json'),fit_counts=dict(backend.counts),runtime=support,namespace_proof=namespace_proof,seconds=time.time()-started,query_outcome_labels_accessed=False)
 save_new(args.output,result);print(json.dumps({'task_id':result['task_id'],'fit_counts':result['fit_counts'],'output_sha256':sha(Path(args.output)),'seconds':result['seconds']}))
if __name__=='__main__':main()
