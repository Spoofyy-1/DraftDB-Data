from pathlib import Path
import sys,json,hashlib,collections,math,datetime
import numpy as np
from scipy.stats import rankdata,spearmanr
R=Path('/home/ubuntu/nba/handoff/r9n');O=R/'results';sys.path[:0]=[str(R),str(R/'code')]
import research,postprocess,stack_core as C

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
a=research.pins();p=read(R/'code/protocol.json');plan=read(R/'plan.json');finish=read(O/'completion.json');manifest=read(O/'result_manifest.json')
assert finish['status']=='completed' and finish['tasks']==51 and finish['new_TabICL_fits']==153
assert finish['result_manifest_sha256']==sha(O/'result_manifest.json')
assert manifest['diagnostics_sha256']==sha(O/'stack_diagnostics.json')
d=read(O/'stack_diagnostics.json');lines=[json.loads(s)for s in (O/'completed.jsonl').read_text().splitlines()];assert len(lines)==51 and len({e['task_id']for e in lines})==51
assert {e['task_id']:e for e in lines}==manifest['tasks']
jobs=[]
for t in plan['tasks']:
 e=manifest['tasks'][t['id']];assert e['file']==f"jobs/{t['id']}/result.json" and sha(O/e['file'])==e['sha256'];r=read(O/e['file']);research.validate(r,t)
 with np.load(R/'inputs'/t['id']/'inference.npz',allow_pickle=False)as q:
  for m in r['members']:
   v,ta=C.canonicalize(q['X'],m['raw_predictions'],r['query_pids']);assert v.tolist()==m['canonical_predictions'] and ta==m['tie_audit']
 jobs.append(r)
sources,gate=postprocess.reference_gate(R);assert gate==d['reference_gate']==read(O/'reference_gate.json')
recalc=postprocess.summarize(jobs,R);assert recalc==d
# Independent prediction and scipy Spearman reconstruction, without S.assemble or postprocess.rho.
J={(j['profile_id'],j['outer_year']):j for j in jobs};Q={}
for year in p['outer_years']:
 with np.load(R/'scoring'/f'{year}.npz',allow_pickle=False)as q:Q[year]=(q['pid'].tolist(),q['legacy_truth'].copy(),q['observed_truth_mask'].copy())
base=p['baseline_profile_id'];cache={};byrecipe={r['id']:r for r in plan['stack_recipes']};group=collections.defaultdict(list);maxerr=0.
for row in d['prediction_details']:
 year=row['year'];mode=row['seed'];ids,y,mask=Q[year];recipe=byrecipe[row['architecture']];assert row['query_pids']==ids;n=len(ids);parts=[]
 for member in recipe['members']:
  family=member['family'];pid=member['profile_id'];panel=member['panel_id'];key=(year,mode,family,pid,panel)
  if key not in cache:
   if family!='tabicl' or pid==base:
    seedrows=sources[(panel,year)]['seed_results'];vectors={s['seed']:np.asarray(s['members'][family]['canonical_predictions']) for s in seedrows}
   else:vectors={s['seed']:np.asarray(s['canonical_predictions'])for s in J[(pid,year)]['members']}
   if isinstance(mode,int):v=vectors[mode]
   elif family.startswith('ridge_'):
    v=vectors[0];assert all(np.array_equal(v,w)for w in vectors.values())
   else:v=np.sum([np.rint(2*rankdata(vectors[s],method='average')).astype(np.int64) for s in p['seeds']],axis=0,dtype=np.int64)/(6*n)
   cache[key]=np.rint(2*rankdata(v,method='average')).astype(np.int64)
  parts.append(cache[key]*member['units'])
 predicted=np.sum(parts,axis=0,dtype=np.int64)/(24*n)
 assert np.array_equal(predicted,row['prediction']) and C.array_hash(predicted)==row['prediction_hash']
 vals={name:float(spearmanr(predicted[k],y[k]).statistic) if np.ptp(predicted[k])>0 and np.ptp(y[k])>0 else 0. for name,k in [('full',np.ones(n,dtype=bool)),('observed',mask)]}
 for name,v in vals.items():maxerr=max(maxerr,abs(row[name]-v));assert abs(row[name]-v)<1e-14
 group[row['architecture']].append({**row,**vals})
assert len(group)==1358 and len(d['prediction_details'])==16296
for s in d['cross_panel_summaries']:
 rows=group[s['architecture']];direct=[r for r in rows if isinstance(r['seed'],int)];fixed=[r for r in rows if isinstance(r['seed'],str)];assert len(direct)==9 and len(fixed)==3
 for metric in ['full','observed']:
  actual={'mean_score':float(np.mean([r[metric]for r in direct])),'fold_scores':{str(y):float(np.mean([r[metric]for r in direct if r['year']==y]))for y in p['outer_years']},'seed_scores':{str(seed):float(np.mean([r[metric]for r in direct if r['seed']==seed]))for seed in p['seeds']},'fixed_three_seed_family_rank_average':float(np.mean([r[metric]for r in fixed]))}
  for name,v in actual.items():
   if isinstance(v,dict):assert all(abs(v[k]-s[metric][name][k])<1e-14 for k in v)
   else:assert abs(v-s[metric][name])<1e-14
eligible=[s for s in d['cross_panel_summaries']if s['multi_family_every_fold_seed'] and not s['member_control']]
best=min(eligible,key=lambda s:(-s['full']['mean_score'],s['architecture']));assert best==d['best_actual_multifamily_stack']
profile=next(v for v in p['profiles']if v['id']==best['profile_id']);selected={
 'study':'R9N completed development selection','frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'selected_architecture':best['architecture'],'recipe':best['recipe'],
 'selection_rule':p['selection'],'selection_tiebreak':'Lexicographically smallest architecture id for an exact score tie; no seed selection',
 'development_years':p['outer_years'],'seeds':p['seeds'],'aggregation_modes':p['aggregation_modes'],
 'deployment_aggregation':'fixed_three_seed_family_rank_average; rank each canonical seed prediction within query cohort, average seed ranks per stochastic family, re-rank each family then fixed recipe weighted average; Ridge deterministic once',
 'tabicl':{**p['tabicl_base'],**{k:v for k,v in profile.items()if k!='id'}},'tabicl_profile':profile,
 'ridge':p['ridge'],'catboost':p['catboost'],'panels':p['source_panels'],'policy_id':p['policy_id'],'labels':p['labels'],
 'tie_policy':'Canonical pid hash row order; equal model-input vectors receive identical averaged predictions per family before average-rank blending; never use draft order or outcome for ties',
 'primary_development_score':best['full']['mean_score'],'fixed_three_seed_development_score':best['full']['fixed_three_seed_family_rank_average'],
 'development_summary':best,'source_protocol_sha256':sha(R/'code/protocol.json'),'source_plan_sha256':sha(R/'plan.json'),'source_frozen_sha256':sha(R/'frozen.json'),'source_results_sha256':sha(O/'stack_diagnostics.json'),
 'verification':'independent_verification.json','no2019plus_access':True,'no_new_fits':True,
 'limitations':p['limitations']}
proof={'passed':True,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_files':len(read(R/'frozen.json')['files']),'frozen_sha256':sha(R/'frozen.json'),'new_jobs':len(jobs),'new_TabICL_fits':153,'preprocessing_fingerprints_verified':153,'all_equal_input_ties_reconstructed':True,'reference_gate':gate,'recipes':len(group),'prediction_score_records':len(d['prediction_details']),'entire_saved_summary_reproduced_exactly':True,'independent_rank_predictions_byte_exact':True,'independent_scipy_score_max_error':maxerr,'primary_best_recipe':best['architecture'],'primary_full_score':best['full']['mean_score'],'strongest_standalone':d['best_member_control']['full']['mean_score'],'fixed_seed_average':best['full']['fixed_three_seed_family_rank_average'],'no2019plus_access':True,'no_new_fits':True,'completion_sha256':sha(O/'completion.json'),'result_manifest_sha256':sha(O/'result_manifest.json')}
write(O/'selection.json',selected);proof['selection_sha256']=sha(O/'selection.json');write(O/'independent_verification.json',proof);write(O/'compact_results.json',{k:v for k,v in d.items()if k not in ['prediction_details','cross_panel_summaries','stack_summaries_oof','control_summaries_oof']})
print(json.dumps(proof,indent=2))
