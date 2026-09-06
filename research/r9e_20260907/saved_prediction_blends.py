"""Fixed saved-prediction complement diagnostic; no fits or favorable-seed choice."""
from pathlib import Path
import json,hashlib,math
import numpy as np
from scipy.stats import rankdata
import worker as W
R=Path(__file__).resolve().parent;O=R/'results'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,value):
 raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
def info(path):return {'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size}
def rank_blend(a,b,step):
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape and a.ndim==1 and len(a)>0 and np.isfinite(a).all()and np.isfinite(b).all()and step in range(11)
 # Average ranks are integer or half-integer. Integer arithmetic preserves exact ties.
 ra=np.rint(2*rankdata(a,method='average')).astype(np.int64);rb=np.rint(2*rankdata(b,method='average')).astype(np.int64)
 return ((10-step)*ra+step*rb)/(20*len(a))
def main():
 proof=json.loads((O/'run_verification.json').read_text());assert proof['passed']and proof['records']==1152 and proof['reference_replays_exact']==18
 frozen=json.loads((R/'frozen.json').read_text());assert sha((R/'frozen.json').read_bytes())==proof['frozen_manifest_sha256']
 for name,digest in frozen['files'].items():assert sha((R/name).read_bytes())==digest
 from tabicl import TabICLRegressor
 def forbidden(*args,**kwargs):raise AssertionError('No fitting or model prediction in saved diagnostic')
 TabICLRegressor.fit=forbidden;TabICLRegressor.predict=forbidden
 p=W.load_plan();anchors=['drop5_001','none_o0p5_n16'];records={};hashes={}
 for vid in anchors:
  assert p['settings_by_id'][vid]['target_transform']=='identity'
  for seed in p['seeds']:
   path=O/'tasks'/f'{vid}_seed{seed}.json';entry=json.loads(path.read_text());W.validate_entry(entry,p);records[(vid,seed)]=entry;hashes[str(path.relative_to(R))]=info(path)
 assert p['settings_by_id'][anchors[1]]['norm_methods']=='none'and p['settings_by_id'][anchors[1]]['n_estimators']==16 and p['settings_by_id'][anchors[1]]['outlier_threshold']==.5
 ep=O/'seed_ensembles.json';assert info(ep)==proof['seed_ensembles'];ensemble=json.loads(ep.read_text());em={e['id']:e for e in ensemble['configurations']}
 registration={'diagnostic_only':True,'models_fitted':0,'source_verification_sha256':sha((O/'run_verification.json').read_bytes()),'source_code_sha256':sha(Path(__file__).read_bytes()),'anchors':anchors,'endpoint_records':hashes,'seed_ensemble_source':info(ep),'seeds':p['seeds'],'alpha_steps':list(range(11)),'alpha':'step/10;0 baseline,1 challenger','method':'Within each query cohort, average-tied rank/n percentiles; exact doubled-integer ranks combined before division preserve algebraic ties. Same-seed endpoints and fixed equal-three-seed mean endpoints are separate diagnostics.','endpoint_selection':'Fixed parent-requested completed-development endpoints; no test/confirmation or favorable seed selection.','no_promotion':True}
 rp=O/'saved_blend_registration.json'
 if rp.exists():assert json.loads(rp.read_text())==registration
 else:save(rp,registration)
 # Meaningful tie/endpoint fixture, including original tied values and arbitrary row order.
 a=np.array([2.,2.,0.,4.]);b=np.array([0.,0.,4.,2.]);order=np.array([3,0,2,1])
 for step in range(11):
  z=rank_blend(a,b,step);assert z[0]==z[1];assert np.array_equal(rank_blend(a[order],b[order],step),z[order])
 assert np.array_equal(rank_blend(a,b,0),rankdata(a,method='average')/len(a));assert np.array_equal(rank_blend(a,b,10),rankdata(b,method='average')/len(b))
 _,_,_,folds=W.B._prepared();results=[]
 for mode in ['same_seed','fixed_three_seed_average']:
  seeds=p['seeds']if mode=='same_seed'else[None]
  for step in range(11):
   rows=[]
   for seed in seeds:
    for fold in folds:
     endpoints=[records[(v,seed)]if seed is not None else em[v]for v in anchors];rr=[next(r for r in e['rows']if r['season']==fold['year'])for e in endpoints]
     pids=[x['pid']for x in rr[0]['predictions']];assert pids==fold['te'].pid.tolist()==[x['pid']for x in rr[1]['predictions']]
     z=rank_blend([x['score']for x in rr[0]['predictions']],[x['score']for x in rr[1]['predictions']],step);score=W.B.rho(z,fold['truth'])
     if step in [0,10]:assert score==rr[step//10]['stack']
     rows.append({'season':fold['year'],'seed':seed,'score':score,'baseline':rr[0]['stack'],'challenger':rr[1]['stack'],'gain_vs_baseline':score-rr[0]['stack'],'predictions':[{'pid':pid,'score':float(value)}for pid,value in zip(pids,z)]})
   results.append({'mode':mode,'alpha_step':step,'alpha':step/10,'mean_score':float(np.mean([r['score']for r in rows])),'mean_gain_vs_baseline':float(np.mean([r['gain_vs_baseline']for r in rows])),'fold_gains':{str(y):float(np.mean([r['gain_vs_baseline']for r in rows if r['season']==y]))for y in p['folds']},'seed_gains':{str(seed):float(np.mean([r['gain_vs_baseline']for r in rows if r['seed']==seed]))for seed in seeds},'rows':rows})
 output={'registration':registration,'all_endpoint_scores_exact':True,'tie_and_row_order_fixture_passed':True,'diagnostics':results};save(O/'saved_blend_predictions.json',output)
 slim={'registration':registration,'all_endpoint_scores_exact':True,'tie_and_row_order_fixture_passed':True,'diagnostics':[{k:v for k,v in e.items()if k!='rows'}for e in results],'prediction_artifact':info(O/'saved_blend_predictions.json')};save(O/'saved_blend_summary.json',slim)
 public=json.loads((O/'PUBLIC_ALLOWLIST.json').read_text())
 for name in ['saved_prediction_blends.py','run_blend_sandbox.sh','results/saved_blend_registration.json','results/saved_blend_predictions.json','results/saved_blend_summary.json']:public['files'][name]=info(R/name)
 public['total_bytes']=sum(f['bytes']for f in public['files'].values());save(O/'PUBLIC_ALLOWLIST.json',public)
 print(json.dumps({'passed':True,'model_fits':0,'diagnostics':len(results),'alpha_steps':11,'same_seed_rows':99,'seed_average_rows':33,'all_endpoint_scores_exact':True,'public_allowlist':info(O/'PUBLIC_ALLOWLIST.json'),'public_files':len(public['files']),'public_bytes':public['total_bytes']}))
if __name__=='__main__':main()
