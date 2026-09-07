"""Stream all prespecified checkpoint/anchor rank blends from saved predictions."""
from pathlib import Path
import json,gzip,hashlib,math
import numpy as np
from scipy.stats import rankdata
import worker as W

def sha(raw):return hashlib.sha256(raw).hexdigest()
def rank_blend(a,b,step):
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape and a.ndim==1 and np.isfinite(a).all()and np.isfinite(b).all()and step in range(11)
 ra=np.rint(2*rankdata(a,method='average')).astype(np.int64);rb=np.rint(2*rankdata(b,method='average')).astype(np.int64)
 return ((10-step)*ra+step*rb)/(20*len(a))
def save(path,value):
 raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
def fixed_mean(arrays):
 assert len(arrays)==3 and len({len(a)for a in arrays})==1
 return np.asarray([math.fsum(a[i]for a in arrays)/3 for i in range(len(arrays[0]))])
def process(records,out):
 p=W.load_plan();out=Path(out);dest=out/'blend_diagnostics';dest.mkdir(exist_ok=True);tasks={(r['config']['id'],r['seed']):r for r in records};assert len(tasks)==len(records)==p['execution']['task_count']
 assert W.summarize_matched(records)['reference_replays_passed']==3
 _,_,_,folds=W.B._prepared();truth={f['year']:f['truth']for f in folds};pids={f['year']:f['te'].pid.tolist()for f in folds};anchors=W.anchors();seeds=p['seeds'];av={};cv={};base=p['reference_id'];summary=[];chunks=[]
 for vid in p['blend_diagnostic']['anchors']:
  for year in p['folds']:
   for seed in seeds:
    row=next(r for r in anchors[(vid,seed)]['rows']if r['season']==year);assert [v['pid']for v in row['predictions']]==pids[year];av[(vid,seed,year)]=np.asarray([v['score']for v in row['predictions']])
   av[(vid,None,year)]=fixed_mean([av[(vid,s,year)]for s in seeds])
 for v in p['variants']:
  vid=v['id']
  if vid==base:continue
  for year in p['folds']:
   for end in p['tree_checkpoints']:
    for seed in seeds:
     row=next(r for r in tasks[(vid,seed)]['rows']if r['season']==year);cp=next(c for c in row['checkpoints']if c['ntree_end']==end);assert [r['pid']for r in cp['predictions']]==pids[year];cv[(seed,year,end)]=np.asarray([r['score']for r in cp['predictions']])
    cv[(None,year,end)]=fixed_mean([cv[(s,year,end)]for s in seeds])
  path=dest/(vid+'.jsonl.gz');tmp=path.with_suffix('.tmp');line_info=[];unc=hashlib.sha256();unc_bytes=0
  with tmp.open('wb')as file:
   with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0,compresslevel=6)as stream:
    for end in p['tree_checkpoints']:
     for anchor in p['blend_diagnostic']['anchors']:
      for mode in ['same_seed','fixed_three_seed_average']:
       use_seeds=seeds if mode=='same_seed'else[None]
       for step in p['blend_diagnostic']['alpha_steps']:
        rows=[]
        for seed in use_seeds:
         for year in p['folds']:
          a=av[(anchor,seed,year)];b=cv[(seed,year,end)];z=rank_blend(a,b,step);score=W.B.rho(z,truth[year]);ba=W.B.rho(av[(base,seed,year)],truth[year]);aa=W.B.rho(a,truth[year])
          if step in [0,10]:assert score==W.B.rho(a if step==0 else b,truth[year])
          rows.append({'season':year,'seed':seed,'stack':score,'anchor_score':aa,'baseline_score':ba,'gain_vs_anchor':score-aa,'gain_vs_baseline':score-ba,'predictions':[{'pid':pid,'score':float(value)}for pid,value in zip(pids[year],z)]})
        metric={'id':vid,'ntree_end':end,'anchor':anchor,'mode':mode,'alpha_step':step,'alpha':step/10,'mean_score':float(np.mean([r['stack']for r in rows])),'mean_gain_vs_baseline':float(np.mean([r['gain_vs_baseline']for r in rows])),'mean_gain_vs_anchor':float(np.mean([r['gain_vs_anchor']for r in rows])),'fold_gains':{str(y):float(np.mean([r['gain_vs_baseline']for r in rows if r['season']==y]))for y in p['folds']},'seed_gains':{str(s):float(np.mean([r['gain_vs_baseline']for r in rows if r['seed']==s]))for s in use_seeds}}
        raw=json.dumps({**metric,'rows':rows},sort_keys=True,separators=(',',':'),allow_nan=False).encode();line=raw+b'\n';stream.write(line);unc.update(line);unc_bytes+=len(line);line_info.append({'line_1based':len(line_info)+1,'sha256':sha(raw),'bytes':len(raw)});summary.append(metric)
  assert tmp.stat().st_size<40_000_000
  if path.exists():assert sha(path.read_bytes())==sha(tmp.read_bytes());tmp.unlink()
  else:tmp.replace(path)
  restored=hashlib.sha256()
  with gzip.open(path,'rb')as stream:
   for info in line_info:
    line=stream.readline();assert line.endswith(b'\n')and sha(line[:-1])==info['sha256']and len(line)-1==info['bytes'];restored.update(line)
   assert not stream.read()
  assert restored.hexdigest()==unc.hexdigest()
  chunks.append({'file':str(path.relative_to(out)),'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size,'uncompressed_bytes':unc_bytes,'uncompressed_sha256':unc.hexdigest(),'recipes':line_info,'all_roundtrips_exact':True})
  save(out/'postprocess_progress.json',{'status':'running','completed_configurations':len(chunks),'total_configurations':len(p['variants'])-1,'model_fits':0})
 payload={'diagnostic_only':True,'no_model_promotion':True,'method':p['blend_diagnostic'],'all_endpoints_exact':True,'all_three_model_seeds_fixed':True,'configurations':len(chunks),'recipes':len(summary),'chunks':chunks};save(out/'blend_manifest.json',payload)
 save(out/'blend_summary.json',{'diagnostic_only':True,'no_model_promotion':True,'method':p['blend_diagnostic'],'all_endpoints_exact':True,'diagnostics':summary})
 save(out/'postprocess_progress.json',{'status':'completed','completed_configurations':len(chunks),'total_configurations':len(chunks),'model_fits':0,'recipes':len(summary)})
 return {'configurations':len(chunks),'recipes':len(summary),'chunks':len(chunks),'all_endpoints_and_roundtrips_exact':True,'source_models_only':True}
