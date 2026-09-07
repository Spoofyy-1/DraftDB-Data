"""Remote-only input/source-control preparation. No models or score-based selection."""
from pathlib import Path
import hashlib,json,os,shutil,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;L=ROOT.parent/'r9l';K=ROOT.parent/'r9k'
sys.path.insert(0,str(ROOT/'code'));import stack_core as C

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,d):
 with p.open('x')as f:f.write(json.dumps(d,indent=2,allow_nan=False)+'\n')
def arrays(path):
 with np.load(path,allow_pickle=False)as f:return {k:f[k].copy()for k in f.files}
def main():
 os.umask(0o077);protocol=read(ROOT/'code/protocol.json');assert sha(L/'frozen.json')==protocol['L_frozen_sha256']
 for name,digest in read(L/'frozen.json')['files'].items():assert sha(L/name)==digest,name
 lp=read(L/'code/protocol.json');assert sha(L/'code/protocol.json')==protocol['L_protocol_sha256']
 for name,digest in protocol['unchanged_L_model_files'].items():assert sha(ROOT/'code'/name)==sha(L/'code'/name)==digest
 for name in ['tabicl','ridge','catboost','architectures','labels','policy_id','outer_years','seeds']:assert protocol[name]==lp[name]
 complete=read(L/'results/completion.json');assert complete['status']=='completed'and complete['tasks']==24
 source_log=L/'results/completed.jsonl';raw=source_log.read_bytes();assert raw.endswith(b'\n')
 entries=[json.loads(s)for s in raw.splitlines()];logged={e['task_id']:e for e in entries};assert len(logged)==len(entries)==24
 pm=read(K/'panels/panel_manifest.json');assert sha(K/'panels/panel_manifest.json')==protocol['source_panel_manifest_sha256'];path=K/'panels/panel174.csv';assert sha(path)==pm['outputs']['panel174.csv']['sha256']
 panel=pd.read_csv(path,float_precision='round_trip').set_index('pid');assert len(panel)==1428 and panel.index.is_unique and panel.draft_year.le(2018).all()
 for folder in ['inputs','scoring','source_refs']:(ROOT/folder).mkdir()
 (ROOT/'source_refs/records').mkdir();tasks=[];source_controls={};scoring={}
 for y in protocol['outer_years']:
  base=L/'inputs'/f'base44_y{y}';bm=read(base/'manifest.json');tr=arrays(base/'training.npz');q=arrays(base/'inference.npz')
  for f,info in bm['files'].items():assert sha(base/f)==info['sha256']
  assert np.array_equal(panel.loc[tr['pid'],protocol['original_H44_columns']].to_numpy(float),tr['X'],equal_nan=True)and np.array_equal(panel.loc[q['pid'],protocol['original_H44_columns']].to_numpy(float),q['X'],equal_nan=True)
  src=L/'scoring'/f'{y}.npz';assert sha(src)==read(L/'plan.json')['scoring'][str(y)]['sha256'];dest=ROOT/'scoring'/f'{y}.npz';shutil.copyfile(src,dest);scoring[str(y)]={'sha256':sha(dest),'source_sha256':sha(src),'not_mounted_in_model_worker':True}
  for spec in protocol['panels']:
   tid=f"{spec['id']}_y{y}";out=ROOT/'inputs'/tid;out.mkdir();reuse=spec['id']in['base44','add_f50']
   if reuse:
    original=L/'inputs'/tid;om=read(original/'manifest.json')
    for f,info in om['files'].items():assert sha(original/f)==info['sha256'];shutil.copyfile(original/f,out/f)
    ct=arrays(out/'training.npz');cq=arrays(out/'inference.npz')
    for key in tr:
     if key!='X':assert np.array_equal(tr[key],ct[key],equal_nan=tr[key].dtype.kind=='f')
    assert np.array_equal(ct['X'],panel.loc[tr['pid'],spec['columns']].to_numpy(float),equal_nan=True)and np.array_equal(cq['X'],panel.loc[q['pid'],spec['columns']].to_numpy(float),equal_nan=True)
    e=logged[tid];assert e['file']==f'jobs/{tid}/result.json';record_path=L/'results'/e['file'];assert sha(record_path)==e['sha256'];dest=ROOT/'source_refs/records'/f'{tid}.json';shutil.copyfile(record_path,dest)
    source_controls[tid]={'file':str(dest.relative_to(ROOT)),'sha256':sha(dest),'source_completed_entry':e,'source_input_manifest':om,'source_input_manifest_sha256':sha(original/'manifest.json'),'source_input_directory':str(original)}
   else:
    np.savez_compressed(out/'training.npz',**{**tr,'X':panel.loc[tr['pid'],spec['columns']].to_numpy(float)})
    np.savez_compressed(out/'inference.npz',**{**q,'X':panel.loc[q['pid'],spec['columns']].to_numpy(float)})
   m={'task_id':tid,'panel_id':spec['id'],'policy_id':protocol['policy_id'],'outer_year':y,'columns':spec['columns'],'protocol_sha256':sha(ROOT/'code/protocol.json'),'files':{n:{'sha256':sha(out/n)}for n in ['training.npz','inference.npz']},'label_audit':bm['label_audit']};save(out/'manifest.json',m)
   tasks.append({'id':tid,'panel_id':spec['id'],'policy_id':protocol['policy_id'],'outer_year':y,'input_manifest_sha256':sha(out/'manifest.json'),'training_rows':len(tr['pid']),'query_rows':len(q['pid']),'kind':'reused_L_control'if reuse else'new_model_job'})
 for name,path in [('L_completed.jsonl',source_log),('L_completion.json',L/'results/completion.json'),('L_frozen.json',L/'frozen.json')]:shutil.copyfile(path,ROOT/'source_refs'/name)
 source={'study':'r9l','L_frozen_sha256':sha(L/'frozen.json'),'L_protocol_sha256':sha(L/'code/protocol.json'),'L_runtime_sha256':sha(L/'code/runtime_support.json'),'source_completed_log_sha256':sha(source_log),'source_completion_sha256':sha(L/'results/completion.json'),'control_records':source_controls,'source_records_unchanged':True,'control_model_refits':0};save(ROOT/'source_refs/manifest.json',source)
 plan={'study':'R9M complementary panels and cross-panel model-family stacks','target_percent':55,'tasks':tasks,'task_count':24,'new_model_jobs':18,'reused_control_records':6,'model_fits':162,'reused_original_model_fits':54,'workers':4,'outer_years':protocol['outer_years'],'seeds':protocol['seeds'],'protocol_sha256':sha(ROOT/'code/protocol.json'),'scoring':scoring,'architectures':protocol['architectures'],'cross_panel_stacks':protocol['cross_panel_stacks'],'reference_source_manifest_sha256':sha(ROOT/'source_refs/manifest.json'),'full_pool_primary':True,'subset_secondary':True,'fitted_weights':False,'no_2019plus_scoring':True,'no_automatic_promotion':True}
 save(ROOT/'plan.json',plan);print(json.dumps({'task_records':24,'new_jobs':18,'new_fits':162,'reuse_records':6,'plan_sha256':sha(ROOT/'plan.json')}))
if __name__=='__main__':main()
