"""Frozen development scoring and two exact M recipe replays; outside model namespaces."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
from scipy.stats import rankdata
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'code'))
import reuse_controls,stack_predictions as S

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def rho(a,b):
 a=rankdata(a);b=rankdata(b);return float(np.corrcoef(a,b)[0,1])if np.ptp(a)>0 and np.ptp(b)>0 else 0.
def truths(root,plan):
 out={}
 for y in plan['outer_years']:
  path=root/'scoring'/f'{y}.npz';assert sha(path)==plan['scoring'][str(y)]['sha256']
  with np.load(path,allow_pickle=False)as q:out[y]=(q['pid'].tolist(),q['legacy_truth'].copy(),q['observed_truth_mask'].copy())
 return out

def reference_gate(root=ROOT):
 root=Path(root);sources,gate=reuse_controls.verify(root);p=read(root/'code/protocol.json');plan=read(root/'plan.json');q=truths(root,plan);saved=read(root/'source_refs/reference_recipes.json');baseline=p['baseline_profile_id'];g=p['panel_id']
 refs=[{'id':'cross_0771','kind':'fixed_rank_weights','weight_total':12,'members':[{'family':'tabicl','panel_id':g,'profile_id':baseline,'units':4},{'family':'ridge_a30','panel_id':g,'profile_id':None,'units':4},{'family':'catboost','panel_id':'base44','profile_id':None,'units':4}]},{'id':'samepanel_stack_013','kind':'fixed_rank_weights','weight_total':12,'members':[{'family':'tabicl','panel_id':g,'profile_id':baseline,'units':9},{'family':'ridge_a30','panel_id':g,'profile_id':None,'units':3}]}]
 rows=S.assemble(sources,[],refs,p);assert len(rows)==24;checked=0
 for r in rows:
  old=next(x for x in saved[r['architecture']]if x['year']==r['year']and x['seed']==r['seed']);pids,truth,mask=q[r['year']];v=np.asarray(r['prediction']);assert r['query_pids']==old['query_pids']==pids and np.array_equal(v,old['prediction'])
  assert rho(v,truth)==old['full']and rho(v[mask],truth[mask])==old['observed'];checked+=1
 return sources,{**gate,'exact_M_recipe_prediction_records':checked,'both_frozen_metrics_exact':True,'M_reference_recipes':['cross_0771','samepanel_stack_013'],'before_new_profile_fits':True}

def summarize(jobs,root=ROOT):
 root=Path(root);plan=read(root/'plan.json');p=read(root/'code/protocol.json');sources,gate=reference_gate(root);bytask={t['id']:t for t in plan['tasks']};assert len({j['task_id']for j in jobs})==len(jobs)
 for r in jobs:
  t=bytask[r['task_id']];m=read(root/'inputs'/t['id']/'manifest.json');assert sha(root/'inputs'/t['id']/'manifest.json')==t['input_manifest_sha256'];S.validate_job(r,t,m,p)
 details=[];groups={};truth=truths(root,plan)
 for r in S.assemble(sources,jobs,plan['stack_recipes'],p):
  ids,y,mask=truth[r['year']];assert r['query_pids']==ids;v=np.asarray(r['prediction']);row={**r,'full':rho(v,y),'observed':rho(v[mask],y[mask])};details.append(row);groups.setdefault(r['architecture'],[]).append(row)
 recipes={r['id']:r for r in plan['stack_recipes']};summaries=[]
 def metric(rows,name):
  direct=[r for r in rows if isinstance(r['seed'],int)];fixed=[r for r in rows if isinstance(r['seed'],str)];assert len(direct)==9 and len(fixed)==3
  return {'mean_score':float(np.mean([r[name]for r in direct])),'fold_scores':{str(y):float(np.mean([r[name]for r in direct if r['year']==y]))for y in p['outer_years']},'seed_scores':{str(s):float(np.mean([r[name]for r in direct if r['seed']==s]))for s in p['seeds']},'fixed_three_seed_family_rank_average':float(np.mean([r[name]for r in fixed]))}
 for rid,rows in groups.items():
  recipe=recipes[rid];multi=all(r['multi_family_stack']for r in rows);profile=next((m['profile_id']for m in recipe['members']if m['family']=='tabicl'),None)
  summaries.append({'panel_id':p['panel_id'],'policy_id':p['policy_id'],'profile_id':profile,'architecture':rid,'recipe':recipe,'member_control':not multi,'multi_family_every_fold_seed':multi,'diagnostic_only':True,'no_automatic_promotion':True,'full':metric(rows,'full'),'observed':metric(rows,'observed')})
 # Exact same member/view/weight recipe with the baseline TabICL profile.
 baseline=p['baseline_profile_id'];bydesign={json.dumps(s['recipe']['members'],sort_keys=True):s for s in summaries}
 for s in summaries:
  members=[{**m,'profile_id':baseline if m['family']=='tabicl'else None}for m in s['recipe']['members']];ref=bydesign.get(json.dumps(members,sort_keys=True))
  if ref:
   s['full_gain_vs_same_recipe_baseline_profile']=s['full']['mean_score']-ref['full']['mean_score'];s['full_fold_gains_vs_baseline']={y:s['full']['fold_scores'][y]-ref['full']['fold_scores'][y]for y in s['full']['fold_scores']};s['full_seed_gains_vs_baseline']={s0:s['full']['seed_scores'][s0]-ref['full']['seed_scores'][s0]for s0 in s['full']['seed_scores']}
 summaries.sort(key=lambda s:(-s['full']['mean_score'],s['architecture']));stacks=[s for s in summaries if s['multi_family_every_fold_seed']];controls=[s for s in summaries if s['member_control']];scan=read(root/'results/preprocessing_scan.json');profiles=[]
 for pid in plan['active_profiles']:
  candidates=[s for s in summaries if s['profile_id']==pid];best=next((s for s in candidates if s['multi_family_every_fold_seed']),None)
  effective=sorted({d['generator']['effective_estimators']for d in scan['designs'][pid].values()});requested=[x for x,rep in plan['profile_mapping'].items()if rep==pid]
  profiles.append({'profile_id':pid,'requested_profile_ids':requested,'requested_estimators':[next(v['n_estimators']for v in p['profiles']if v['id']==x)for x in requested],'effective_estimators':effective,'complete':bool(candidates),'best_actual_multifamily_stack':best,'baseline_reused':pid==baseline})
 return {'reference_gate':gate,'interpretation_allowed':gate['passed'],'stack_summaries_oof':stacks,'control_summaries_oof':controls,'cross_panel_summaries':summaries,'best_actual_multifamily_stack':stacks[0]if stacks else None,'best_member_control':controls[0]if controls else None,'profile_summaries':profiles,'admission_counts':{'requested_profiles':23,'active_distinct_profiles':len(plan['active_profiles']),'baseline_profiles_reused':1,'excluded_profiles':plan['rejected_profiles'],'requested_new_jobs':66,'active_new_jobs':plan['task_count'],'requested_new_fits':198,'active_new_fits':plan['model_fits'],'profile_aliases':plan['profile_mapping']},'prediction_details':details,'scored_prediction_records':len(details),'stack_recipe_count':plan['stack_recipe_count'],'full_pool_primary':True,'subset_secondary':True,'learned_weights':False,'no2019plus_access':True}
